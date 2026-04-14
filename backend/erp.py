"""
ERP — Enterprise Resource Planning Module
Handles manufacturing orders, procurement, inventory, cost tracking,
and change order workflow management.
Integrated with the change management and PDM pipeline.
"""

import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from backend import database as db


class ERPManager:
    """Enterprise Resource Planning — orders, costs, inventory, workflow."""

    # ─── Manufacturing Orders ────────────────────────────

    def create_work_order_from_change(self, change_id: str, target_part: str,
                                       classification: str, risk_level: str,
                                       effort_hours: float, affected_parts: List[Dict]) -> Dict:
        """Auto-create manufacturing orders when a change is analyzed."""
        part = db.get_part_by_name(target_part)
        if not part:
            return {"orders": [], "error": f"Part '{target_part}' not found"}

        orders = []

        # Main modification order
        priority = "urgent" if risk_level == "HIGH" else ("high" if classification == "MAJOR" else "normal")
        main_cost = self._estimate_manufacturing_cost(part, effort_hours, classification)

        due_days = 7 if priority == "normal" else (3 if priority == "high" else 1)
        due_date = (datetime.now() + timedelta(days=due_days)).strftime("%Y-%m-%d")

        main_order = {
            "id": f"MO-{uuid.uuid4().hex[:6].upper()}",
            "change_id": change_id,
            "part_id": part["id"],
            "order_type": "modification",
            "status": "draft",
            "priority": priority,
            "quantity": 1,
            "estimated_cost": round(main_cost, 2),
            "estimated_hours": effort_hours,
            "assigned_to": "Engineering Team",
            "notes": f"Change request: {change_id}. Modify {target_part}.",
            "due_date": due_date,
        }
        db.create_manufacturing_order(main_order)
        orders.append(main_order)

        # Quality inspection order for MAJOR changes
        if classification == "MAJOR":
            qa_order = {
                "id": f"QA-{uuid.uuid4().hex[:6].upper()}",
                "change_id": change_id,
                "part_id": part["id"],
                "order_type": "quality_inspection",
                "status": "pending",
                "priority": priority,
                "quantity": 1,
                "estimated_cost": round(main_cost * 0.15, 2),
                "estimated_hours": round(effort_hours * 0.2, 1),
                "assigned_to": "Quality Assurance",
                "notes": f"Inspection for {change_id}. Verify dimensional accuracy post-modification.",
                "due_date": (datetime.now() + timedelta(days=due_days + 2)).strftime("%Y-%m-%d"),
            }
            db.create_manufacturing_order(qa_order)
            orders.append(qa_order)

        # Re-test orders for affected parts with HIGH severity
        for ap in affected_parts:
            if ap.get("severity") == "HIGH":
                test_order = {
                    "id": f"RT-{uuid.uuid4().hex[:6].upper()}",
                    "change_id": change_id,
                    "part_id": ap.get("part_id"),
                    "order_type": "retest",
                    "status": "pending",
                    "priority": "normal",
                    "quantity": 1,
                    "estimated_cost": round(main_cost * 0.05, 2),
                    "estimated_hours": 2.0,
                    "assigned_to": "Test Lab",
                    "notes": f"Retest {ap.get('part_name')} due to change in {target_part} ({ap.get('relationship')}).",
                    "due_date": (datetime.now() + timedelta(days=due_days + 5)).strftime("%Y-%m-%d"),
                }
                db.create_manufacturing_order(test_order)
                orders.append(test_order)

        return {
            "orders": orders,
            "total_orders": len(orders),
            "total_estimated_cost": round(sum(o["estimated_cost"] for o in orders), 2),
            "total_estimated_hours": round(sum(o["estimated_hours"] for o in orders), 1),
        }

    def _estimate_manufacturing_cost(self, part: Dict, effort_hours: float,
                                      classification: str) -> float:
        """Estimate manufacturing cost based on part and effort."""
        labor_rate = 75  # $/hour
        base_cost = effort_hours * labor_rate

        # Material cost multiplier
        material = (part.get("material") or "").lower()
        if "steel" in material or "stainless" in material:
            base_cost *= 1.3
        elif "aluminum" in material or "aluminium" in material:
            base_cost *= 1.1
        elif "titanium" in material:
            base_cost *= 2.0
        elif "plastic" in material or "nylon" in material:
            base_cost *= 0.7

        # Complexity multiplier
        if classification == "MAJOR":
            base_cost *= 1.4

        return base_cost

    def get_all_orders(self, status: str = None) -> Dict:
        """Get all manufacturing orders."""
        orders = db.get_manufacturing_orders(status)
        return {
            "orders": orders,
            "total": len(orders),
            "by_status": self._count_by_field(orders, "status"),
            "by_type": self._count_by_field(orders, "order_type"),
        }

    def update_order_status(self, order_id: str, new_status: str) -> Dict:
        db.update_order_status(order_id, new_status)
        return {"success": True, "order_id": order_id, "new_status": new_status}

    # ─── Change Order Workflow ───────────────────────────

    def create_change_order(self, change_id: str, title: str, description: str,
                            target_part: str, classification: str, risk_level: str,
                            effort_hours: float, affected_count: int,
                            total_cost: float = 0) -> Dict:
        """Create a formal change order for the workflow."""
        priority = "critical" if risk_level == "HIGH" else (
            "high" if classification == "MAJOR" else "normal"
        )

        # Resolve part name to ID for FK constraint
        part = db.get_part_by_name(target_part)
        target_part_id = part["id"] if part else None

        co_id = f"CO-{uuid.uuid4().hex[:6].upper()}"
        data = {
            "id": co_id,
            "change_id": change_id,
            "title": title,
            "description": description,
            "status": "draft",
            "priority": priority,
            "target_part": target_part_id,  # FK to parts(id)
            "target_part_name": target_part,  # Display name
            "classification": classification,
            "risk_level": risk_level,
            "total_cost": total_cost,
            "total_effort_hours": effort_hours,
            "affected_count": affected_count,
        }
        db.create_change_order(data)
        return data

    def get_change_orders(self, status: str = None) -> Dict:
        orders = db.get_change_orders(status)
        return {
            "orders": orders,
            "total": len(orders),
            "by_status": self._count_by_field(orders, "status"),
        }

    def advance_workflow(self, change_id: str, action: str,
                         approved_by: str = None) -> Dict:
        """Advance a change order through the workflow."""
        workflow = {
            "submit":  "review",
            "approve": "approved",
            "reject":  "rejected",
            "start":   "in_progress",
            "complete": "completed",
        }
        new_status = workflow.get(action)
        if not new_status:
            return {"error": f"Unknown action: {action}. Use: {list(workflow.keys())}"}

        db.update_change_order_status(change_id, new_status, approved_by)
        return {
            "success": True,
            "change_id": change_id,
            "new_status": new_status,
            "action": action,
        }

    # ─── Inventory Management ────────────────────────────

    def get_inventory_status(self) -> Dict:
        """Get full inventory status."""
        inventory = db.get_inventory()
        low_stock = [i for i in inventory if (i.get("stock_quantity", 0) or 0) <= (i.get("reorder_point", 10) or 10)]

        return {
            "items": inventory,
            "total_items": len(inventory),
            "low_stock_count": len(low_stock),
            "low_stock_items": low_stock,
        }

    def check_inventory_impact(self, part_name: str, change_type: str) -> Dict:
        """Check if a change makes current inventory obsolete."""
        part = db.get_part_by_name(part_name)
        if not part:
            return {"impact": "none"}

        inv_list = db.get_inventory(part["id"])
        if not inv_list:
            return {"impact": "none", "message": "No inventory tracked for this part"}

        inv = inv_list[0]
        stock = inv.get("stock_quantity", 0) or 0

        if change_type == "MAJOR" and stock > 0:
            scrap_cost = stock * (part.get("cost_usd", 0) or 0)
            return {
                "impact": "high",
                "current_stock": stock,
                "scrap_quantity": stock,
                "scrap_cost": round(scrap_cost, 2),
                "message": f"MAJOR change requires scrapping {stock} units of {part_name} in inventory.",
                "recommendation": "Deplete current stock before implementing change, or rework existing inventory.",
            }
        elif stock > 0:
            return {
                "impact": "low",
                "current_stock": stock,
                "message": f"MINOR change — {stock} units in stock may need rework or can be used as-is.",
            }

        return {"impact": "none", "current_stock": 0}

    # ─── Cost Summary ────────────────────────────────────

    def get_cost_summary(self, change_id: str = None) -> Dict:
        """Get a cost breakdown for the change or overall."""
        orders = db.get_manufacturing_orders()
        if change_id:
            orders = [o for o in orders if o.get("change_id") == change_id]

        total_cost = sum(o.get("estimated_cost", 0) or 0 for o in orders)
        total_hours = sum(o.get("estimated_hours", 0) or 0 for o in orders)
        bom_cost = db.get_bom_total_cost()

        return {
            "manufacturing_cost": round(total_cost, 2),
            "total_labor_hours": round(total_hours, 1),
            "bom_total_cost": round(bom_cost, 2),
            "labor_rate": 75,
            "orders_count": len(orders),
            "change_id": change_id,
        }

    # ─── Helpers ─────────────────────────────────────────

    def _count_by_field(self, items: List[Dict], field: str) -> Dict:
        counts = {}
        for item in items:
            val = item.get(field, "unknown")
            counts[val] = counts.get(val, 0) + 1
        return counts


# Global instance
erp_manager = ERPManager()
