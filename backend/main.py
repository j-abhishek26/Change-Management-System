"""
FastAPI Application — Engineering Change Management System v3.0
Integrates Change Analyzer + PDM + ERP through an intelligent reasoning layer.

Run: python backend/main.py
"""

import os
import sys
import uuid
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse

from backend.models import (
    ChangeRequest, AnalysisResponse, ParsedInstruction,
    PartInfo, PartsListResponse, UploadResponse, DemoLoadResponse
)
from backend.nlp_parser import parse_change_request
from backend.cad_engine import fusion_bridge, apply_modification, OUTPUTS_DIR, UPLOADS_DIR
from backend.impact_analyzer import ImpactAnalyzer
from backend.report_generator import generate_report
from backend.pdm import pdm_manager
from backend.erp import erp_manager
from backend import database as db

# ─── App Setup ────────────────────────────────────────────

app = FastAPI(
    title="Engineering Change Management System",
    description="Prompt-driven intelligent change analysis with Fusion 360, PDM, and ERP integration",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

REPORTS_DIR = PROJECT_ROOT / "reports"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
for d in [UPLOADS_DIR, OUTPUTS_DIR, REPORTS_DIR]:
    d.mkdir(exist_ok=True)

analyzer = ImpactAnalyzer()


# ─── Startup ──────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    print("\n" + "=" * 60)
    print("  Engineering Change Management System v3.0")
    print("  Fusion 360 + PDM + ERP Integration")
    print("=" * 60)

    db.init_schema()
    print("  [OK] Database initialized (Core + PDM + ERP tables)")

    # Reset and reload demo data
    parts = db.get_all_parts(source="demo")
    if not parts:
        print("  [..] Loading demo data...")
        from data.init_db import populate_demo_data
        populate_demo_data()

    status = fusion_bridge.check_connection()
    if status.get("connected"):
        print(f"  [OK] Fusion 360 connected (v{status.get('version', '?')})")
    else:
        print("  [--] Fusion 360 not connected (simulation mode)")

    print(f"\n  URL:  http://localhost:8000")
    print(f"  Docs: http://localhost:8000/docs")
    print("=" * 60 + "\n")


# ─── Static File Serving ─────────────────────────────────

app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")
app.mount("/reports", StaticFiles(directory=str(REPORTS_DIR)), name="reports")

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Frontend not found</h1>")

@app.get("/style.css")
async def serve_css():
    return FileResponse(FRONTEND_DIR / "style.css", media_type="text/css")

@app.get("/app.js")
async def serve_js():
    return FileResponse(FRONTEND_DIR / "app.js", media_type="application/javascript")

@app.get("/three_viewer.js")
async def serve_viewer_js():
    return FileResponse(FRONTEND_DIR / "three_viewer.js", media_type="application/javascript")


# ═══════════════════════════════════════════════════════════
#  FUSION 360 ENDPOINTS
# ═══════════════════════════════════════════════════════════

@app.get("/api/fusion/connect")
async def connect_fusion():
    status = fusion_bridge.check_connection()
    if not status.get("connected"):
        return {
            "connected": False,
            "message": "Cannot reach Fusion 360. Ensure FusionBridge add-in is running.",
        }
    design_info = fusion_bridge.get_design_info()
    params_data = fusion_bridge.get_parameters()
    components_data = fusion_bridge.get_components()
    _sync_fusion_parts(components_data.get("components", []), params_data.get("parameters", []))
    return {
        "connected": True,
        "message": f"Connected to Fusion 360 — {design_info.get('design_name', 'Unknown')}",
        "design": design_info,
        "parameters": params_data.get("parameters", []),
        "components": components_data.get("components", []),
    }

@app.get("/api/fusion/parameters")
async def get_fusion_parameters():
    if not fusion_bridge.is_connected:
        fusion_bridge.check_connection()
    return fusion_bridge.get_parameters()

@app.get("/api/fusion/components")
async def get_fusion_components():
    if not fusion_bridge.is_connected:
        fusion_bridge.check_connection()
    return fusion_bridge.get_components()

@app.post("/api/fusion/save")
async def save_fusion_document():
    """Save the active .f3d file in Fusion 360."""
    if not fusion_bridge.is_connected:
        raise HTTPException(status_code=503, detail="Fusion 360 not connected")
    result = fusion_bridge.save_document()
    return result

@app.post("/api/fusion/undo")
async def undo_fusion():
    """Undo the last operation in Fusion 360."""
    if not fusion_bridge.is_connected:
        raise HTTPException(status_code=503, detail="Fusion 360 not connected")
    result = fusion_bridge.undo()
    return result


# ═══════════════════════════════════════════════════════════
#  PARTS & DEMO ENDPOINTS
# ═══════════════════════════════════════════════════════════

@app.get("/api/parts")
async def list_parts():
    parts_db = db.get_all_parts()
    parts_list = []
    for p in parts_db:
        parts_list.append({
            "id": p["id"], "name": p["name"],
            "description": p.get("description"), "material": p.get("material"),
            "category": p.get("category"), "parameters": p.get("parameters", {}),
            "weight_kg": p.get("weight_kg"), "cost_usd": p.get("cost_usd"),
            "source": p.get("source", "demo"),
        })
    return {"parts": parts_list, "total": len(parts_list)}

@app.get("/api/parts/{part_name}")
async def get_part(part_name: str):
    part = db.get_part_by_name(part_name)
    if not part:
        raise HTTPException(status_code=404, detail=f"Part '{part_name}' not found")
    part["dependencies"] = db.get_dependencies(part_name)
    part["documents"] = db.get_documents_for_part(part_name)
    return part

@app.post("/api/demo/load")
async def load_demo():
    parts_db = db.get_all_parts(source="demo")
    parts_list = [{
        "id": p["id"], "name": p["name"],
        "description": p.get("description"), "material": p.get("material"),
        "category": p.get("category"), "parameters": p.get("parameters", {}),
        "weight_kg": p.get("weight_kg"), "cost_usd": p.get("cost_usd"),
        "source": "demo",
    } for p in parts_db]

    fusion_info = fusion_bridge.get_parameters() if fusion_bridge.is_connected else None

    return {
        "success": True,
        "message": f"Loaded {len(parts_list)} demo parts" +
                   (" — Fusion 360 connected" if fusion_bridge.is_connected else " — simulation mode"),
        "parts": parts_list,
        "total_parts": len(parts_list),
        "fusion_connected": fusion_bridge.is_connected,
        "fusion_parameters": fusion_info.get("parameters", []) if fusion_info else [],
    }

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    filename = file.filename or "uploaded.stp"
    ext = Path(filename).suffix.lower()
    if ext not in (".stp", ".step", ".f3d"):
        raise HTTPException(status_code=400, detail="Supported formats: .f3d, .stp, .step")
    save_path = UPLOADS_DIR / filename
    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)
    part_name = Path(filename).stem.replace("-", "_").replace(" ", "_")
    part_id = f"UPL-{uuid.uuid4().hex[:6].upper()}"
    db.upsert_part({
        "id": part_id, "name": part_name,
        "description": f"Uploaded file: {filename}",
        "material": "Unknown", "category": "uploaded",
        "parameters": {}, "source": "uploaded",
        "filepath": str(save_path),
    })
    message = f"Uploaded {filename}."
    if ext == ".f3d":
        message += " Open this file in Fusion 360 and connect the bridge to modify it."
    return {"success": True, "message": message, "part_name": part_name, "file_type": ext}


# ═══════════════════════════════════════════════════════════
#  CORE ANALYSIS ENDPOINT (Intelligent Reasoning Layer)
# ═══════════════════════════════════════════════════════════

@app.post("/api/analyze")
async def analyze_change(request: ChangeRequest):
    """
    Main pipeline: NLP → Fusion 360 → Impact Analysis → PDM → ERP → Report
    The intelligent reasoning layer connects all systems.
    """
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Change request text cannot be empty")

    # 1. Get known names for NLP
    known_parts = db.get_all_part_names()
    if fusion_bridge.is_connected:
        comps = fusion_bridge.get_components()
        for c in comps.get("components", []):
            if c["name"] not in known_parts:
                known_parts.append(c["name"])

    # 2. NLP Parse
    parsed_dict = parse_change_request(text, known_parts)
    parsed = ParsedInstruction(**parsed_dict)

    if request.target_part_override:
        parsed.target_part = request.target_part_override

    if not parsed.target_part:
        return {
            "success": False,
            "message": "Could not identify a target part. Please specify which part to modify.",
            "parsed": parsed.model_dump(),
        }

    # 3. Resolve Fusion parameter
    if fusion_bridge.is_connected and parsed.parameter:
        from backend.cad_engine import _resolve_parameter
        fusion_param = _resolve_parameter(fusion_bridge, parsed.target_part, parsed.parameter)
        parsed.fusion_parameter = fusion_param

    # 4. Apply CAD modification
    cad_result = None
    try:
        fusion_bridge.check_connection()
        cad_result = apply_modification(
            bridge=fusion_bridge,
            action=parsed.action or "CHANGE",
            target_part=parsed.target_part,
            parameter=parsed.parameter,
            value=parsed.value if parsed.value is not None else 0.0,
            unit=parsed.unit or "mm",
            material_value=parsed.material_value,
        )
    except Exception as e:
        print(f"CAD modification error: {e}")
        cad_result = None

    # 5. Impact analysis
    impact = analyzer.analyze(parsed, cad_result)
    impact.fusion_connected = fusion_bridge.is_connected
    if cad_result:
        impact.param_changed = cad_result.get("param_changed")
        impact.old_expression = cad_result.get("old_expression")
        impact.new_expression = cad_result.get("new_expression")

    if fusion_bridge.is_connected:
        impact.fusion_design = fusion_bridge.get_design_info()

    # ═══ INTELLIGENT REASONING LAYER ═══════════════════
    # Connect PDM, ERP, and Change Analysis

    # 6. PDM — Create revision for the changed part
    pdm_revision = None
    if impact.classification.value == "MAJOR":
        pdm_revision = pdm_manager.create_revision(
            part_name=parsed.target_part,
            change_id=impact.change_id,
            description=f"{parsed.action} {parsed.parameter or 'geometry'} — {text}",
        )

    # 7. PDM — Save CAD metadata from snapshot
    if cad_result and cad_result.get("before"):
        pdm_manager.save_part_metadata(
            parsed.target_part, cad_result["before"],
            revision=pdm_revision.get("previous_revision", "A") if pdm_revision else "A"
        )

    # 8. PDM — Get BOM impact
    bom_impact = pdm_manager.get_bom_impact(
        parsed.target_part, parsed.parameter or "", parsed.action or "", parsed.value or 0
    )

    # 9. ERP — Create manufacturing orders automatically
    erp_orders = erp_manager.create_work_order_from_change(
        change_id=impact.change_id,
        target_part=parsed.target_part,
        classification=impact.classification.value,
        risk_level=impact.risk_level.value,
        effort_hours=impact.effort_hours,
        affected_parts=[a.model_dump() for a in impact.affected_parts],
    )

    # 10. ERP — Create change order workflow
    erp_change_order = erp_manager.create_change_order(
        change_id=impact.change_id,
        title=f"{parsed.action} {parsed.parameter or 'geometry'} on {parsed.target_part}",
        description=text,
        target_part=parsed.target_part,
        classification=impact.classification.value,
        risk_level=impact.risk_level.value,
        effort_hours=impact.effort_hours,
        affected_count=impact.total_affected_count,
        total_cost=erp_orders.get("total_estimated_cost", 0),
    )

    # 11. ERP — Check inventory impact
    inventory_impact = erp_manager.check_inventory_impact(
        parsed.target_part, impact.classification.value
    )

    # 12. Generate report (with PDM and ERP data for comprehensive report)
    report_url = None
    pdf_url = None
    try:
        pdm_data = {
            "revision": pdm_revision,
            "bom_impact": bom_impact,
        }
        erp_data_for_report = {
            "change_order": erp_change_order,
            "manufacturing_orders": erp_orders,
            "inventory_impact": inventory_impact,
        }
        report_filename = generate_report(impact, pdm_data=pdm_data, erp_data=erp_data_for_report)
        report_url = f"/reports/{report_filename}"
        # Check if PDF was generated
        pdf_filename = report_filename.replace('.html', '.pdf')
        if (REPORTS_DIR / pdf_filename).exists():
            pdf_url = f"/reports/{pdf_filename}"
    except Exception as e:
        print(f"Report generation error: {e}")

    return {
        "success": True,
        "message": f"Analysis complete for: {text}",
        "parsed": parsed.model_dump(),
        "impact": impact.model_dump(),
        "report_url": report_url,
        "pdf_url": pdf_url,
        "cad_result": cad_result,
        "fusion_connected": fusion_bridge.is_connected,
        # PDM data
        "pdm": {
            "revision": pdm_revision,
            "bom_impact": bom_impact,
        },
        # ERP data
        "erp": {
            "change_order": erp_change_order,
            "manufacturing_orders": erp_orders,
            "inventory_impact": inventory_impact,
        },
    }


# ═══════════════════════════════════════════════════════════
#  PDM ENDPOINTS
# ═══════════════════════════════════════════════════════════

@app.get("/api/pdm/bom")
async def get_bom():
    return pdm_manager.get_full_bom()

@app.get("/api/pdm/revisions/{part_name}")
async def get_revisions(part_name: str):
    return pdm_manager.get_part_revision_history(part_name)

@app.get("/api/pdm/metadata/{part_name}")
async def get_metadata(part_name: str):
    data = pdm_manager.get_part_metadata(part_name)
    if not data:
        raise HTTPException(status_code=404, detail=f"No CAD metadata for '{part_name}'")
    return data

@app.get("/api/pdm/profile/{part_name}")
async def get_pdm_profile(part_name: str):
    return pdm_manager.get_part_full_profile(part_name)


# ═══════════════════════════════════════════════════════════
#  ERP ENDPOINTS
# ═══════════════════════════════════════════════════════════

@app.get("/api/erp/orders")
async def get_orders():
    return erp_manager.get_all_orders()

@app.get("/api/erp/inventory")
async def get_inventory():
    return erp_manager.get_inventory_status()

@app.get("/api/erp/costs")
async def get_costs(change_id: str = None):
    return erp_manager.get_cost_summary(change_id)

@app.get("/api/erp/workflow")
async def get_workflow():
    return erp_manager.get_change_orders()

@app.post("/api/erp/workflow/{change_id}")
async def advance_workflow(change_id: str, action: str = "submit"):
    return erp_manager.advance_workflow(change_id, action)

@app.get("/api/erp/suppliers")
async def get_suppliers():
    return {"suppliers": db.get_suppliers()}


# ═══════════════════════════════════════════════════════════
#  UTILITY ENDPOINTS
# ═══════════════════════════════════════════════════════════

@app.post("/api/parse")
async def parse_only(request: ChangeRequest):
    known_parts = db.get_all_part_names()
    parsed = parse_change_request(request.text, known_parts)
    return {"success": True, "parsed": parsed}

@app.get("/api/history")
async def get_history():
    history = db.get_change_history()
    return {"history": history, "total": len(history)}

@app.get("/api/status")
async def get_status():
    fusion_status = fusion_bridge.check_connection()
    return {
        "status": "running",
        "version": "3.0.0",
        "fusion_connected": fusion_status.get("connected", False),
        "fusion_version": fusion_status.get("version"),
        "fusion_design": fusion_status.get("design_name"),
        "parts_in_db": len(db.get_all_parts()),
        "modules": ["analyzer", "pdm", "erp"],
    }


# ─── Helpers ──────────────────────────────────────────────

def _sync_fusion_parts(components: list, parameters: list):
    for comp in components:
        name = comp.get("name", "")
        if not name or name in ("Gearbox Assembly", "Root"):
            continue
        existing = db.get_part_by_name(name)
        if not existing:
            part_id = f"FSN-{uuid.uuid4().hex[:6].upper()}"
            db.upsert_part({
                "id": part_id, "name": name,
                "description": f"Fusion 360 component: {name}",
                "material": comp.get("material", "Unknown"),
                "category": "fusion", "parameters": {},
                "source": "fusion",
            })


# ─── Run Server ──────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=[str(PROJECT_ROOT / "backend")],
    )
