"""
Report Generator — Renders HTML change impact reports and generates PDF downloads.
Uses Jinja2 for HTML templating and xhtml2pdf for PDF conversion.
"""

from pathlib import Path
from datetime import datetime
from io import BytesIO

from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
REPORTS_DIR = Path(__file__).parent.parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))

# Try to import xhtml2pdf for PDF generation
try:
    from xhtml2pdf import pisa
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    print("  [WARN] xhtml2pdf not installed — PDF generation disabled (pip install xhtml2pdf)")


def _build_context(impact, pdm_data=None, erp_data=None) -> dict:
    """Build template context from impact object and optional PDM/ERP data."""
    parsed = impact.parsed_instruction
    
    context = {
        "change_id": impact.change_id,
        "timestamp": impact.timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "original_text": parsed.original_text,
        "target_part": impact.target_part,
        "action": parsed.action,
        "parameter": parsed.parameter,
        "value": parsed.value,
        "unit": parsed.unit,
        "material_value": parsed.material_value,
        "confidence": parsed.confidence,
        "fusion_parameter": parsed.fusion_parameter,
        # Classification
        "classification": impact.classification.value if hasattr(impact.classification, 'value') else str(impact.classification),
        "risk_level": impact.risk_level.value if hasattr(impact.risk_level, 'value') else str(impact.risk_level),
        "effort_hours": impact.effort_hours,
        "total_affected_count": impact.total_affected_count,
        # Parameter change
        "param_changed": impact.param_changed,
        "old_expression": impact.old_expression,
        "new_expression": impact.new_expression,
        # Fusion design info
        "fusion_design": impact.fusion_design,
        "fusion_connected": impact.fusion_connected,
        # Metrics
        "before_metrics": impact.before_metrics,
        "after_metrics": impact.after_metrics,
        # Lists
        "affected_parts": [
            {
                "part_name": p.part_name,
                "relationship": p.relationship,
                "impact_description": p.impact_description,
                "severity": p.severity,
                "severity_score": getattr(p, 'severity_score', 50),
            }
            for p in impact.affected_parts
        ],
        "bom_impacts": [
            {
                "impact_type": b.impact_type,
                "description": b.description,
                "estimated_change": b.estimated_change,
            }
            for b in impact.bom_impacts
        ],
        "document_impacts": [
            {
                "doc_type": d.doc_type,
                "doc_title": d.doc_title,
                "action_required": d.action_required,
            }
            for d in impact.document_impacts
        ],
        "recommendations": impact.recommendations,
        # PDM data
        "pdm_revision": pdm_data.get("revision") if pdm_data else None,
        "bom_impact_pdm": pdm_data.get("bom_impact") if pdm_data else None,
        # ERP data
        "erp_change_order": erp_data.get("change_order") if erp_data else None,
        "erp_manufacturing": erp_data.get("manufacturing_orders") if erp_data else None,
        "erp_inventory": erp_data.get("inventory_impact") if erp_data else None,
        # PDF URL (will be set after generation)
        "pdf_url": None,
    }
    
    return context


def generate_report(impact, pdm_data=None, erp_data=None) -> str:
    """Generate an HTML report and return the filename."""
    template = env.get_template("report_template.html")
    context = _build_context(impact, pdm_data, erp_data)
    
    # Set PDF URL if available
    if PDF_AVAILABLE:
        context["pdf_url"] = f"/reports/ECR_{impact.change_id}.pdf"
    
    html = template.render(**context)

    filename = f"ECR_{impact.change_id}.html"
    filepath = REPORTS_DIR / filename
    filepath.write_text(html, encoding="utf-8")
    
    # Also generate PDF if available
    if PDF_AVAILABLE:
        try:
            _generate_pdf(html, impact.change_id)
        except Exception as e:
            print(f"  [WARN] PDF generation failed: {e}")

    return filename


def _generate_pdf(html_content: str, change_id: str) -> str:
    """Convert HTML report to PDF using xhtml2pdf."""
    if not PDF_AVAILABLE:
        return ""
    
    # Modify HTML for PDF compatibility (xhtml2pdf has limited CSS support)
    # Replace gradient text with solid colors, simplify some styles
    pdf_html = html_content
    # Remove download bar from PDF
    pdf_html = pdf_html.replace('class="download-bar"', 'class="download-bar" style="display:none;"')
    # Replace gradient text fill with solid color
    pdf_html = pdf_html.replace('-webkit-background-clip: text; -webkit-text-fill-color: transparent;', 'color: #3b82f6;')
    pdf_html = pdf_html.replace('-webkit-text-fill-color: unset; background: none;', '')
    
    pdf_filename = f"ECR_{change_id}.pdf"
    pdf_path = REPORTS_DIR / pdf_filename
    
    with open(pdf_path, "wb") as pdf_file:
        pisa_status = pisa.CreatePDF(
            pdf_html,
            dest=pdf_file,
            encoding='utf-8',
        )
    
    if pisa_status.err:
        print(f"  [WARN] PDF had {pisa_status.err} errors during conversion")
    else:
        print(f"  [OK] PDF report generated: {pdf_filename}")
    
    return pdf_filename
