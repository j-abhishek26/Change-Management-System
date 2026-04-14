"""
CAD Engine — Fusion 360 Bridge Client
Communicates with the FusionBridge add-in running inside Fusion 360
via HTTP on localhost:5001.

Falls back to simulation mode when Fusion 360 is not connected.
"""

import json
import time
import traceback
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# ─── Configuration ────────────────────────────────────────

FUSION_BRIDGE_URL = "http://127.0.0.1:5001"
BRIDGE_TIMEOUT = 120  # seconds — computeAll() can take 30-60s on complex models

BASE_DIR = Path(__file__).parent.parent
OUTPUTS_DIR = BASE_DIR / "outputs"
UPLOADS_DIR = BASE_DIR / "uploads"
OUTPUTS_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)


# ═══════════════════════════════════════════════════════════
#  FUSION BRIDGE CLIENT
# ═══════════════════════════════════════════════════════════

class FusionBridge:
    """Client that talks to the FusionBridge add-in in Fusion 360."""

    def __init__(self):
        self.base_url = FUSION_BRIDGE_URL
        self._connected = False
        self._design_info = None
        self._parameters_cache = None

    # ─── Connection ───────────────────────────────────

    def check_connection(self) -> Dict:
        """Check if Fusion 360 is running with the bridge add-in."""
        try:
            resp = requests.get(
                f"{self.base_url}/fusion/status",
                timeout=5
            )
            data = resp.json()
            self._connected = data.get("connected", False)
            return data
        except Exception:
            self._connected = False
            return {"connected": False, "error": "Cannot reach Fusion 360. Is the FusionBridge add-in running?"}

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ─── Design Info ──────────────────────────────────

    def get_design_info(self) -> Dict:
        """Get current design metadata from Fusion 360."""
        if not self._connected:
            return {"error": "Not connected to Fusion 360"}
        try:
            resp = requests.get(
                f"{self.base_url}/fusion/design/info",
                timeout=BRIDGE_TIMEOUT
            )
            data = resp.json()
            self._design_info = data
            return data
        except Exception as e:
            return {"error": f"Failed to get design info: {e}"}

    # ─── Parameters ───────────────────────────────────

    def get_parameters(self) -> Dict:
        """Get all parameters from the current Fusion 360 design."""
        if not self._connected:
            return {"parameters": [], "error": "Not connected"}
        try:
            resp = requests.get(
                f"{self.base_url}/fusion/design/parameters",
                timeout=BRIDGE_TIMEOUT
            )
            data = resp.json()
            self._parameters_cache = data.get("parameters", [])
            return data
        except Exception as e:
            return {"parameters": [], "error": str(e)}

    def get_parameter_names(self) -> List[str]:
        """Get list of all parameter names for NLP matching."""
        if self._parameters_cache:
            return [p["name"] for p in self._parameters_cache]
        data = self.get_parameters()
        return [p["name"] for p in data.get("parameters", [])]

    # ─── Components ───────────────────────────────────

    def get_components(self) -> Dict:
        """Get component tree from Fusion 360."""
        if not self._connected:
            return {"components": [], "error": "Not connected"}
        try:
            resp = requests.get(
                f"{self.base_url}/fusion/design/components",
                timeout=BRIDGE_TIMEOUT
            )
            return resp.json()
        except Exception as e:
            return {"components": [], "error": str(e)}

    # ─── Snapshot ─────────────────────────────────────

    def take_snapshot(self) -> Dict:
        """Capture a geometry snapshot (for before/after comparison)."""
        if not self._connected:
            return _simulated_snapshot()
        try:
            resp = requests.post(
                f"{self.base_url}/fusion/design/snapshot",
                json={},
                timeout=BRIDGE_TIMEOUT
            )
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    # ─── Modification ─────────────────────────────────

    def modify_parameter(self, param_name: str, new_expression: str) -> Dict:
        """Modify a parameter value in Fusion 360."""
        if not self._connected:
            return _simulated_modification(param_name, new_expression)
        try:
            resp = requests.post(
                f"{self.base_url}/fusion/design/modify",
                json={
                    "parameter_name": param_name,
                    "new_expression": new_expression,
                },
                timeout=BRIDGE_TIMEOUT
            )
            return resp.json()
        except Exception as e:
            return {"error": f"Modification failed: {e}"}

    # ─── Export ───────────────────────────────────────

    def export_stl(self, filename: str, component_name: str = "") -> Dict:
        """Export current design as STL."""
        export_path = str(OUTPUTS_DIR / filename)
        if not self._connected:
            return {"success": False, "simulated": True, "path": export_path}
        try:
            resp = requests.post(
                f"{self.base_url}/fusion/design/export/stl",
                json={"path": export_path, "component": component_name},
                timeout=BRIDGE_TIMEOUT
            )
            return resp.json()
        except Exception as e:
            return {"error": f"STL export failed: {e}"}

    def export_step(self, filename: str) -> Dict:
        """Export current design as STEP."""
        export_path = str(OUTPUTS_DIR / filename)
        if not self._connected:
            return {"success": False, "simulated": True, "path": export_path}
        try:
            resp = requests.post(
                f"{self.base_url}/fusion/design/export/step",
                json={"path": export_path},
                timeout=BRIDGE_TIMEOUT
            )
            return resp.json()
        except Exception as e:
            return {"error": f"STEP export failed: {e}"}

    # ─── Save & Undo ─────────────────────────────────

    def save_document(self, save_as_path: str = "") -> Dict:
        """Save the active .f3d document in Fusion 360."""
        if not self._connected:
            return {"success": False, "simulated": True, "message": "Not connected to Fusion 360"}
        try:
            payload = {}
            if save_as_path:
                payload["path"] = save_as_path
            resp = requests.post(
                f"{self.base_url}/fusion/design/save",
                json=payload,
                timeout=BRIDGE_TIMEOUT
            )
            return resp.json()
        except Exception as e:
            return {"error": f"Save failed: {e}"}

    def undo(self) -> Dict:
        """Undo the last operation in Fusion 360."""
        if not self._connected:
            return {"success": False, "simulated": True}
        try:
            resp = requests.post(
                f"{self.base_url}/fusion/design/undo",
                json={},
                timeout=BRIDGE_TIMEOUT
            )
            return resp.json()
        except Exception as e:
            return {"error": f"Undo failed: {e}"}


# ═══════════════════════════════════════════════════════════
#  HIGH-LEVEL MODIFICATION FUNCTION
# ═══════════════════════════════════════════════════════════

def apply_modification(bridge: FusionBridge, action: str, target_part: str,
                       parameter: Optional[str] = None, value: Optional[float] = None,
                       unit: str = "mm", material_value: str = None) -> Dict:
    """
    Apply a modification to the Fusion 360 model.
    
    1. Take a before snapshot
    2. Resolve parameter name
    3. Calculate new expression
    4. Modify parameter in Fusion 360
    5. Take after snapshot
    6. Export STL files
    """
    # Safety: ensure value is numeric
    if value is None:
        value = 0.0

    result = {
        "success": False,
        "part_name": target_part,
        "before": {},
        "after": {},
        "param_changed": None,
        "old_expression": None,
        "new_expression": None,
        "original_stl": None,
        "modified_stl": None,
        "modified_step": None,
        "message": "",
        "simulated": not bridge.is_connected,
    }

    # 1. Take BEFORE snapshot
    before = bridge.take_snapshot()
    result["before"] = before

    # 2. Resolve the Fusion component name for this part
    safe_name = _safe_filename(target_part)
    
    # Map our part names to Fusion occurrence component names
    # Universal Joint model — simple ASCII names from Fusion 360
    component_map = {
        "fork_1": "Fork 1",
        "fork_2": "Fork 2",
        "shaft": "Shaft",
        "pin": "Pin 1",        # Both pins share component 'Pin 1'
    }
    fusion_comp_name = component_map.get(safe_name.lower(), "")

    # 3. Export BEFORE STL from Fusion (same component we'll modify)
    stl_before = f"{safe_name}_original.stl"
    print(f"  [CAD] Exporting BEFORE STL from Fusion: component='{fusion_comp_name}'")
    bridge.export_stl(stl_before, component_name=fusion_comp_name)
    result["original_stl"] = stl_before

    # 4. Find the matching parameter
    param_name = _resolve_parameter(bridge, target_part, parameter)
    if not param_name:
        result["message"] = f"Could not find parameter '{parameter}' for '{target_part}' in Fusion 360"
        result["simulated"] = True
        return _simulate_full_modification(result, action, parameter, value, before)

    # 5. Get current parameter value
    params_data = bridge.get_parameters()
    current_param = None
    for p in params_data.get("parameters", []):
        if p["name"] == param_name:
            current_param = p
            break

    if not current_param:
        result["message"] = f"Parameter '{param_name}' not found"
        return _simulate_full_modification(result, action, parameter, value, before)

    # 6. Calculate new expression
    old_expression = current_param["expression"]
    new_expression = _calculate_new_expression(action, old_expression, value, unit)

    result["param_changed"] = param_name
    result["old_expression"] = old_expression
    result["new_expression"] = new_expression

    # 7. Apply modification IN FUSION 360 (design.computeAll rebuilds geometry)
    mod_result = bridge.modify_parameter(param_name, new_expression)
    print(f"  [CAD] Modified {param_name}: {old_expression} -> {new_expression}")
    print(f"  [CAD] Fusion response: {mod_result}")

    if mod_result.get("error"):
        result["message"] = f"Fusion 360 error: {mod_result['error']}"
        return result

    # 8. Take AFTER snapshot from Fusion (geometry already rebuilt by computeAll)
    time.sleep(1)
    after = bridge.take_snapshot()
    result["after"] = after

    # 9. Export AFTER STL from Fusion (same component, now modified)
    stl_after = f"{safe_name}_modified.stl"
    step_after = f"{safe_name}_modified.step"
    print(f"  [CAD] Exporting AFTER STL from Fusion: component='{fusion_comp_name}'")
    bridge.export_stl(stl_after, component_name=fusion_comp_name)
    bridge.export_step(step_after)

    result["modified_stl"] = stl_after
    result["modified_step"] = step_after
    result["success"] = True
    result["message"] = mod_result.get("message", f"Modified {param_name}: {old_expression} -> {new_expression}")

    # 9. AUTO-SAVE the .f3d file
    save_result = bridge.save_document()
    result["saved"] = save_result.get("success", False)
    if save_result.get("success"):
        result["message"] += " | Document saved."
    else:
        result["message"] += f" | Save warning: {save_result.get('error', 'unknown')}"

    return result


# ═══════════════════════════════════════════════════════════
#  HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════

def _resolve_parameter(bridge: FusionBridge, target_part: str, parameter: str) -> Optional[str]:
    """Map an NLP-parsed parameter name to an actual Fusion 360 parameter name.
    
    Handles both named user parameters AND unnamed model parameters (d2, d3, etc.)
    that are common in downloaded GrabCAD/external models.
    """
    if not parameter:
        return None

    params = bridge.get_parameter_names()
    params_data = bridge.get_parameters()
    all_params = params_data.get("parameters", [])

    # ── 1. Direct match ───────────────────────────────
    if parameter in params:
        return parameter

    underscore_version = parameter.replace(" ", "_")
    if underscore_version in params:
        return underscore_version

    # ── 2. Named parameter mappings (DemoGearboxBuilder etc.) ──
    named_mappings = {
        "wall_thickness": ["wall_thickness", "wallThickness", "housing_wall_thickness"],
        "diameter": ["input_shaft_dia", "output_shaft_dia", "bearing_inner_dia", "bearing_outer_dia"],
        "inner_diameter": ["bearing_inner_dia", "input_shaft_dia"],
        "outer_diameter": ["bearing_outer_dia"],
        "length": ["housing_length", "input_shaft_length", "output_shaft_length"],
        "width": ["housing_width", "gear_a_face_width", "gear_b_face_width", "bearing_width"],
        "height": ["housing_height"],
        "face_width": ["gear_a_face_width", "gear_b_face_width"],
        "teeth": ["gear_a_teeth", "gear_b_teeth"],
        "gear_module": ["gear_a_module", "gear_b_module"],
        "hole_diameter": ["bolt_hole_dia"],
    }

    target_lower = target_part.lower().replace(" ", "_")
    candidates = named_mappings.get(parameter, [])

    for c in candidates:
        if target_lower in c.lower() and c in params:
            return c
    for c in candidates:
        if c in params:
            return c

    # Fuzzy search on named params
    for p in params:
        p_lower = p.lower()
        param_lower = parameter.lower().replace("_", "")
        if param_lower in p_lower.replace("_", ""):
            if target_lower.split("_")[0] in p_lower or not target_lower:
                return p

    for p in params:
        if parameter.replace("_", "") in p.lower().replace("_", ""):
            return p

    # ── 3. Universal Joint model parameter mappings ──
    # Maps engineering terms to actual dXX model parameters.
    # Verified by testing each parameter's effect on component bounding boxes.
    universal_joint_mappings = {
        # Pin dimensions
        "pin_length": "d2",           # 3.6 mm — pin length (verified: changes Pin bbox height)
        "pin_diameter": "d4",         # 1.0 mm — pin diameter (verified: changes Pin bbox width/depth)
        
        # Fork dimensions
        "fork_length": "d13",         # 3.2 mm — fork length (verified: changes Fork bbox height)
        "fork_width": "d9",           # 1.8 mm — fork width
        "fork_depth": "d14",          # 1.8 mm — fork depth
        
        # Shaft/Spider dimensions
        "shaft_diameter": "d32",      # 2.2 mm — shaft/spider diameter
        "trunnion_length": "d11",     # 1.1 mm — trunnion arm length
        "spread": "d22",              # 2.6 mm — spider spread/span
        
        # Generic aliases
        "diameter": "d4",             # generic diameter -> pin diameter
        "length": "d2",               # generic length -> pin length
        "width": "d9",                # generic width -> fork width
        "height": "d13",              # generic height -> fork length
        "depth": "d14",               # generic depth -> fork depth
        "thickness": "d15",           # 0.6 mm — wall/arm thickness
        "wall_thickness": "d15",      # alias
        "bore_diameter": "d10",       # 1.0 mm — bore in fork for pin
        "hole_diameter": "d10",       # alias
        "outer_diameter": "d32",      # shaft outer diameter
        "inner_diameter": "d10",      # bore
    }

    # Try direct mapping
    param_key = parameter.lower().replace(" ", "_")
    if param_key in universal_joint_mappings:
        mapped = universal_joint_mappings[param_key]
        if mapped in params:
            return mapped

    # ── 4. Heuristic: match by value range for common terms ──
    # When no static mapping works, find model parameters (dXX) that
    # have values in a plausible range for the requested parameter type.
    param_type_ranges = {
        "wall_thickness": (0.3, 2.0),   # small model — 0.3-2mm
        "thickness": (0.3, 2.0),
        "diameter": (0.5, 5.0),         # universal joint is small (~1-4mm)
        "outer_diameter": (1.0, 5.0),
        "inner_diameter": (0.5, 3.0),
        "height": (1.0, 5.0),
        "width": (1.0, 5.0),
        "length": (1.0, 5.0),
    }

    if param_key in param_type_ranges:
        lo, hi = param_type_ranges[param_key]
        # Find model params in that range
        for p in all_params:
            name = p.get("name", "")
            if not name.startswith("d"):
                continue
            val = p.get("value", 0)  # Fusion internal value is in cm
            val_mm = abs(val) * 10   # Convert cm → mm
            unit = p.get("unit", "")
            if unit == "deg" or unit == "":
                continue  # Skip angles and dimensionless
            if lo <= val_mm <= hi:
                return name

    return None


def _calculate_new_expression(action: str, old_expression: str, value: float, unit: str) -> str:
    """Calculate the new parameter expression based on the action."""
    import re

    # Safety: ensure value is a number
    if value is None:
        value = 0.0
    value = float(value)

    # Extract numeric value from old expression
    old_num_match = re.search(r'([\d.]+)', str(old_expression))
    old_num = float(old_num_match.group(1)) if old_num_match else 0

    # Extract unit from old expression
    old_unit_match = re.search(r'[a-zA-Z]+', str(old_expression))
    old_unit = old_unit_match.group(0) if old_unit_match else (unit or 'mm')

    if action == "REDUCE":
        new_val = max(0.1, old_num - value)
    elif action == "INCREASE":
        new_val = old_num + value
    elif action == "CHANGE":
        new_val = value if value > 0 else old_num
    elif action == "SCALE":
        new_val = old_num * value if value > 0 else old_num
    else:
        new_val = value if value > 0 else old_num

    # Format with unit
    if new_val == int(new_val):
        return f"{int(new_val)} {old_unit}"
    else:
        return f"{new_val:.2f} {old_unit}"


def _safe_filename(name: str) -> str:
    """Create a safe filename from a part name."""
    return name.replace(" ", "_").replace("/", "_").replace("\\", "_")


def _simulated_snapshot() -> Dict:
    """Return a simulated snapshot when Fusion is not connected."""
    return {
        "parameters": {
            "wall_thickness": {"expression": "5 mm", "value": 0.5, "unit": "mm"},
            "housing_length": {"expression": "120 mm", "value": 12.0, "unit": "mm"},
            "housing_width": {"expression": "80 mm", "value": 8.0, "unit": "mm"},
            "housing_height": {"expression": "90 mm", "value": 9.0, "unit": "mm"},
        },
        "total_volume": 450000,
        "total_area": 48000,
        "bounding_box": {"length": 12.0, "width": 8.0, "height": 9.0},
        "bodies": [{"name": "Housing Body", "volume": 450000, "area": 48000}],
        "simulated": True,
    }


def _simulated_modification(param_name: str, new_expression: str) -> Dict:
    """Simulate a parameter modification."""
    return {
        "success": True,
        "parameter": param_name,
        "before_expression": "5 mm",
        "after_expression": new_expression,
        "message": f"Simulated: {param_name} -> {new_expression} (Fusion 360 not connected)",
        "simulated": True,
    }


def _simulate_full_modification(result: Dict, action: str, parameter: str,
                                 value: float, before: Dict) -> Dict:
    """Simulate a full modification when Fusion is not available."""
    result["simulated"] = True
    result["after"] = before.copy()

    # Approximate changes
    if parameter == "wall_thickness" and action == "REDUCE":
        vol = result["after"].get("total_volume", 450000)
        result["after"]["total_volume"] = round(vol * 0.85, 2)

    result["success"] = True
    result["message"] = (
        f"Simulated {action} on {parameter} (Fusion 360 not connected — "
        f"connect for real CAD modifications)"
    )
    return result


# ═══════════════════════════════════════════════════════════
#  GLOBAL BRIDGE INSTANCE
# ═══════════════════════════════════════════════════════════

fusion_bridge = FusionBridge()
