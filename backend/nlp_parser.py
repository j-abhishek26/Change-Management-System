"""
NLP Parser for Engineering Change Requests.
Uses spaCy + rule-based pattern matching to extract structured information
from natural language engineering change requests.

Works with ANY model — not limited to specific parts.
"""

import re
from typing import List, Dict, Optional

# Try to load spaCy, fall back to basic parsing if unavailable
try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
    SPACY_AVAILABLE = True
except (ImportError, OSError):
    SPACY_AVAILABLE = False
    print("⚠️  spaCy not available — using rule-based parser only")


# ─── Action Vocabulary ───────────────────────────────────
# Maps natural language verbs to normalized action types

ACTION_MAP = {
    # Reduce family
    "reduce": "REDUCE", "decrease": "REDUCE", "lower": "REDUCE",
    "shrink": "REDUCE", "thin": "REDUCE", "narrow": "REDUCE",
    "shorten": "REDUCE", "minimize": "REDUCE", "diminish": "REDUCE",
    "trim": "REDUCE",
    # Increase family
    "increase": "INCREASE", "enlarge": "INCREASE", "raise": "INCREASE",
    "grow": "INCREASE", "thicken": "INCREASE", "widen": "INCREASE",
    "lengthen": "INCREASE", "extend": "INCREASE", "expand": "INCREASE",
    "maximize": "INCREASE", "boost": "INCREASE",
    # Change/Modify family
    "change": "CHANGE", "modify": "CHANGE", "update": "CHANGE",
    "set": "CHANGE", "make": "CHANGE", "alter": "CHANGE", "adjust": "CHANGE",
    # Add family
    "add": "ADD", "insert": "ADD", "include": "ADD",
    "attach": "ADD", "create": "ADD", "drill": "ADD", "bore": "ADD",
    # Remove family
    "remove": "REMOVE", "delete": "REMOVE", "eliminate": "REMOVE",
    "cut": "REMOVE", "strip": "REMOVE",
    # Replace family
    "replace": "REPLACE", "substitute": "REPLACE", "swap": "REPLACE",
    "switch": "REPLACE", "use": "REPLACE",
    # Scale family
    "scale": "SCALE", "resize": "SCALE",
    # Fillet/chamfer family
    "fillet": "FILLET", "round": "FILLET", "chamfer": "CHAMFER",
    "bevel": "CHAMFER",
}

# ─── Parameter Vocabulary ────────────────────────────────
# Maps natural language phrases to normalized parameter keys
# Sorted by length (longest first) to match multi-word phrases first

PARAMETER_MAP = {
    # Universal joint specific terms
    "pin diameter": "pin_diameter",
    "pin length": "pin_length",
    "fork length": "fork_length",
    "fork width": "fork_width",
    "fork depth": "fork_depth",
    "trunnion length": "trunnion_length",
    "shaft diameter": "shaft_diameter",
    "spider diameter": "shaft_diameter",
    "spread": "spread",
    # Generic terms
    "wall thickness": "wall_thickness",
    "shell thickness": "wall_thickness",
    "casing thickness": "wall_thickness",
    "thickness": "thickness",
    "outer diameter": "outer_diameter",
    "inner diameter": "inner_diameter",
    "bore diameter": "bore_diameter",
    "diameter": "diameter",
    "dia": "diameter",
    "length": "length",
    "width": "width",
    "height": "height",
    "depth": "depth",
    "radius": "radius",
    "fillet radius": "radius",
    "chamfer size": "radius",
    "material": "material",
    "weight": "weight",
    "mass": "weight",
    "size": "size",
    "bore": "bore_diameter",
    "hole": "hole_diameter",
    "angle": "angle",
    "tolerance": "tolerance",
}

# Pre-sort by length (longest first) for matching
_SORTED_PARAMS = sorted(PARAMETER_MAP.items(), key=lambda x: len(x[0]), reverse=True)


# ─── Material Vocabulary ─────────────────────────────────

KNOWN_MATERIALS = [
    "aluminum 6061", "aluminum 7075", "aluminum 6061-t6",
    "steel 4140", "steel 8620", "steel 4340", "steel 9310",
    "stainless steel 304", "stainless steel 316",
    "chrome steel", "carbon steel", "tool steel",
    "titanium", "titanium ti-6al-4v",
    "brass", "bronze", "copper",
    "cast iron", "ductile iron",
    "nylon", "delrin", "peek", "abs", "polycarbonate",
    "nitrile rubber", "viton", "silicone",
    "ceramic", "cork composite",
]


def parse_change_request(text: str, known_parts: Optional[List[str]] = None) -> Dict:
    """
    Parse a natural language engineering change request into structured data.
    
    Args:
        text: The user's natural language change request
        known_parts: List of known part names for matching
        
    Returns:
        Dictionary with: action, target_part, parameter, value, unit, 
                         material_value, confidence
    """
    result = {
        "original_text": text,
        "action": None,
        "target_part": None,
        "parameter": None,
        "value": None,
        "unit": "mm",
        "material_value": None,
        "confidence": 0.0,
        "interpretation": "",
    }

    text_lower = text.lower().strip()

    # ── Step 1: Extract Action ────────────────────────────
    action_found = False
    if SPACY_AVAILABLE:
        doc = nlp(text_lower)
        for token in doc:
            lemma = token.lemma_.lower()
            if lemma in ACTION_MAP:
                result["action"] = ACTION_MAP[lemma]
                action_found = True
                break

    if not action_found:
        # Fallback: simple word matching
        for word in text_lower.split():
            clean_word = word.strip(".,;:!?")
            if clean_word in ACTION_MAP:
                result["action"] = ACTION_MAP[clean_word]
                break

    # Special case: "drill a hole" → ADD hole
    if "drill" in text_lower or ("add" in text_lower and "hole" in text_lower):
        result["action"] = "ADD"
        if not result.get("parameter"):
            result["parameter"] = "hole_diameter"

    # ── Step 2: Extract Value and Unit ────────────────────
    # Pattern: number + optional unit
    value_patterns = [
        r'(?:by|to|=|of)\s+(\d+\.?\d*)\s*(mm|cm|m|inch|in|inches|%|degrees?|deg|kn)',
        r'(\d+\.?\d*)\s*(mm|cm|m|inch|in|inches|%|degrees?|deg|kn)',
        r'(?:by|to|=)\s+(\d+\.?\d*)',
    ]

    for pattern in value_patterns:
        match = re.search(pattern, text_lower)
        if match:
            result["value"] = float(match.group(1))
            if match.lastindex >= 2:
                result["unit"] = match.group(2).rstrip('s')  # normalize "inches" → "inch"
            break

    # Handle percentage
    if result["unit"] == "%":
        # Convert percentage to scale factor
        if result["action"] == "INCREASE":
            result["value"] = 1.0 + (result["value"] / 100.0)
        elif result["action"] == "REDUCE":
            result["value"] = 1.0 - (result["value"] / 100.0)
        result["action"] = "SCALE"
        result["unit"] = "factor"

    # ── Step 3: Extract Parameter ─────────────────────────
    for phrase, param_key in _SORTED_PARAMS:
        if phrase in text_lower:
            result["parameter"] = param_key
            break

    # ── Step 4: Extract Target Part ───────────────────────
    if known_parts:
        # Try matching known parts (case-insensitive)
        # Sort by name length descending to match longer names first
        for part_name in sorted(known_parts, key=len, reverse=True):
            # Try exact and partial matching
            variants = [
                part_name.lower(),
                part_name.lower().replace("_", " "),
                part_name.lower().replace(" ", "_"),
            ]
            for variant in variants:
                if variant in text_lower:
                    result["target_part"] = part_name
                    break
            if result["target_part"]:
                break

    # If no part found with known list, try to extract from text
    if not result["target_part"]:
        # Pattern 1: "of <Part Name>"
        part_patterns = [
            r'(?:of|on|in|to|for)\s+(?:the\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'(?:of|on|in|to|for)\s+(?:the\s+)?(\w+(?:\s+\w+)?)\s+(?:by|to|from)',
        ]
        for pattern in part_patterns:
            match = re.search(pattern, text)
            if match:
                candidate = match.group(1).strip()
                # Filter out common non-part words
                skip_words = {"the", "a", "an", "all", "every", "each", "its", "this", "that"}
                if candidate.lower() not in skip_words:
                    result["target_part"] = candidate
                    break

    # ── Step 5: Extract Material (for material changes) ──
    if "material" in text_lower or result["action"] in ("CHANGE", "REPLACE"):
        for mat in sorted(KNOWN_MATERIALS, key=len, reverse=True):
            if mat in text_lower:
                result["material_value"] = mat.title()
                result["parameter"] = "material"
                break

        if not result["material_value"]:
            # Try pattern: "to <Material>"
            mat_pattern = r'(?:to|with|using)\s+([A-Za-z0-9][\w\s\-]+?)(?:\s*$|\s*\.|(?:\s+(?:for|on|in)))'
            match = re.search(mat_pattern, text, re.IGNORECASE)
            if match:
                candidate = match.group(1).strip()
                # Don't capture action words as materials
                if candidate.lower() not in ACTION_MAP and len(candidate) > 2:
                    result["material_value"] = candidate.title()
                    result["parameter"] = "material"

    # ── Step 6: Calculate Confidence ──────────────────────
    score = 0
    if result["action"]:
        score += 1
    if result["target_part"]:
        score += 1
    if result["parameter"] or result["action"] in ("SCALE", "FILLET", "CHAMFER"):
        score += 1
    if result["value"] is not None or result["material_value"]:
        score += 1
    result["confidence"] = round(score / 4.0, 2)

    # ── Step 7: Build Interpretation String ───────────────
    parts = []
    if result["action"]:
        parts.append(f"Action: {result['action']}")
    if result["target_part"]:
        parts.append(f"Target: {result['target_part']}")
    if result["parameter"]:
        parts.append(f"Parameter: {result['parameter']}")
    if result["value"] is not None:
        parts.append(f"Value: {result['value']} {result['unit']}")
    if result["material_value"]:
        parts.append(f"New Material: {result['material_value']}")

    result["interpretation"] = " | ".join(parts) if parts else "Could not parse request"

    return result


def get_supported_actions() -> List[str]:
    """Return list of supported action types."""
    return list(set(ACTION_MAP.values()))


def get_supported_parameters() -> List[str]:
    """Return list of supported parameter types."""
    return list(set(PARAMETER_MAP.values()))
