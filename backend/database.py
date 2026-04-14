"""
SQLite database module for the Engineering Change Management System.
Manages parts, dependencies, assemblies, BOM, documents, change history,
PDM (revisions, metadata), and ERP (orders, inventory, procurement).
"""

import sqlite3
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

# Database file path
DB_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DB_DIR / "ecm.db"


def get_connection() -> sqlite3.Connection:
    """Get a SQLite connection with row_factory enabled."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema():
    """Create all database tables."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
        -- ═══ CORE TABLES ═══════════════════════════════════
        CREATE TABLE IF NOT EXISTS parts (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            material TEXT,
            category TEXT,
            parameters TEXT DEFAULT '{}',
            weight_kg REAL,
            cost_usd REAL,
            source TEXT DEFAULT 'demo',
            filepath TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS dependencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            part_id TEXT NOT NULL,
            depends_on TEXT NOT NULL,
            relationship_type TEXT,
            description TEXT,
            coupling_factor REAL DEFAULT 0.5,
            FOREIGN KEY (part_id) REFERENCES parts(id),
            FOREIGN KEY (depends_on) REFERENCES parts(id)
        );

        CREATE TABLE IF NOT EXISTS assemblies (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            parent_assembly TEXT
        );

        CREATE TABLE IF NOT EXISTS assembly_parts (
            assembly_id TEXT,
            part_id TEXT,
            quantity INTEGER DEFAULT 1,
            PRIMARY KEY (assembly_id, part_id),
            FOREIGN KEY (assembly_id) REFERENCES assemblies(id),
            FOREIGN KEY (part_id) REFERENCES parts(id)
        );

        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            doc_type TEXT,
            related_part TEXT,
            revision TEXT DEFAULT 'A',
            status TEXT DEFAULT 'current',
            filepath TEXT,
            FOREIGN KEY (related_part) REFERENCES parts(id)
        );

        CREATE TABLE IF NOT EXISTS change_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            change_id TEXT UNIQUE,
            change_request TEXT,
            parsed_instruction TEXT,
            target_part TEXT,
            modification_type TEXT,
            classification TEXT,
            risk_level TEXT,
            impact_summary TEXT,
            original_file TEXT,
            modified_file TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- ═══ PDM TABLES ════════════════════════════════════
        CREATE TABLE IF NOT EXISTS revisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            part_id TEXT NOT NULL,
            revision TEXT NOT NULL DEFAULT 'A',
            change_id TEXT,
            description TEXT,
            author TEXT DEFAULT 'system',
            status TEXT DEFAULT 'released',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (part_id) REFERENCES parts(id)
        );

        CREATE TABLE IF NOT EXISTS cad_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            part_id TEXT NOT NULL,
            revision TEXT DEFAULT 'A',
            volume_mm3 REAL,
            surface_area_mm2 REAL,
            bbox_length REAL,
            bbox_width REAL,
            bbox_height REAL,
            mass_kg REAL,
            material TEXT,
            units TEXT DEFAULT 'mm',
            fusion_file TEXT,
            step_file TEXT,
            stl_file TEXT,
            captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (part_id) REFERENCES parts(id)
        );

        -- ═══ ERP TABLES ════════════════════════════════════
        CREATE TABLE IF NOT EXISTS bom_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assembly_id TEXT NOT NULL,
            part_id TEXT NOT NULL,
            quantity INTEGER DEFAULT 1,
            unit_cost REAL DEFAULT 0,
            total_cost REAL DEFAULT 0,
            lead_time_days INTEGER DEFAULT 7,
            supplier TEXT,
            make_or_buy TEXT DEFAULT 'make',
            FOREIGN KEY (assembly_id) REFERENCES assemblies(id),
            FOREIGN KEY (part_id) REFERENCES parts(id)
        );

        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            part_id TEXT NOT NULL UNIQUE,
            stock_quantity INTEGER DEFAULT 0,
            min_stock INTEGER DEFAULT 5,
            max_stock INTEGER DEFAULT 100,
            reorder_point INTEGER DEFAULT 10,
            warehouse_location TEXT DEFAULT 'WH-01',
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (part_id) REFERENCES parts(id)
        );

        CREATE TABLE IF NOT EXISTS suppliers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            contact TEXT,
            material_types TEXT,
            lead_time_days INTEGER DEFAULT 14,
            rating REAL DEFAULT 4.0
        );

        CREATE TABLE IF NOT EXISTS manufacturing_orders (
            id TEXT PRIMARY KEY,
            change_id TEXT,
            part_id TEXT,
            order_type TEXT DEFAULT 'modification',
            status TEXT DEFAULT 'draft',
            priority TEXT DEFAULT 'normal',
            quantity INTEGER DEFAULT 1,
            estimated_cost REAL DEFAULT 0,
            estimated_hours REAL DEFAULT 0,
            assigned_to TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            due_date TEXT,
            completed_at TEXT,
            FOREIGN KEY (part_id) REFERENCES parts(id)
        );

        CREATE TABLE IF NOT EXISTS change_orders (
            id TEXT PRIMARY KEY,
            change_id TEXT UNIQUE,
            title TEXT,
            description TEXT,
            status TEXT DEFAULT 'draft',
            priority TEXT DEFAULT 'normal',
            requested_by TEXT DEFAULT 'system',
            approved_by TEXT,
            target_part TEXT,
            classification TEXT,
            risk_level TEXT,
            total_cost REAL DEFAULT 0,
            total_effort_hours REAL DEFAULT 0,
            affected_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            approved_at TEXT,
            completed_at TEXT,
            FOREIGN KEY (target_part) REFERENCES parts(id)
        );
    """)

    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════
#  PART OPERATIONS
# ═══════════════════════════════════════════════════════════

def get_all_parts(source: Optional[str] = None) -> List[Dict]:
    conn = get_connection()
    if source:
        rows = conn.execute("SELECT * FROM parts WHERE source = ?", (source,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM parts ORDER BY source, name").fetchall()
    conn.close()
    result = []
    for row in rows:
        part = dict(row)
        part["parameters"] = json.loads(part.get("parameters") or "{}")
        result.append(part)
    return result


def get_part_by_name(name: str) -> Optional[Dict]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM parts WHERE LOWER(name) = LOWER(?) OR LOWER(REPLACE(name, '_', ' ')) = LOWER(?)",
        (name, name)
    ).fetchone()
    conn.close()
    if row:
        part = dict(row)
        part["parameters"] = json.loads(part.get("parameters") or "{}")
        return part
    return None


def get_part_by_id(part_id: str) -> Optional[Dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM parts WHERE id = ?", (part_id,)).fetchone()
    conn.close()
    if row:
        part = dict(row)
        part["parameters"] = json.loads(part.get("parameters") or "{}")
        return part
    return None


def upsert_part(part_data: Dict):
    conn = get_connection()
    params = part_data.get("parameters", {})
    if isinstance(params, dict):
        params = json.dumps(params)

    conn.execute("""
        INSERT OR REPLACE INTO parts (id, name, description, material, category,
                                       parameters, weight_kg, cost_usd, source, filepath)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        part_data["id"], part_data["name"], part_data.get("description"),
        part_data.get("material"), part_data.get("category"),
        params, part_data.get("weight_kg"), part_data.get("cost_usd"),
        part_data.get("source", "demo"), part_data.get("filepath")
    ))
    conn.commit()
    conn.close()


def get_all_part_names() -> List[str]:
    conn = get_connection()
    rows = conn.execute("SELECT name FROM parts").fetchall()
    conn.close()
    return [row["name"] for row in rows]


# ═══════════════════════════════════════════════════════════
#  DEPENDENCY OPERATIONS
# ═══════════════════════════════════════════════════════════

def get_dependencies(part_name: str) -> List[Dict]:
    """Get all parts that are affected if the given part changes."""
    conn = get_connection()

    rows = conn.execute("""
        SELECT d.*, p.name as affected_name, p.description as affected_description,
               p.material as affected_material, p.category as affected_category
        FROM dependencies d
        JOIN parts p ON d.part_id = p.id
        JOIN parts target ON d.depends_on = target.id
        WHERE LOWER(target.name) = LOWER(?) 
           OR LOWER(REPLACE(target.name, '_', ' ')) = LOWER(?)
    """, (part_name, part_name)).fetchall()

    rows2 = conn.execute("""
        SELECT d.*, p.name as affected_name, p.description as affected_description,
               p.material as affected_material, p.category as affected_category
        FROM dependencies d
        JOIN parts p ON d.depends_on = p.id
        JOIN parts target ON d.part_id = target.id
        WHERE LOWER(target.name) = LOWER(?)
           OR LOWER(REPLACE(target.name, '_', ' ')) = LOWER(?)
    """, (part_name, part_name)).fetchall()

    conn.close()

    affected = []
    seen_names = set()
    for row in list(rows) + list(rows2):
        name = row["affected_name"]
        if name not in seen_names and name.lower() != part_name.lower():
            seen_names.add(name)
            affected.append({
                "part_id": row["part_id"],
                "part_name": name,
                "relationship": row["relationship_type"],
                "description": row["description"] or f"Related to {part_name}",
                "material": row["affected_material"],
                "category": row["affected_category"],
                "coupling_factor": row["coupling_factor"] if "coupling_factor" in row.keys() else 0.5,
            })

    return affected


def get_dependency_with_coupling(part_id_a: str, part_id_b: str) -> Optional[Dict]:
    """Get the dependency record between two specific parts."""
    conn = get_connection()
    row = conn.execute("""
        SELECT * FROM dependencies 
        WHERE (part_id = ? AND depends_on = ?) OR (part_id = ? AND depends_on = ?)
    """, (part_id_a, part_id_b, part_id_b, part_id_a)).fetchone()
    conn.close()
    return dict(row) if row else None


def add_dependency(part_id: str, depends_on: str, rel_type: str, description: str = "", coupling_factor: float = 0.5):
    conn = get_connection()
    conn.execute("""
        INSERT OR IGNORE INTO dependencies (part_id, depends_on, relationship_type, description, coupling_factor)
        VALUES (?, ?, ?, ?, ?)
    """, (part_id, depends_on, rel_type, description, coupling_factor))
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════
#  DOCUMENT OPERATIONS
# ═══════════════════════════════════════════════════════════

def get_documents_for_part(part_name: str) -> List[Dict]:
    conn = get_connection()
    rows = conn.execute("""
        SELECT d.* FROM documents d
        JOIN parts p ON d.related_part = p.id
        WHERE LOWER(p.name) = LOWER(?) 
           OR LOWER(REPLACE(p.name, '_', ' ')) = LOWER(?)
    """, (part_name, part_name)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ═══════════════════════════════════════════════════════════
#  ASSEMBLY & BOM OPERATIONS
# ═══════════════════════════════════════════════════════════

def get_assembly_parts(assembly_id: str) -> List[Dict]:
    conn = get_connection()
    rows = conn.execute("""
        SELECT ap.quantity, p.* FROM assembly_parts ap
        JOIN parts p ON ap.part_id = p.id
        WHERE ap.assembly_id = ?
    """, (assembly_id,)).fetchall()
    conn.close()
    result = []
    for row in rows:
        part = dict(row)
        part["parameters"] = json.loads(part.get("parameters") or "{}")
        result.append(part)
    return result


def get_bom(assembly_id: str = "ASM-001") -> List[Dict]:
    """Get full BOM with costs."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT b.*, p.name, p.material, p.category, p.weight_kg
        FROM bom_items b
        JOIN parts p ON b.part_id = p.id
        WHERE b.assembly_id = ?
        ORDER BY p.name
    """, (assembly_id,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_bom_total_cost(assembly_id: str = "ASM-001") -> float:
    conn = get_connection()
    row = conn.execute(
        "SELECT SUM(total_cost) as total FROM bom_items WHERE assembly_id = ?",
        (assembly_id,)
    ).fetchone()
    conn.close()
    return row["total"] or 0.0


# ═══════════════════════════════════════════════════════════
#  PDM — REVISION OPERATIONS
# ═══════════════════════════════════════════════════════════

def get_revisions(part_id: str) -> List[Dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM revisions WHERE part_id = ? ORDER BY created_at DESC", (part_id,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def add_revision(part_id: str, revision: str, change_id: str = None,
                 description: str = "", author: str = "system"):
    conn = get_connection()
    conn.execute("""
        INSERT INTO revisions (part_id, revision, change_id, description, author)
        VALUES (?, ?, ?, ?, ?)
    """, (part_id, revision, change_id, description, author))
    conn.commit()
    conn.close()


def get_latest_revision(part_id: str) -> str:
    conn = get_connection()
    row = conn.execute(
        "SELECT revision FROM revisions WHERE part_id = ? ORDER BY created_at DESC LIMIT 1",
        (part_id,)
    ).fetchone()
    conn.close()
    return row["revision"] if row else "A"


def increment_revision(current_rev: str) -> str:
    """A → B → C ... Z → AA"""
    if not current_rev:
        return "B"
    if len(current_rev) == 1 and current_rev < "Z":
        return chr(ord(current_rev) + 1)
    return current_rev + "A"


# ═══════════════════════════════════════════════════════════
#  PDM — CAD METADATA
# ═══════════════════════════════════════════════════════════

def save_cad_metadata(part_id: str, metadata: Dict):
    conn = get_connection()
    conn.execute("""
        INSERT INTO cad_metadata (part_id, revision, volume_mm3, surface_area_mm2,
                                   bbox_length, bbox_width, bbox_height, mass_kg,
                                   material, units, fusion_file, step_file, stl_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        part_id, metadata.get("revision", "A"),
        metadata.get("volume_mm3"), metadata.get("surface_area_mm2"),
        metadata.get("bbox_length"), metadata.get("bbox_width"), metadata.get("bbox_height"),
        metadata.get("mass_kg"), metadata.get("material"), metadata.get("units", "mm"),
        metadata.get("fusion_file"), metadata.get("step_file"), metadata.get("stl_file"),
    ))
    conn.commit()
    conn.close()


def get_cad_metadata(part_id: str) -> Optional[Dict]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM cad_metadata WHERE part_id = ? ORDER BY captured_at DESC LIMIT 1",
        (part_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ═══════════════════════════════════════════════════════════
#  ERP — INVENTORY
# ═══════════════════════════════════════════════════════════

def get_inventory(part_id: str = None) -> List[Dict]:
    conn = get_connection()
    if part_id:
        rows = conn.execute("""
            SELECT i.*, p.name, p.material FROM inventory i
            JOIN parts p ON i.part_id = p.id WHERE i.part_id = ?
        """, (part_id,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT i.*, p.name, p.material FROM inventory i
            JOIN parts p ON i.part_id = p.id ORDER BY p.name
        """).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_inventory(part_id: str, quantity_change: int):
    conn = get_connection()
    conn.execute("""
        UPDATE inventory SET stock_quantity = MAX(0, stock_quantity + ?),
                             last_updated = CURRENT_TIMESTAMP
        WHERE part_id = ?
    """, (quantity_change, part_id))
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════
#  ERP — MANUFACTURING ORDERS
# ═══════════════════════════════════════════════════════════

def create_manufacturing_order(order_data: Dict):
    conn = get_connection()
    conn.execute("""
        INSERT OR REPLACE INTO manufacturing_orders
        (id, change_id, part_id, order_type, status, priority,
         quantity, estimated_cost, estimated_hours, assigned_to, notes, due_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        order_data["id"], order_data.get("change_id"), order_data.get("part_id"),
        order_data.get("order_type", "modification"), order_data.get("status", "draft"),
        order_data.get("priority", "normal"), order_data.get("quantity", 1),
        order_data.get("estimated_cost", 0), order_data.get("estimated_hours", 0),
        order_data.get("assigned_to"), order_data.get("notes"),
        order_data.get("due_date"),
    ))
    conn.commit()
    conn.close()


def get_manufacturing_orders(status: str = None) -> List[Dict]:
    conn = get_connection()
    if status:
        rows = conn.execute("""
            SELECT m.*, p.name as part_name FROM manufacturing_orders m
            LEFT JOIN parts p ON m.part_id = p.id
            WHERE m.status = ? ORDER BY m.created_at DESC
        """, (status,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT m.*, p.name as part_name FROM manufacturing_orders m
            LEFT JOIN parts p ON m.part_id = p.id
            ORDER BY m.created_at DESC
        """).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_order_status(order_id: str, new_status: str):
    conn = get_connection()
    updates = {"status": new_status}
    if new_status == "completed":
        updates["completed_at"] = datetime.now().isoformat()
    conn.execute(
        "UPDATE manufacturing_orders SET status = ?, completed_at = ? WHERE id = ?",
        (new_status, updates.get("completed_at"), order_id)
    )
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════
#  ERP — CHANGE ORDERS (WORKFLOW)
# ═══════════════════════════════════════════════════════════

def create_change_order(data: Dict):
    conn = get_connection()
    conn.execute("""
        INSERT OR REPLACE INTO change_orders
        (id, change_id, title, description, status, priority, requested_by,
         target_part, classification, risk_level, total_cost, 
         total_effort_hours, affected_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data["id"], data.get("change_id"), data.get("title"), data.get("description"),
        data.get("status", "draft"), data.get("priority", "normal"),
        data.get("requested_by", "system"), data.get("target_part"),
        data.get("classification"), data.get("risk_level"),
        data.get("total_cost", 0), data.get("total_effort_hours", 0),
        data.get("affected_count", 0),
    ))
    conn.commit()
    conn.close()


def get_change_orders(status: str = None) -> List[Dict]:
    conn = get_connection()
    if status:
        rows = conn.execute(
            "SELECT * FROM change_orders WHERE status = ? ORDER BY created_at DESC",
            (status,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM change_orders ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_change_order_status(change_id: str, new_status: str, approved_by: str = None):
    conn = get_connection()
    now = datetime.now().isoformat()
    if new_status == "approved":
        conn.execute(
            "UPDATE change_orders SET status = ?, approved_by = ?, approved_at = ?, updated_at = ? WHERE change_id = ?",
            (new_status, approved_by, now, now, change_id)
        )
    elif new_status == "completed":
        conn.execute(
            "UPDATE change_orders SET status = ?, completed_at = ?, updated_at = ? WHERE change_id = ?",
            (new_status, now, now, change_id)
        )
    else:
        conn.execute(
            "UPDATE change_orders SET status = ?, updated_at = ? WHERE change_id = ?",
            (new_status, now, change_id)
        )
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════
#  ERP — SUPPLIERS
# ═══════════════════════════════════════════════════════════

def get_suppliers() -> List[Dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM suppliers ORDER BY rating DESC").fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ═══════════════════════════════════════════════════════════
#  CHANGE HISTORY
# ═══════════════════════════════════════════════════════════

def save_change_history(change_data: Dict):
    conn = get_connection()
    conn.execute("""
        INSERT INTO change_history 
        (change_id, change_request, parsed_instruction, target_part,
         modification_type, classification, risk_level, impact_summary,
         original_file, modified_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        change_data.get("change_id"),
        change_data.get("change_request"),
        json.dumps(change_data.get("parsed_instruction", {})),
        change_data.get("target_part"),
        change_data.get("modification_type"),
        change_data.get("classification"),
        change_data.get("risk_level"),
        json.dumps(change_data.get("impact_summary", {})),
        change_data.get("original_file"),
        change_data.get("modified_file"),
    ))
    conn.commit()
    conn.close()


def get_change_history() -> List[Dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM change_history ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def clear_demo_data():
    conn = get_connection()
    conn.execute("DELETE FROM manufacturing_orders")
    conn.execute("DELETE FROM change_orders")
    conn.execute("DELETE FROM inventory")
    conn.execute("DELETE FROM bom_items")
    conn.execute("DELETE FROM cad_metadata")
    conn.execute("DELETE FROM revisions")
    conn.execute("DELETE FROM assembly_parts WHERE assembly_id IN (SELECT id FROM assemblies)")
    conn.execute("DELETE FROM dependencies")
    conn.execute("DELETE FROM documents")
    conn.execute("DELETE FROM assemblies")
    conn.execute("DELETE FROM suppliers")
    conn.execute("DELETE FROM parts WHERE source = 'demo'")
    conn.commit()
    conn.close()
