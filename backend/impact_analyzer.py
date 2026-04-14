"""
Impact Analysis Engine — v3.0
Quantified severity scoring, cascading dependency traversal,
context-aware automated recommendations, and PDM/ERP integration.
"""

import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional

from backend import database as db
from backend.models import (
    ParsedInstruction, ImpactAnalysisResult, AffectedPart,
    BOMImpact, DocumentImpact, ChangeClassification, RiskLevel
)


# ─── Severity & Coupling Constants ────────────────────────

RELATIONSHIP_SEVERITY = {
    # Universal joint relationships
    "connects_to": 95,     # Fork-to-spider trunnion — critical interface
    "retained_by": 90,     # Pin retention — structural integrity
    "coupled_with": 80,    # Fork-to-fork angular coupling
    "fits_in":     90,     # Press-fit / interference fit — tolerance critical
    # General relationships
    "meshes_with": 95,     # Gear teeth mesh — any geometry change affects mesh
    "mates_with":  90,     # Direct mating surfaces — tight tolerance
    "mounted_on":  80,     # Structural mount — load path affected
    "housed_in":   80,     # Enclosed component — clearance critical
    "drives":      85,     # Power transmission — torque/speed affected
    "driven_by":   85,
    "fastened_to": 60,     # Bolt pattern — hole alignment
    "seals":       65,     # Seal interface — leak risk on geometry change
    "supports":    70,     # Structural support — load redistribution
    "aligns_with": 55,     # Alignment reference — positional tolerance
    "lubricates":  40,     # Lubrication path — low direct impact
    "related_to":  30,     # Generic relationship
}

PARAMETER_CRITICALITY = {
    "wall_thickness": 0.95, "diameter": 0.90, "teeth": 0.95,
    "module": 0.90, "face_width": 0.80, "height": 0.70,
    "length": 0.70, "width": 0.70, "thickness": 0.85,
    "bore_diameter": 0.90, "pitch_diameter": 0.95,
    "clearance": 0.85, "tolerance": 0.90, "material": 1.0,
    "pressure_angle": 0.95, "helix_angle": 0.85,
    "fillet_radius": 0.40, "chamfer": 0.30,
    # Universal joint parameters
    "pin_diameter": 0.95, "pin_length": 0.85,
    "fork_length": 0.80, "fork_width": 0.80, "fork_depth": 0.80,
    "shaft_diameter": 0.90, "trunnion_length": 0.85, "spread": 0.80,
    "bore_diameter": 0.90,
}

# Which parameters affect which aspects of connected parts
PARAMETER_IMPACT_MAP = {
    "wall_thickness": {
        "meshes_with": "Mesh clearance and gear contact pattern may shift. Tooth root stress redistribution expected.",
        "mates_with": "Mating surface interface geometry changes. Check fit tolerance.",
        "housed_in": "Housing cavity clearance changes. Verify component does not interfere.",
        "seals": "Seal groove depth may change. Verify O-ring compression ratio.",
        "supports": "Structural rigidity change. Load capacity affected.",
    },
    "diameter": {
        "meshes_with": "Pitch circle diameter change affects gear ratio and mesh alignment.",
        "mates_with": "Shaft-bore fit tolerance changes. Check interference/clearance fit.",
        "housed_in": "Bore clearance or interference fit affected.",
        "drives": "Torque transmission capacity changes with diameter.",
    },
    "teeth": {
        "meshes_with": "Gear ratio changes. Module must be recalculated for proper mesh.",
        "drives": "Speed ratio and torque multiplication affected.",
        "driven_by": "Input/output speed ratio changes.",
    },
    "face_width": {
        "meshes_with": "Contact area changes. Load distribution across face width affected.",
        "housed_in": "Axial length change may affect housing clearance.",
    },
    "height": {
        "housed_in": "Component height change affects housing clearance.",
        "mates_with": "Mating surface alignment may shift vertically.",
        "supports": "Center of gravity shift. Support load redistribution.",
    },
    "material": {
        "meshes_with": "Material hardness difference affects wear rate and contact stress.",
        "mates_with": "Galvanic corrosion risk if dissimilar metals. Thermal expansion mismatch.",
        "seals": "Surface finish and chemical compatibility with seal material.",
        "connects_to": "Material change affects bearing surface wear and fatigue life.",
        "fits_in": "Different thermal expansion coefficients affect press-fit retention.",
    },
    # Universal joint specific parameters
    "pin_diameter": {
        "connects_to": "Trunnion-to-pin fit changes. Check interference/clearance fit tolerance.",
        "retained_by": "Pin retention force changes with diameter. Verify press-fit specification.",
        "fits_in": "Pin-to-bore fit tolerance affected. May require bore re-machining.",
        "coupled_with": "Torque transmission capacity changes with pin cross-section.",
    },
    "pin_length": {
        "connects_to": "Pin protrusion through fork bore changes. Check circlip groove position.",
        "retained_by": "Engagement length in fork bore affected. Verify structural retention.",
        "fits_in": "Pin may protrude or not fully seat in fork bore.",
    },
    "fork_length": {
        "connects_to": "Fork arm length change affects spider engagement depth.",
        "coupled_with": "Angular velocity range may change with fork geometry.",
        "retained_by": "Pin hole position relative to fork arm may shift.",
    },
    "fork_width": {
        "connects_to": "Fork yoke opening width affects spider trunnion clearance.",
        "retained_by": "Pin bore spacing changes. Verify alignment with spider.",
    },
    "shaft_diameter": {
        "connects_to": "Spider trunnion diameter affects fork bore clearance.",
        "retained_by": "Pin-to-trunnion relationship changes. Check assembly sequence.",
        "fits_in": "Trunnion-to-bearing or trunnion-to-bore fit affected.",
        "coupled_with": "Cross-shaft strength changes affect torque capacity.",
    },
    "bore_diameter": {
        "fits_in": "Bore-to-pin interference fit directly affected. Critical tolerance.",
        "retained_by": "Pin retention force proportional to bore-pin interference.",
        "connects_to": "Fork-to-spider interface clearance changes.",
    },
}


class ImpactAnalyzer:
    """Analyzes the impact of engineering changes with quantified severity."""

    def analyze(self, parsed: ParsedInstruction, cad_result: Optional[Dict] = None) -> ImpactAnalysisResult:
        change_id = f"ECR-{uuid.uuid4().hex[:8].upper()}"
        target_part = parsed.target_part or "Unknown"

        # 1. Find affected parts with quantified severity
        affected_parts = self._find_affected_parts(
            target_part, parsed.parameter, parsed.action, parsed.value
        )

        # 2. Classify the change
        classification = self._classify_change(parsed, affected_parts)

        # 3. Assess risk
        risk_level = self._assess_risk(parsed, affected_parts, classification)

        # 4. Estimate effort
        effort_hours = self._estimate_effort(parsed, affected_parts, classification)

        # 5. Check BOM impact
        bom_impacts = self._check_bom_impact(parsed, cad_result)

        # 6. Check document impact
        doc_impacts = self._check_document_impact(target_part, classification)

        # 7. Generate context-aware recommendations
        recommendations = self._generate_recommendations(
            parsed, affected_parts, classification, risk_level, cad_result
        )

        # 8. Metrics
        before_metrics = cad_result.get("before", {}) if cad_result else {}
        after_metrics = cad_result.get("after", {}) if cad_result else {}

        result = ImpactAnalysisResult(
            change_id=change_id,
            target_part=target_part,
            target_part_id=self._get_part_id(target_part),
            parsed_instruction=parsed,
            affected_parts=affected_parts,
            total_affected_count=len(affected_parts),
            classification=classification,
            risk_level=risk_level,
            effort_hours=effort_hours,
            bom_impacts=bom_impacts,
            document_impacts=doc_impacts,
            before_metrics=before_metrics,
            after_metrics=after_metrics,
            original_stl_path=cad_result.get("original_stl") if cad_result else None,
            modified_stl_path=cad_result.get("modified_stl") if cad_result else None,
            modified_step_path=cad_result.get("modified_step") if cad_result else None,
            timestamp=datetime.now().isoformat(),
            recommendations=recommendations,
        )

        self._save_to_history(result)
        return result

    # ─── Dependency Analysis (Quantified) ─────────────────

    def _find_affected_parts(self, target_part: str, parameter: str,
                             action: str, value: float) -> List[AffectedPart]:
        """Find all affected parts with quantified severity scores."""
        deps = db.get_dependencies(target_part)
        target_part_data = db.get_part_by_name(target_part)

        affected = []
        seen = set()

        for dep in deps:
            name = dep.get("part_name", "Unknown")
            if name in seen:
                continue
            seen.add(name)

            relationship = dep.get("relationship", "related_to")
            coupling = dep.get("coupling_factor", 0.5)

            # Calculate severity score (0-100)
            severity_score = self._calculate_severity_score(
                relationship, parameter, action, value, coupling,
                target_part_data
            )

            # Generate specific impact description
            impact_desc = self._generate_impact_description(
                target_part, name, parameter, action, value, relationship
            )

            severity_label = self._score_to_severity(severity_score)

            affected.append(AffectedPart(
                part_id=dep.get("part_id", ""),
                part_name=name,
                relationship=relationship,
                impact_description=impact_desc,
                severity=severity_label,
                severity_score=severity_score,
            ))

        # Sort by severity score descending
        affected.sort(key=lambda x: x.severity_score, reverse=True)

        # Cascading: check if affected parts have their own dependents
        cascade_parts = []
        for ap in affected:
            cascade_deps = db.get_dependencies(ap.part_name)
            for cd in cascade_deps:
                cn = cd.get("part_name", "")
                if cn not in seen and cn.lower() != target_part.lower():
                    seen.add(cn)
                    # Cascade severity = parent severity * coupling factor * 0.6
                    cascade_score = int(ap.severity_score * (cd.get("coupling_factor", 0.3)) * 0.6)
                    if cascade_score >= 10:
                        cascade_parts.append(AffectedPart(
                            part_id=cd.get("part_id", ""),
                            part_name=cn,
                            relationship=f"cascade:{cd.get('relationship', 'related_to')}",
                            impact_description=f"Indirectly affected via {ap.part_name}. {cd.get('relationship', '')} relationship.",
                            severity=self._score_to_severity(cascade_score),
                            severity_score=cascade_score,
                        ))

        affected.extend(cascade_parts)
        affected.sort(key=lambda x: x.severity_score, reverse=True)
        return affected

    def _calculate_severity_score(self, relationship: str, parameter: str,
                                   action: str, value: float, coupling: float,
                                   target_part: Dict) -> int:
        """Calculate a 0-100 severity score."""
        # Base: relationship type severity
        base = RELATIONSHIP_SEVERITY.get(relationship, 30)

        # Parameter criticality multiplier (0-1)
        param_crit = PARAMETER_CRITICALITY.get(parameter or "", 0.5)

        # Action severity multiplier
        action_mult = {
            "REDUCE": 1.2, "REMOVE": 1.5, "INCREASE": 1.0,
            "CHANGE": 0.9, "REPLACE": 1.3, "SCALE": 1.1,
            "ADD": 0.8, "FILLET": 0.4, "CHAMFER": 0.4,
        }.get(action or "CHANGE", 0.8)

        # Magnitude factor: how big is the change relative to typical values
        magnitude_factor = 1.0
        if value and parameter:
            # Get the part's current parameter value for reference
            part_params = target_part.get("parameters", {}) if target_part else {}
            current_val = None
            if parameter in part_params:
                cv = part_params[parameter]
                if isinstance(cv, dict):
                    current_val = cv.get("value")
                elif isinstance(cv, (int, float)):
                    current_val = cv

            if current_val and current_val > 0:
                pct_change = value / current_val
                if pct_change > 0.30:
                    magnitude_factor = 1.4
                elif pct_change > 0.15:
                    magnitude_factor = 1.2
                elif pct_change < 0.05:
                    magnitude_factor = 0.7

        score = base * param_crit * action_mult * coupling * magnitude_factor
        return min(100, max(0, int(score)))

    def _score_to_severity(self, score: int) -> str:
        if score >= 70:
            return "HIGH"
        elif score >= 35:
            return "MEDIUM"
        return "LOW"

    def _generate_impact_description(self, target: str, affected: str,
                                      parameter: str, action: str,
                                      value: float, relationship: str) -> str:
        """Generate a specific, contextual impact description."""
        # Check parameter-specific impact map
        param_impacts = PARAMETER_IMPACT_MAP.get(parameter or "", {})
        specific = param_impacts.get(relationship)
        if specific:
            return specific

        # Generate based on action + relationship
        action_text = {
            "REDUCE": "Reducing",
            "INCREASE": "Increasing",
            "CHANGE": "Changing",
            "REMOVE": "Removing",
            "REPLACE": "Replacing",
        }.get(action, "Modifying")

        val_text = f" by {value} mm" if value else ""

        templates = {
            "meshes_with": f"{action_text} {parameter}{val_text} on {target} changes the mesh interface with {affected}. Verify gear mesh alignment and backlash.",
            "mates_with": f"{action_text} {parameter}{val_text} on {target} alters the mating interface with {affected}. Check dimensional fit and tolerance stack-up.",
            "housed_in": f"{action_text} {parameter}{val_text} on {target} changes clearance within {affected}. Verify no interference.",
            "seals": f"{action_text} {parameter}{val_text} on {target} may affect seal compression on {affected}. Check leak integrity.",
            "supports": f"{action_text} {parameter}{val_text} on {target} changes the load path to {affected}. Verify structural adequacy.",
            "fastened_to": f"{action_text} {parameter}{val_text} on {target} may affect bolt pattern alignment with {affected}.",
            "drives": f"{action_text} {parameter}{val_text} on {target} affects power transmission to {affected}.",
        }

        return templates.get(
            relationship,
            f"{action_text} {parameter or 'geometry'}{val_text} on {target} affects {affected} ({relationship})."
        )

    # ─── Classification ──────────────────────────────────

    def _classify_change(self, parsed: ParsedInstruction,
                         affected: List[AffectedPart]) -> ChangeClassification:
        score = 0

        major_actions = {"REDUCE", "INCREASE", "REMOVE", "REPLACE", "SCALE"}
        if parsed.action in major_actions:
            score += 2

        critical_params = {"wall_thickness", "diameter", "teeth", "material", "bore_diameter", "pitch_diameter"}
        if parsed.parameter in critical_params:
            score += 2

        # High-severity affected count
        high_count = sum(1 for a in affected if a.severity == "HIGH")
        if high_count >= 3:
            score += 3
        elif high_count >= 1:
            score += 1
        if len(affected) >= 4:
            score += 1

        # Value magnitude
        if parsed.value and parsed.value > 5:
            score += 1

        return ChangeClassification.MAJOR if score >= 4 else ChangeClassification.MINOR

    # ─── Risk Assessment ─────────────────────────────────

    def _assess_risk(self, parsed: ParsedInstruction,
                     affected: List[AffectedPart],
                     classification: ChangeClassification) -> RiskLevel:
        score = 0

        if parsed.action in ("REDUCE", "REMOVE"):
            score += 3
        if parsed.parameter in ("wall_thickness", "material"):
            score += 3
        if parsed.parameter in ("teeth", "diameter", "bore_diameter"):
            score += 2

        # Weighted by severity scores
        avg_severity = (sum(a.severity_score for a in affected) / max(len(affected), 1))
        if avg_severity >= 60:
            score += 4
        elif avg_severity >= 35:
            score += 2

        score += min(len(affected), 5)

        if classification == ChangeClassification.MAJOR:
            score += 2

        if parsed.value and parsed.value > 10:
            score += 1

        if score >= 10:
            return RiskLevel.HIGH
        elif score >= 5:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    # ─── Effort Estimation ───────────────────────────────

    def _estimate_effort(self, parsed: ParsedInstruction,
                         affected: List[AffectedPart],
                         classification: ChangeClassification) -> float:
        base_hours = {
            "REDUCE": 8, "INCREASE": 8, "CHANGE": 6,
            "ADD": 16, "REMOVE": 12, "REPLACE": 10,
            "SCALE": 4, "FILLET": 3, "CHAMFER": 3,
        }
        hours = base_hours.get(parsed.action, 8)

        # Weighted by severity
        for a in affected:
            if a.severity == "HIGH":
                hours += 4
            elif a.severity == "MEDIUM":
                hours += 2
            else:
                hours += 1

        if classification == ChangeClassification.MAJOR:
            hours *= 1.5

        if parsed.parameter == "material":
            hours += 8

        return round(hours, 1)

    # ─── BOM Impact ──────────────────────────────────────

    def _check_bom_impact(self, parsed: ParsedInstruction,
                          cad_result: Optional[Dict]) -> List[BOMImpact]:
        impacts = []

        dimensional_params = {"wall_thickness", "diameter", "length", "width", "height", "face_width", "thickness"}
        if parsed.parameter in dimensional_params:
            change_desc = ""
            if cad_result and "before" in cad_result and "after" in cad_result:
                before_vol = cad_result["before"].get("total_volume", 0) or cad_result["before"].get("volume", 0)
                after_vol = cad_result["after"].get("total_volume", 0) or cad_result["after"].get("volume", 0)
                if before_vol and before_vol > 0 and after_vol:
                    vol_change_pct = ((after_vol - before_vol) / before_vol) * 100
                    change_desc = f"Volume change: {vol_change_pct:+.1f}%"

            impacts.append(BOMImpact(
                impact_type="weight_change",
                description="Part weight changes due to modified geometry. BOM weight column requires update.",
                estimated_change=change_desc or "Recalculation needed after Fusion 360 update",
            ))
            impacts.append(BOMImpact(
                impact_type="cost_change",
                description="Manufacturing cost affected — material usage and machining time changed.",
                estimated_change="Requote from manufacturing required",
            ))

        if parsed.parameter == "material":
            impacts.append(BOMImpact(
                impact_type="material_change",
                description=f"Material changed to {parsed.material_value or 'new material'}. Supplier qualification needed.",
                estimated_change="Material cost and lead time will change",
            ))
            impacts.append(BOMImpact(
                impact_type="supplier_change",
                description="New material supplier may be required. Qualification lead time: 2-6 weeks.",
                estimated_change="Procurement cycle restart required",
            ))

        if parsed.action in ("ADD", "REMOVE"):
            impacts.append(BOMImpact(
                impact_type="process_change",
                description="New manufacturing operations may be required. Update process sheets.",
                estimated_change="Additional machining/processing steps",
            ))

        return impacts

    # ─── Document Impact ─────────────────────────────────

    def _check_document_impact(self, target_part: str,
                               classification: ChangeClassification) -> List[DocumentImpact]:
        impacts = []
        docs = db.get_documents_for_part(target_part)

        for doc in docs:
            action = "Update required" if classification == ChangeClassification.MAJOR else "Review required"
            impacts.append(DocumentImpact(
                doc_type=doc.get("doc_type", "document"),
                doc_title=doc.get("title", "Unknown Document"),
                action_required=action,
            ))

        if not impacts:
            impacts.append(DocumentImpact(
                doc_type="drawing", doc_title=f"{target_part} Engineering Drawing",
                action_required="Update required",
            ))
            if classification == ChangeClassification.MAJOR:
                impacts.extend([
                    DocumentImpact(doc_type="fea_report", doc_title=f"{target_part} FEA Report",
                                   action_required="Re-analysis required"),
                    DocumentImpact(doc_type="process_sheet", doc_title="Manufacturing Process Sheet",
                                   action_required="Update required"),
                    DocumentImpact(doc_type="inspection_plan", doc_title="Quality Inspection Plan",
                                   action_required="Update required"),
                ])
            impacts.append(DocumentImpact(
                doc_type="bom", doc_title="Bill of Materials",
                action_required="Update required",
            ))

        return impacts

    # ─── Context-aware Recommendations ───────────────────

    def _generate_recommendations(self, parsed: ParsedInstruction,
                                   affected: List[AffectedPart],
                                   classification: ChangeClassification,
                                   risk: RiskLevel,
                                   cad_result: Optional[Dict]) -> List[str]:
        recs = []

        # ── Risk-based ──
        if risk == RiskLevel.HIGH:
            recs.append("⚠️ HIGH RISK — Perform Finite Element Analysis (FEA) before implementation to verify structural integrity.")
            recs.append("Schedule a Design Review Board (DRB) meeting before proceeding.")

        # ── Parameter-specific ──
        if parsed.parameter == "wall_thickness":
            if parsed.action == "REDUCE":
                recs.append("Verify minimum wall thickness per material spec (e.g., ASME/ISO standards).")
                recs.append("Check safety factor after thickness reduction. Target: SF ≥ 2.0 for static loads.")
                recs.append("Run stress analysis on reduced cross-section — buckling risk increases with thinner walls.")
            elif parsed.action == "INCREASE":
                recs.append("Verify that increased wall thickness does not cause interference with mating parts.")

        if parsed.parameter in ("diameter", "bore_diameter"):
            recs.append("Verify all mating bore/shaft fits remain within tolerance (H7/g6 or H7/p6 as applicable).")
            recs.append("Check bearing selection — inner/outer race compatibility.")

        if parsed.parameter in ("teeth", "module", "pitch_diameter"):
            recs.append("Recalculate gear ratio and verify it meets design requirements.")
            recs.append("Run gear mesh analysis (contact pattern, backlash, root stress).")

        if parsed.parameter == "face_width":
            recs.append("Verify load distribution uniformity across new face width.")
            recs.append("Check axial clearance in housing for modified width.")

        if parsed.parameter == "material":
            recs.append("Verify new material meets thermal, mechanical, and corrosion requirements.")
            recs.append("Check galvanic compatibility with mating stainless steel components.")
            recs.append("Confirm material availability and lead time with procurement.")

        # ── Scope-based ──
        high_severity_parts = [a for a in affected if a.severity == "HIGH"]
        if len(high_severity_parts) >= 3:
            names = ", ".join(a.part_name for a in high_severity_parts[:3])
            recs.append(f"Critical: {len(high_severity_parts)} high-severity components affected ({names}). Consider phased rollout.")

        if len(affected) > 0:
            recs.append(f"Notify owners of {len(affected)} affected components. Coordinate change implementation schedule.")

        # ── Magnitude-based ──
        if parsed.value and parsed.value > 0:
            part = db.get_part_by_name(parsed.target_part)
            if part:
                params = part.get("parameters", {})
                if parsed.parameter and parsed.parameter in params:
                    pv = params[parsed.parameter]
                    orig = pv.get("value") if isinstance(pv, dict) else pv
                    if orig and orig > 0:
                        pct = (parsed.value / orig) * 100
                        if pct > 30:
                            recs.append(f"Change magnitude is {pct:.0f}% of original — prototype testing strongly recommended.")
                        elif pct > 15:
                            recs.append(f"Change is {pct:.0f}% of original value — verify within acceptable tolerance range.")

        # ── Classification-based ──
        if classification == ChangeClassification.MAJOR:
            recs.append("Increment revision level (e.g., Rev A -> Rev B). Update PDM system.")
            recs.append("Notify Quality team — inspection plan update and first article inspection (FAI) required.")
            recs.append("Update manufacturing process sheets and CNC programs.")
            recs.append("File Engineering Change Notice (ECN) in company PLM system.")

        # ── ERP integration recommendations ──
        if classification == ChangeClassification.MAJOR:
            recs.append("ERP: Check current inventory — MAJOR change may require scrapping existing stock.")
            recs.append("ERP: Create manufacturing order for modified parts. Update production schedule.")

        # ── Always-add general ──
        recs.append("Update Bill of Materials (BOM) with new specifications.")
        recs.append("Document change in engineering change log and PDM revision history.")

        return recs

    # ─── Helpers ─────────────────────────────────────────

    def _get_part_id(self, part_name: str) -> Optional[str]:
        part = db.get_part_by_name(part_name)
        return part["id"] if part else None

    def _save_to_history(self, result: ImpactAnalysisResult):
        try:
            db.save_change_history({
                "change_id": result.change_id,
                "change_request": result.parsed_instruction.original_text,
                "parsed_instruction": result.parsed_instruction.model_dump(),
                "target_part": result.target_part,
                "modification_type": result.parsed_instruction.action,
                "classification": result.classification.value,
                "risk_level": result.risk_level.value,
                "impact_summary": {
                    "affected_count": result.total_affected_count,
                    "risk_level": result.risk_level.value,
                    "effort_hours": result.effort_hours,
                },
                "original_file": result.original_stl_path,
                "modified_file": result.modified_step_path,
            })
        except Exception as e:
            print(f"⚠️  Failed to save change history: {e}")
