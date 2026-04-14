"""
PDM — Product Data Management Module
Handles revision control, BOM management, CAD metadata, and document tracking.
Integrated with the change management pipeline.
"""

import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any

from backend import database as db


class PDMManager:
    """Product Data Management — revisions, BOM, metadata, documents."""

    # ─── Revision Management ─────────────────────────────

    def get_part_revision_history(self, part_name: str) -> Dict:
        """Get complete revision history for a part."""
        part = db.get_part_by_name(part_name)
        if not part:
            return {"error": f"Part '{part_name}' not found"}

        revisions = db.get_revisions(part["id"])
        current_rev = db.get_latest_revision(part["id"])

        return {
            "part_id": part["id"],
            "part_name": part["name"],
            "current_revision": current_rev,
            "revisions": revisions,
            "total_revisions": len(revisions),
        }

    def create_revision(self, part_name: str, change_id: str,
                        description: str, author: str = "system") -> Dict:
        """Create a new revision for a part after a change."""
        part = db.get_part_by_name(part_name)
        if not part:
            return {"error": f"Part '{part_name}' not found"}

        current_rev = db.get_latest_revision(part["id"])
        new_rev = db.increment_revision(current_rev)

        db.add_revision(
            part_id=part["id"],
            revision=new_rev,
            change_id=change_id,
            description=description,
            author=author,
        )

        return {
            "part_id": part["id"],
            "part_name": part["name"],
            "previous_revision": current_rev,
            "new_revision": new_rev,
            "change_id": change_id,
        }

    # ─── BOM Management ──────────────────────────────────

    def get_full_bom(self, assembly_id: str = "ASM-001") -> Dict:
        """Get the complete Bill of Materials with costs."""
        bom_items = db.get_bom(assembly_id)
        total_cost = sum(item.get("total_cost", 0) or 0 for item in bom_items)
        total_weight = sum((item.get("weight_kg", 0) or 0) * (item.get("quantity", 1)) for item in bom_items)

        return {
            "assembly_id": assembly_id,
            "items": bom_items,
            "total_items": len(bom_items),
            "total_cost_usd": round(total_cost, 2),
            "total_weight_kg": round(total_weight, 3),
        }

    def get_bom_impact(self, part_name: str, parameter: str,
                       action: str, value: float) -> Dict:
        """Calculate how a change affects the BOM."""
        part = db.get_part_by_name(part_name)
        if not part:
            return {"affected_items": [], "cost_impact": 0}

        bom_items = db.get_bom()
        affected = []

        for item in bom_items:
            if item.get("part_id") == part.get("id"):
                cost_change = self._estimate_cost_change(
                    item, parameter, action, value
                )
                affected.append({
                    "part_name": item.get("name", part_name),
                    "current_unit_cost": item.get("unit_cost", 0),
                    "estimated_new_cost": round((item.get("unit_cost", 0) or 0) + cost_change, 2),
                    "cost_change": round(cost_change, 2),
                    "quantity": item.get("quantity", 1),
                    "total_impact": round(cost_change * item.get("quantity", 1), 2),
                })

        total_impact = sum(a["total_impact"] for a in affected)
        return {
            "affected_items": affected,
            "total_cost_impact": round(total_impact, 2),
            "bom_update_required": len(affected) > 0,
        }

    def _estimate_cost_change(self, bom_item: Dict, parameter: str,
                              action: str, value: float) -> float:
        """Estimate cost change for a BOM item due to a modification."""
        base_cost = bom_item.get("unit_cost", 0) or 0
        if base_cost == 0:
            return 0

        # Volume-affecting parameters change material cost proportionally
        volume_params = {"wall_thickness", "diameter", "length", "width", "height"}
        if parameter in volume_params:
            # Rough estimate: cost changes ~ proportional to volume change
            if action == "REDUCE":
                return -base_cost * (value / 50)  # ~2% per mm reduced
            elif action == "INCREASE":
                return base_cost * (value / 50)
            elif action == "CHANGE":
                return base_cost * 0.05  # 5% re-tooling cost

        # Material changes
        if parameter == "material":
            return base_cost * 0.15  # 15% material cost premium

        return 0

    # ─── CAD Metadata ────────────────────────────────────

    def save_part_metadata(self, part_name: str, cad_snapshot: Dict,
                           revision: str = "A") -> Dict:
        """Save CAD geometry metadata from a Fusion 360 snapshot."""
        part = db.get_part_by_name(part_name)
        if not part:
            return {"error": f"Part '{part_name}' not found"}

        bbox = cad_snapshot.get("bounding_box", {})

        # Fusion internal units are cm, convert to mm
        vol_cm3 = cad_snapshot.get("total_volume", 0)
        area_cm2 = cad_snapshot.get("total_area", 0)

        metadata = {
            "revision": revision,
            "volume_mm3": round(vol_cm3 * 1000, 2),       # cm³ → mm³
            "surface_area_mm2": round(area_cm2 * 100, 2),  # cm² → mm²
            "bbox_length": round(bbox.get("length", 0) * 10, 2),  # cm → mm
            "bbox_width": round(bbox.get("width", 0) * 10, 2),
            "bbox_height": round(bbox.get("height", 0) * 10, 2),
            "mass_kg": part.get("weight_kg"),
            "material": part.get("material"),
            "units": "mm",
            "stl_file": f"{part_name.replace(' ', '_')}_original.stl",
        }

        db.save_cad_metadata(part["id"], metadata)
        return {"success": True, "metadata": metadata}

    def get_part_metadata(self, part_name: str) -> Optional[Dict]:
        """Get latest CAD metadata for a part."""
        part = db.get_part_by_name(part_name)
        if not part:
            return None
        return db.get_cad_metadata(part["id"])

    # ─── Document Tracking ───────────────────────────────

    def get_part_documents(self, part_name: str) -> List[Dict]:
        """Get all documents linked to a part."""
        return db.get_documents_for_part(part_name)

    def get_part_full_profile(self, part_name: str) -> Dict:
        """Get complete PDM profile: part info + revisions + metadata + docs."""
        part = db.get_part_by_name(part_name)
        if not part:
            return {"error": f"Part '{part_name}' not found"}

        revisions = db.get_revisions(part["id"])
        metadata = db.get_cad_metadata(part["id"])
        documents = db.get_documents_for_part(part_name)
        deps = db.get_dependencies(part_name)

        return {
            "part": part,
            "current_revision": db.get_latest_revision(part["id"]),
            "revisions": revisions,
            "cad_metadata": metadata,
            "documents": documents,
            "dependencies": deps,
            "dependency_count": len(deps),
        }


# Global instance
pdm_manager = PDMManager()
