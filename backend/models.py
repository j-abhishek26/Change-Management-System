"""
Pydantic data models for the Engineering Change Management System.
Defines request/response schemas for the API.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# ─── Enums ───────────────────────────────────────────────

class ActionType(str, Enum):
    REDUCE = "REDUCE"
    INCREASE = "INCREASE"
    CHANGE = "CHANGE"
    ADD = "ADD"
    REMOVE = "REMOVE"
    REPLACE = "REPLACE"
    SCALE = "SCALE"
    FILLET = "FILLET"
    CHAMFER = "CHAMFER"


class ChangeClassification(str, Enum):
    MAJOR = "MAJOR"
    MINOR = "MINOR"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


# ─── Request Models ──────────────────────────────────────

class ChangeRequest(BaseModel):
    """Input from the user — a natural language change request."""
    text: str = Field(..., description="Natural language change request", 
                      examples=["Increase pin diameter of Pin by 0.5 mm"])
    target_part_override: Optional[str] = Field(None, description="Override for target part name (optional)")


# ─── NLP Parser Output ───────────────────────────────────

class ParsedInstruction(BaseModel):
    """Output from the NLP parser."""
    model_config = {"extra": "ignore"}  # Ignore extra fields like 'interpretation'

    original_text: str
    action: Optional[str] = None
    target_part: Optional[str] = None
    parameter: Optional[str] = None
    value: Optional[float] = None
    unit: str = "mm"
    material_value: Optional[str] = None
    confidence: float = 0.0
    # Fusion 360 resolved parameter name
    fusion_parameter: Optional[str] = None


# ─── Fusion 360 Models ──────────────────────────────────

class FusionParameter(BaseModel):
    """A parameter from a Fusion 360 design."""
    name: str
    expression: str
    value: float
    unit: str
    comment: Optional[str] = ""
    type: str = "user"  # 'user' or 'model'


class FusionComponent(BaseModel):
    """A component from a Fusion 360 design."""
    name: str
    depth: int = 0
    bodies: List[Dict[str, Any]] = []
    material: Optional[str] = None


class FusionDesignInfo(BaseModel):
    """Metadata about the current Fusion 360 design."""
    design_name: str
    document_name: str
    units: str = "mm"
    component_count: int = 0
    body_count: int = 0
    design_type: str = "Parametric"
    is_saved: bool = False


# ─── Part Information ────────────────────────────────────

class BoundingBox(BaseModel):
    length: float
    width: float
    height: float


class PartMetadata(BaseModel):
    """Metadata computed from a CAD model."""
    filename: Optional[str] = None
    bounding_box: Optional[BoundingBox] = None
    volume: Optional[float] = None
    surface_area: Optional[float] = None
    num_faces: Optional[int] = None
    num_edges: Optional[int] = None
    center_x: Optional[float] = None
    center_y: Optional[float] = None
    center_z: Optional[float] = None


class PartInfo(BaseModel):
    """Full part information from the database."""
    id: str
    name: str
    description: Optional[str] = None
    material: Optional[str] = None
    category: Optional[str] = None
    parameters: Dict[str, Any] = {}
    weight_kg: Optional[float] = None
    cost_usd: Optional[float] = None
    source: str = "demo"  # 'demo' or 'uploaded'
    filepath: Optional[str] = None
    cad_metadata: Optional[PartMetadata] = None


# ─── Impact Analysis Results ─────────────────────────────

class AffectedPart(BaseModel):
    """A part that is affected by the change."""
    part_id: str
    part_name: str
    relationship: str  # e.g., 'mates_with', 'housed_in'
    impact_description: str
    severity: str = "MEDIUM"  # LOW, MEDIUM, HIGH
    severity_score: int = 50  # 0-100 quantified severity


class BOMImpact(BaseModel):
    impact_type: str  # 'weight_change', 'cost_change', 'material_change'
    description: str
    estimated_change: Optional[str] = None


class DocumentImpact(BaseModel):
    doc_type: str
    doc_title: Optional[str] = None
    action_required: str  # 'Update required', 'Review required'


class ImpactAnalysisResult(BaseModel):
    """Complete output from the impact analyzer."""
    change_id: str
    target_part: str
    target_part_id: Optional[str] = None
    parsed_instruction: ParsedInstruction
    affected_parts: List[AffectedPart] = []
    total_affected_count: int = 0
    classification: ChangeClassification = ChangeClassification.MINOR
    risk_level: RiskLevel = RiskLevel.LOW
    effort_hours: float = 0.0
    bom_impacts: List[BOMImpact] = []
    document_impacts: List[DocumentImpact] = []
    # Before/after metrics from Fusion 360
    before_metrics: Dict[str, Any] = {}
    after_metrics: Dict[str, Any] = {}
    # Parameter change details
    param_changed: Optional[str] = None
    old_expression: Optional[str] = None
    new_expression: Optional[str] = None
    # File paths for 3D viewer
    original_stl_path: Optional[str] = None
    modified_stl_path: Optional[str] = None
    modified_step_path: Optional[str] = None
    # Fusion design info
    fusion_design: Optional[Dict[str, Any]] = None
    fusion_connected: bool = False
    # Timestamps
    timestamp: str = ""
    recommendations: List[str] = []


# ─── API Response Models ─────────────────────────────────

class PartsListResponse(BaseModel):
    parts: List[PartInfo]
    total: int
    source: str  # 'demo' or 'uploaded'


class UploadResponse(BaseModel):
    success: bool
    message: str
    part_name: Optional[str] = None
    metadata: Optional[PartMetadata] = None


class AnalysisResponse(BaseModel):
    success: bool
    message: str
    parsed: Optional[ParsedInstruction] = None
    impact: Optional[ImpactAnalysisResult] = None
    report_url: Optional[str] = None


class DemoLoadResponse(BaseModel):
    success: bool
    message: str
    parts: List[PartInfo] = []
    total_parts: int = 0
