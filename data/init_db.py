"""
Database initialization — Universal Joint Assembly
Populates all tables: parts, dependencies (with coupling factors),
assemblies, BOM, documents, revisions, inventory, suppliers, and ERP data.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend import database as db


def populate_demo_data():
    """Populate the database with Universal Joint demo data."""
    db.init_schema()
    db.clear_demo_data()

    conn = db.get_connection()

    # ═══════════════════════════════════════════════════════
    #  PARTS — Universal Joint Assembly
    # ═══════════════════════════════════════════════════════

    parts = [
        {
            "id": "PRT-001", "name": "Fork 1",
            "description": "Driving yoke/fork of the universal joint. Connects to the input shaft and transmits torque through the spider.",
            "material": "Steel (AISI 4140)", "category": "structural",
            "parameters": {
                "length": {"value": 3.2, "unit": "mm"},
                "width": {"value": 1.8, "unit": "mm"},
                "depth": {"value": 3.5, "unit": "mm"},
                "bore_diameter": {"value": 1.0, "unit": "mm"},
                "wall_thickness": {"value": 0.6, "unit": "mm"},
            },
            "weight_kg": 0.063, "cost_usd": 8.50,
        },
        {
            "id": "PRT-002", "name": "Fork 2",
            "description": "Driven yoke/fork of the universal joint. Connects to the output shaft and receives torque from the spider.",
            "material": "Steel (AISI 4140)", "category": "structural",
            "parameters": {
                "length": {"value": 3.2, "unit": "mm"},
                "width": {"value": 1.8, "unit": "mm"},
                "depth": {"value": 3.5, "unit": "mm"},
                "bore_diameter": {"value": 1.0, "unit": "mm"},
                "wall_thickness": {"value": 0.6, "unit": "mm"},
            },
            "weight_kg": 0.063, "cost_usd": 8.50,
        },
        {
            "id": "PRT-003", "name": "Shaft",
            "description": "Spider/cross shaft at the center of the universal joint. Four trunnions connect to both forks via pins.",
            "material": "Steel (AISI 4340)", "category": "structural",
            "parameters": {
                "diameter": {"value": 2.2, "unit": "mm"},
                "trunnion_length": {"value": 1.1, "unit": "mm"},
                "spread": {"value": 2.6, "unit": "mm"},
            },
            "weight_kg": 0.022, "cost_usd": 6.20,
        },
        {
            "id": "PRT-004", "name": "Pin",
            "description": "Cross pin (x2) securing the spider shaft to the fork bores. Press-fit or retained by circlips.",
            "material": "Hardened Steel (AISI 52100)", "category": "fastener",
            "parameters": {
                "diameter": {"value": 1.0, "unit": "mm"},
                "length": {"value": 3.6, "unit": "mm"},
            },
            "weight_kg": 0.010, "cost_usd": 2.80,
        },
    ]

    import json
    for p in parts:
        conn.execute("""
            INSERT INTO parts (id, name, description, material, category,
                               parameters, weight_kg, cost_usd, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'demo')
        """, (p["id"], p["name"], p["description"], p["material"], p["category"],
              json.dumps(p["parameters"]), p["weight_kg"], p["cost_usd"]))

    # ═══════════════════════════════════════════════════════
    #  DEPENDENCIES — with coupling factors for quantified impact
    # ═══════════════════════════════════════════════════════

    dependencies = [
        # Fork 1 relationships
        ("PRT-001", "PRT-003", "connects_to", "Fork 1 yoke arms straddle spider trunnions. Bore-to-trunnion fit critical.", 0.95),
        ("PRT-001", "PRT-004", "retained_by", "Pin secures spider shaft in Fork 1 bore. Press-fit tolerance critical.", 0.90),
        ("PRT-001", "PRT-002", "coupled_with", "Fork 1 and Fork 2 operate at angular offset through spider.", 0.80),

        # Fork 2 relationships
        ("PRT-002", "PRT-003", "connects_to", "Fork 2 yoke arms straddle spider trunnions. Bore-to-trunnion fit critical.", 0.95),
        ("PRT-002", "PRT-004", "retained_by", "Pin secures spider shaft in Fork 2 bore. Press-fit tolerance critical.", 0.90),

        # Shaft/Spider relationships
        ("PRT-003", "PRT-004", "mounted_on", "Spider trunnions must align with pin holes in both forks.", 0.85),

        # Pin relationships
        ("PRT-004", "PRT-001", "fits_in", "Pin diameter must match fork bore with interference fit.", 0.90),
        ("PRT-004", "PRT-002", "fits_in", "Pin diameter must match fork bore with interference fit.", 0.90),
    ]

    for d in dependencies:
        conn.execute("""
            INSERT INTO dependencies (part_id, depends_on, relationship_type, description, coupling_factor)
            VALUES (?, ?, ?, ?, ?)
        """, d)

    # ═══════════════════════════════════════════════════════
    #  ASSEMBLY
    # ═══════════════════════════════════════════════════════

    conn.execute("""
        INSERT INTO assemblies (id, name, description)
        VALUES ('ASM-001', 'Universal Joint Assembly', 'Complete universal joint with forks, spider shaft, and pins')
    """)

    assembly_parts = [
        ("ASM-001", "PRT-001", 1),
        ("ASM-001", "PRT-002", 1),
        ("ASM-001", "PRT-003", 1),
        ("ASM-001", "PRT-004", 2),  # 2 pins
    ]

    for ap in assembly_parts:
        conn.execute("INSERT INTO assembly_parts (assembly_id, part_id, quantity) VALUES (?, ?, ?)", ap)

    # ═══════════════════════════════════════════════════════
    #  BOM — with costs, suppliers, make/buy
    # ═══════════════════════════════════════════════════════

    bom_items = [
        ("ASM-001", "PRT-001", 1, 8.50, 8.50, 10, "SteelParts Inc.", "make"),
        ("ASM-001", "PRT-002", 1, 8.50, 8.50, 10, "SteelParts Inc.", "make"),
        ("ASM-001", "PRT-003", 1, 6.20, 6.20, 12, "PrecisionForge Co.", "make"),
        ("ASM-001", "PRT-004", 2, 2.80, 5.60, 5, "FastenerWorld", "buy"),
    ]

    for b in bom_items:
        conn.execute("""
            INSERT INTO bom_items (assembly_id, part_id, quantity, unit_cost, total_cost,
                                    lead_time_days, supplier, make_or_buy)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, b)

    # ═══════════════════════════════════════════════════════
    #  DOCUMENTS
    # ═══════════════════════════════════════════════════════

    documents = [
        ("DOC-001", "Fork 1 Drawing", "drawing", "PRT-001", "A"),
        ("DOC-002", "Fork 1 FEA Report", "fea_report", "PRT-001", "A"),
        ("DOC-003", "Fork 2 Drawing", "drawing", "PRT-002", "A"),
        ("DOC-004", "Shaft/Spider Drawing", "drawing", "PRT-003", "A"),
        ("DOC-005", "Pin Drawing", "drawing", "PRT-004", "A"),
        ("DOC-006", "Universal Joint Assembly Drawing", "assembly_drawing", "PRT-001", "A"),
        ("DOC-007", "Manufacturing Process Sheet", "process_sheet", "PRT-001", "A"),
        ("DOC-008", "Quality Inspection Plan", "inspection_plan", "PRT-001", "A"),
        ("DOC-009", "Universal Joint BOM", "bom", "PRT-001", "A"),
        ("DOC-010", "Stress Analysis Report", "analysis", "PRT-003", "A"),
    ]

    for d in documents:
        conn.execute("INSERT INTO documents (id, title, doc_type, related_part, revision) VALUES (?, ?, ?, ?, ?)", d)

    # ═══════════════════════════════════════════════════════
    #  PDM — Initial Revisions
    # ═══════════════════════════════════════════════════════

    for p in parts:
        conn.execute("""
            INSERT INTO revisions (part_id, revision, description, author, status)
            VALUES (?, 'A', 'Initial release', 'Design Engineer', 'released')
        """, (p["id"],))

    # ═══════════════════════════════════════════════════════
    #  PDM — CAD Metadata (from Fusion 360 snapshot)
    # ═══════════════════════════════════════════════════════

    metadata = [
        ("PRT-001", "A", 80, 210, 1.82, 3.22, 3.52, 0.063, "Steel (AISI 4140)"),
        ("PRT-002", "A", 80, 210, 3.22, 1.82, 3.52, 0.063, "Steel (AISI 4140)"),
        ("PRT-003", "A", 28, 120, 2.22, 2.22, 1.92, 0.022, "Steel (AISI 4340)"),
        ("PRT-004", "A", 13, 40, 1.02, 3.62, 1.02, 0.010, "Hardened Steel (AISI 52100)"),
    ]

    for m in metadata:
        conn.execute("""
            INSERT INTO cad_metadata (part_id, revision, volume_mm3, surface_area_mm2,
                                       bbox_length, bbox_width, bbox_height, mass_kg, material, units)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'mm')
        """, m)

    # ═══════════════════════════════════════════════════════
    #  ERP — Inventory
    # ═══════════════════════════════════════════════════════

    inventory = [
        ("PRT-001", 30, 5, 60, 10, "WH-01-A1"),
        ("PRT-002", 30, 5, 60, 10, "WH-01-A1"),
        ("PRT-003", 40, 10, 80, 15, "WH-01-B1"),
        ("PRT-004", 100, 20, 200, 40, "WH-01-C1"),  # 2x per assembly
    ]

    for inv in inventory:
        conn.execute("""
            INSERT INTO inventory (part_id, stock_quantity, min_stock, max_stock, reorder_point, warehouse_location)
            VALUES (?, ?, ?, ?, ?, ?)
        """, inv)

    # ═══════════════════════════════════════════════════════
    #  ERP — Suppliers
    # ═══════════════════════════════════════════════════════

    suppliers = [
        ("SUP-001", "SteelParts Inc.", "sales@steelparts.com", "Steel forging, CNC machining", 10, 4.5),
        ("SUP-002", "PrecisionForge Co.", "orders@precisionforge.com", "Hardened steel shafts, Cross spiders", 12, 4.7),
        ("SUP-003", "FastenerWorld", "sales@fastenerworld.com", "Pins, Bolts, Circlips, Retainers", 5, 4.3),
    ]

    for s in suppliers:
        conn.execute("""
            INSERT INTO suppliers (id, name, contact, material_types, lead_time_days, rating)
            VALUES (?, ?, ?, ?, ?, ?)
        """, s)

    conn.commit()
    conn.close()
    print(f"  [OK] Populated Universal Joint demo data (4 parts, {len(dependencies)} dependencies, BOM, inventory, suppliers)")


if __name__ == "__main__":
    populate_demo_data()
