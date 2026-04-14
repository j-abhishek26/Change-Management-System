/**
 * app.js — Engineering Change Management System v3.0
 * Frontend logic for Analyzer, PDM, and ERP tabs.
 */

// ─── State ──────────────────────────────────────────────
let currentReportUrl = null;
let currentPdfUrl = null;
let currentStepUrl = null;
let selectedPartName = null;

// ─── Tab Navigation ─────────────────────────────────────

function switchTab(tabName) {
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
    document.getElementById(`tab-${tabName}`).classList.add('active');

    // Auto-load data when switching tabs
    if (tabName === 'pdm') loadPDMData();
    if (tabName === 'erp') loadERPData();
}

// ─── Toast Notifications ────────────────────────────────

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => { toast.classList.add('show'); }, 10);
    setTimeout(() => { toast.classList.remove('show'); setTimeout(() => toast.remove(), 300); }, 3500);
}

function showLoading(text = 'Processing...') {
    document.getElementById('loadingText').textContent = text;
    document.getElementById('loadingOverlay').style.display = 'flex';
}

function hideLoading() {
    document.getElementById('loadingOverlay').style.display = 'none';
}

// ─── Fusion 360 Connection ──────────────────────────────

async function connectFusion() {
    showLoading('Connecting to Fusion 360...');
    try {
        const res = await fetch('/api/fusion/connect');
        const data = await res.json();
        if (data.connected) {
            document.getElementById('cadBadge').textContent = 'Fusion 360 Live';
            document.getElementById('cadBadge').className = 'cad-badge fusion-live';
            document.getElementById('statusDot').style.background = 'var(--accent-green)';
            document.getElementById('statusDot').style.boxShadow = '0 0 8px rgba(34,197,94,0.5)';
            document.getElementById('statusText').textContent = data.design?.design_name || 'Connected';
            document.getElementById('fusionConnectBtn').textContent = '✅ Connected';
            document.getElementById('fusionLiveTag').style.display = 'inline';
            showToast(`Connected: ${data.design?.design_name}`, 'success');
            if (data.parameters?.length) renderFusionParams(data.parameters);
        } else {
            showToast(data.message || 'Connection failed', 'error');
        }
    } catch (e) {
        showToast('Cannot reach server', 'error');
    }
    hideLoading();
}

function renderFusionParams(params) {
    const card = document.getElementById('fusionParamsCard');
    const list = document.getElementById('fusionParamsList');
    if (!params.length) return;
    card.style.display = 'block';
    list.innerHTML = params.slice(0, 20).map(p => `
        <div class="param-item">
            <span class="param-name">${p.name}</span>
            <span class="param-value">${p.expression}</span>
        </div>
    `).join('');
}

async function refreshParams() {
    try {
        const res = await fetch('/api/fusion/parameters');
        const data = await res.json();
        if (data.parameters) renderFusionParams(data.parameters);
    } catch (e) {}
}

// ─── Load Demo ──────────────────────────────────────────

async function loadDemo() {
    showLoading('Loading demo parts...');
    try {
        const res = await fetch('/api/demo/load', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            renderPartsList(data.parts);
            populatePDMSelectors(data.parts);
            showToast(data.message, 'success');
        }
    } catch (e) {
        showToast('Failed to load demo', 'error');
    }
    hideLoading();
}

// ─── Parts List ─────────────────────────────────────────

function renderPartsList(parts) {
    const container = document.getElementById('partsList');
    container.innerHTML = parts.map(p => `
        <div class="part-item ${selectedPartName === p.name ? 'selected' : ''}"
             onclick="selectPart('${p.name}')">
            <div class="part-dot"></div>
            <div class="part-info">
                <div class="part-name">${p.name}</div>
                <div class="part-material">${p.material || 'Unknown'}</div>
            </div>
        </div>
    `).join('');
}

function selectPart(name) {
    selectedPartName = name;
    document.querySelectorAll('.part-item').forEach(el => el.classList.remove('selected'));
    event?.target?.closest('.part-item')?.classList.add('selected');
    
    // Try to load STL
    const safeName = name.replace(/ /g, '_');
    window.loadSTL?.(`/outputs/${safeName}_original.stl`, 'before');
    showToast(`Selected: ${name}`, 'info');
}

function setExample(text) {
    document.getElementById('changeInput').value = text;
}

// ─── View Mode ──────────────────────────────────────────

function setViewMode(mode) {
    document.querySelectorAll('.viewer-tab').forEach(t => t.classList.remove('active'));
    event.target.classList.add('active');
    const before = document.getElementById('viewerBefore');
    const after = document.getElementById('viewerAfter');
    const container = document.getElementById('viewerContainer');
    if (mode === 'split') {
        container.style.gridTemplateColumns = '1fr 1fr';
        before.style.display = 'flex'; after.style.display = 'flex';
    } else if (mode === 'before') {
        container.style.gridTemplateColumns = '1fr';
        before.style.display = 'flex'; after.style.display = 'none';
    } else {
        container.style.gridTemplateColumns = '1fr';
        before.style.display = 'none'; after.style.display = 'flex';
    }
}

// ─── Core Analysis ──────────────────────────────────────

async function analyzeChange() {
    const text = document.getElementById('changeInput').value.trim();
    if (!text) { showToast('Enter a change request first', 'error'); return; }

    showLoading('Analyzing change request...');
    try {
        const res = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text }),
        });
        const data = await res.json();
        if (data.success) {
            renderResults(data);
            showToast('Analysis complete!', 'success');
        } else {
            showToast(data.message || 'Analysis failed', 'error');
        }
    } catch (e) {
        showToast('Server error', 'error');
    }
    hideLoading();
}

// ─── Render Results ─────────────────────────────────────

function renderResults(data) {
    document.getElementById('resultsArea').style.display = 'flex';
    document.getElementById('resultsArea').style.flexDirection = 'column';
    document.getElementById('resultsArea').style.gap = '16px';
    document.getElementById('emptyResults').style.display = 'none';

    renderParseResult(data.parsed);
    renderParamChange(data.cad_result, data.impact);
    if (data.impact) renderImpact(data.impact);
    if (data.erp) renderERPResult(data.erp);

    // Load 3D models (cache-bust with timestamp to ensure fresh Fusion exports load)
    if (data.cad_result) {
        const cacheBust = `?t=${Date.now()}`;
        if (data.cad_result.original_stl) window.loadSTL?.(`/outputs/${data.cad_result.original_stl}${cacheBust}`, 'before');
        if (data.cad_result.modified_stl) {
            window.loadSTL?.(`/outputs/${data.cad_result.modified_stl}${cacheBust}`, 'after');
        } else if (data.cad_result.simulated && data.cad_result.original_stl) {
            // Simulation mode: load same STL for after with simulated transform
            window.loadSTLSimulated?.(
                `/outputs/${data.cad_result.original_stl}${cacheBust}`, 'after',
                data.parsed?.action, data.parsed?.parameter, data.parsed?.value
            );
        }
    }

    currentReportUrl = data.report_url;
    currentPdfUrl = data.pdf_url;
    currentStepUrl = data.cad_result?.modified_step ? `/outputs/${data.cad_result.modified_step}` : null;
    document.getElementById('downloadReport').disabled = !currentReportUrl;
    document.getElementById('downloadPdf').disabled = !currentPdfUrl;
    document.getElementById('downloadStep').disabled = !currentStepUrl;
}

function renderParseResult(parsed) {
    const container = document.getElementById('parseResult');
    const conf = parsed?.confidence || 0;
    const confPct = Math.round(conf * 100);

    container.innerHTML = `
        <div class="parse-item"><div class="parse-label">Action</div><div class="parse-value">${parsed?.action || '—'}</div></div>
        <div class="parse-item"><div class="parse-label">Target Part</div><div class="parse-value">${parsed?.target_part || '—'}</div></div>
        <div class="parse-item"><div class="parse-label">Parameter</div><div class="parse-value">${parsed?.parameter || '—'}</div></div>
        <div class="parse-item"><div class="parse-label">Value</div><div class="parse-value">${parsed?.value != null ? parsed.value + ' ' + (parsed.unit || 'mm') : '—'}</div></div>
    `;

    const badge = document.getElementById('confidenceBadge');
    badge.textContent = `${confPct}% Confidence`;
    badge.className = confPct >= 80 ? 'badge badge-low' : confPct >= 50 ? 'badge badge-medium' : 'badge badge-high';
    document.getElementById('confidenceFill').style.width = `${confPct}%`;
}

function renderParamChange(cadResult, impact) {
    const card = document.getElementById('paramChangeCard');
    const detail = document.getElementById('paramChangeDetail');

    const paramName = impact?.param_changed || cadResult?.param_changed;
    const oldExpr = impact?.old_expression || cadResult?.old_expression;
    const newExpr = impact?.new_expression || cadResult?.new_expression;

    if (paramName && oldExpr && newExpr) {
        card.style.display = 'block';
        detail.innerHTML = `
            <div class="param-change-row">
                <div class="param-change-name">${paramName}</div>
                <div class="param-change-values">
                    <span class="param-change-expr">${oldExpr}</span>
                    <span class="arrow-icon">→</span>
                    <span class="param-change-expr" style="color: var(--accent-green);">${newExpr}</span>
                </div>
            </div>
            <div style="font-size: 11px; color: var(--text-muted); margin-top: 8px;">
                ${cadResult?.simulated ? '⚡ Simulated modification (connect Fusion 360 for live CAD changes)' : '✅ Applied in Fusion 360'}
            </div>
        `;
    } else {
        card.style.display = 'none';
    }
}

function renderImpact(impact) {
    // Stats grid
    const stats = document.getElementById('impactStats');
    stats.innerHTML = `
        <div class="stat-card"><div class="stat-value">${impact.total_affected_count}</div><div class="stat-label">Affected Parts</div></div>
        <div class="stat-card"><div class="stat-value"><span class="badge badge-${impact.classification?.toLowerCase()}">${impact.classification}</span></div><div class="stat-label">Classification</div></div>
        <div class="stat-card"><div class="stat-value"><span class="badge badge-${impact.risk_level?.toLowerCase()}">${impact.risk_level}</span></div><div class="stat-label">Risk Level</div></div>
        <div class="stat-card"><div class="stat-value">${impact.effort_hours}h</div><div class="stat-label">Est. Effort</div></div>
    `;

    // Affected parts table
    if (impact.affected_parts?.length > 0) {
        document.getElementById('affectedSection').style.display = 'block';
        const tbody = document.getElementById('affectedBody');
        tbody.innerHTML = impact.affected_parts.map(ap => `
            <tr>
                <td><strong>${ap.part_name}</strong></td>
                <td><code>${ap.relationship}</code></td>
                <td><span class="badge badge-${ap.severity?.toLowerCase()}">${ap.severity}</span></td>
                <td><div class="severity-bar"><div class="severity-fill" style="width:${ap.severity_score}%;background:${ap.severity_score >= 70 ? 'var(--accent-red)' : ap.severity_score >= 35 ? 'var(--accent-orange)' : 'var(--accent-green)'}"></div><span>${ap.severity_score}</span></div></td>
                <td style="font-size:11px;color:var(--text-secondary);max-width:300px;">${ap.impact_description}</td>
            </tr>
        `).join('');
    }

    // Recommendations
    if (impact.recommendations?.length > 0) {
        document.getElementById('recsCard').style.display = 'block';
        document.getElementById('recsList').innerHTML = impact.recommendations.map(r =>
            `<li class="rec-item">${r}</li>`
        ).join('');
    }
}

function renderERPResult(erp) {
    const card = document.getElementById('erpResultCard');
    const content = document.getElementById('erpResultContent');
    if (!erp) return;
    card.style.display = 'block';

    let html = '<div class="erp-result-grid">';

    // Change Order
    if (erp.change_order) {
        const co = erp.change_order;
        html += `
            <div class="erp-result-item">
                <div class="erp-result-icon">📋</div>
                <div>
                    <div class="erp-result-title">Change Order Created</div>
                    <div class="erp-result-detail">${co.id} — Status: <span class="badge badge-${co.priority}">${co.status?.toUpperCase()}</span></div>
                </div>
            </div>
        `;
    }

    // Manufacturing Orders
    if (erp.manufacturing_orders?.orders?.length) {
        const orders = erp.manufacturing_orders;
        html += `
            <div class="erp-result-item">
                <div class="erp-result-icon">🏭</div>
                <div>
                    <div class="erp-result-title">${orders.total_orders} Manufacturing Orders</div>
                    <div class="erp-result-detail">Est. Cost: $${orders.total_estimated_cost} | Hours: ${orders.total_estimated_hours}h</div>
                </div>
            </div>
        `;
    }

    // Inventory Impact
    if (erp.inventory_impact?.impact !== 'none') {
        const inv = erp.inventory_impact;
        html += `
            <div class="erp-result-item ${inv.impact === 'high' ? 'erp-result-warning' : ''}">
                <div class="erp-result-icon">${inv.impact === 'high' ? '⚠️' : '📦'}</div>
                <div>
                    <div class="erp-result-title">Inventory Impact: ${inv.impact.toUpperCase()}</div>
                    <div class="erp-result-detail">${inv.message}${inv.scrap_cost ? ` Scrap cost: $${inv.scrap_cost}` : ''}</div>
                </div>
            </div>
        `;
    }

    html += '</div>';
    content.innerHTML = html;
}

// ─── Downloads ──────────────────────────────────────────

function downloadReport() {
    if (currentReportUrl) window.open(currentReportUrl, '_blank');
}

function downloadPdf() {
    if (currentPdfUrl) {
        const a = document.createElement('a');
        a.href = currentPdfUrl;
        a.download = '';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }
}

function downloadStep() {
    if (currentStepUrl) window.open(currentStepUrl, '_blank');
}


// ═══════════════════════════════════════════════════════════
//  PDM TAB
// ═══════════════════════════════════════════════════════════

function populatePDMSelectors(parts) {
    const select = document.getElementById('revPartSelect');
    if (!select) return;
    // Keep first option
    select.innerHTML = '<option value="">Select a part...</option>' +
        parts.map(p => `<option value="${p.name}">${p.name}</option>`).join('');
}

async function loadPDMData() {
    loadBOM();
    // Populate part selector if empty
    try {
        const res = await fetch('/api/parts');
        const data = await res.json();
        if (data.parts) populatePDMSelectors(data.parts);
    } catch (e) {}
}

async function loadBOM() {
    try {
        const res = await fetch('/api/pdm/bom');
        const data = await res.json();
        const container = document.getElementById('bomContent');

        if (!data.items?.length) {
            container.innerHTML = '<div class="empty-state" style="padding:20px;"><p>No BOM data. Load demo parts first.</p></div>';
            return;
        }

        container.innerHTML = `
            <div class="bom-summary">
                <div class="bom-stat"><span class="bom-stat-val">${data.total_items}</span><span class="bom-stat-lbl">Items</span></div>
                <div class="bom-stat"><span class="bom-stat-val">$${data.total_cost_usd.toFixed(2)}</span><span class="bom-stat-lbl">Total Cost</span></div>
                <div class="bom-stat"><span class="bom-stat-val">${data.total_weight_kg.toFixed(3)} kg</span><span class="bom-stat-lbl">Total Weight</span></div>
            </div>
            <table class="pdm-table">
                <thead><tr><th>Part</th><th>Material</th><th>Qty</th><th>Unit Cost</th><th>Total</th><th>Lead Time</th><th>Supplier</th><th>Make/Buy</th></tr></thead>
                <tbody>
                    ${data.items.map(i => `
                        <tr>
                            <td><strong>${i.name}</strong></td>
                            <td>${i.material || '—'}</td>
                            <td>${i.quantity}</td>
                            <td>$${(i.unit_cost || 0).toFixed(2)}</td>
                            <td><strong>$${(i.total_cost || 0).toFixed(2)}</strong></td>
                            <td>${i.lead_time_days}d</td>
                            <td>${i.supplier || '—'}</td>
                            <td><span class="badge badge-${i.make_or_buy === 'make' ? 'low' : 'medium'}">${i.make_or_buy}</span></td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    } catch (e) {
        showToast('Failed to load BOM', 'error');
    }
}

async function loadRevisions() {
    const partName = document.getElementById('revPartSelect').value;
    if (!partName) return;

    try {
        const res = await fetch(`/api/pdm/revisions/${encodeURIComponent(partName)}`);
        const data = await res.json();
        const container = document.getElementById('revisionContent');

        if (data.error) {
            container.innerHTML = `<div class="empty-state" style="padding:20px;"><p>${data.error}</p></div>`;
            return;
        }

        container.innerHTML = `
            <div style="margin-bottom:12px;">
                <span class="badge badge-low">Current: Rev ${data.current_revision}</span>
                <span style="font-size:11px;color:var(--text-muted);margin-left:8px;">${data.total_revisions} revision(s)</span>
            </div>
            ${data.revisions.map(r => `
                <div class="revision-item">
                    <div class="revision-badge">Rev ${r.revision}</div>
                    <div class="revision-info">
                        <div style="font-size:12px;font-weight:500;">${r.description || 'No description'}</div>
                        <div style="font-size:10px;color:var(--text-muted);">${r.author} • ${new Date(r.created_at).toLocaleDateString()} ${r.change_id ? `• ${r.change_id}` : ''}</div>
                    </div>
                    <span class="badge badge-${r.status === 'released' ? 'low' : 'medium'}">${r.status}</span>
                </div>
            `).join('')}
        `;

        // Also load metadata and docs
        loadMetadata(partName);
        loadDocRegistry(partName);
    } catch (e) {}
}

async function loadMetadata(partName) {
    try {
        const res = await fetch(`/api/pdm/metadata/${encodeURIComponent(partName)}`);
        if (!res.ok) return;
        const data = await res.json();
        const container = document.getElementById('metadataContent');

        container.innerHTML = `
            <div class="metadata-grid">
                <div class="meta-item"><span class="meta-label">Volume</span><span class="meta-value">${(data.volume_mm3 || 0).toLocaleString()} mm³</span></div>
                <div class="meta-item"><span class="meta-label">Surface Area</span><span class="meta-value">${(data.surface_area_mm2 || 0).toLocaleString()} mm²</span></div>
                <div class="meta-item"><span class="meta-label">Bbox Length</span><span class="meta-value">${data.bbox_length || 0} mm</span></div>
                <div class="meta-item"><span class="meta-label">Bbox Width</span><span class="meta-value">${data.bbox_width || 0} mm</span></div>
                <div class="meta-item"><span class="meta-label">Bbox Height</span><span class="meta-value">${data.bbox_height || 0} mm</span></div>
                <div class="meta-item"><span class="meta-label">Mass</span><span class="meta-value">${data.mass_kg || '—'} kg</span></div>
                <div class="meta-item"><span class="meta-label">Material</span><span class="meta-value">${data.material || '—'}</span></div>
                <div class="meta-item"><span class="meta-label">Units</span><span class="meta-value">${data.units || 'mm'}</span></div>
            </div>
        `;
    } catch (e) {}
}

async function loadDocRegistry(partName) {
    try {
        const res = await fetch(`/api/pdm/profile/${encodeURIComponent(partName)}`);
        const data = await res.json();
        const container = document.getElementById('docRegistryContent');

        if (!data.documents?.length) {
            container.innerHTML = '<div class="empty-state" style="padding:20px;"><p>No documents linked.</p></div>';
            return;
        }

        container.innerHTML = `
            <table class="pdm-table">
                <thead><tr><th>Title</th><th>Type</th><th>Revision</th><th>Status</th></tr></thead>
                <tbody>
                    ${data.documents.map(d => `
                        <tr>
                            <td>${d.title}</td>
                            <td><code>${d.doc_type}</code></td>
                            <td>Rev ${d.revision || 'A'}</td>
                            <td><span class="badge badge-low">${d.status || 'current'}</span></td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    } catch (e) {}
}


// ═══════════════════════════════════════════════════════════
//  ERP TAB
// ═══════════════════════════════════════════════════════════

async function loadERPData() {
    loadERPSummary();
    loadERPOrders();
    loadERPWorkflow();
    loadERPInventory();
    loadERPSuppliers();
}

async function loadERPSummary() {
    try {
        const [costsRes, invRes] = await Promise.all([
            fetch('/api/erp/costs'),
            fetch('/api/erp/inventory'),
        ]);
        const costs = await costsRes.json();
        const inv = await invRes.json();

        document.getElementById('erpOrderCount').textContent = costs.orders_count || 0;
        document.getElementById('erpTotalCost').textContent = `$${(costs.manufacturing_cost || 0).toFixed(0)}`;
        document.getElementById('erpBomCost').textContent = `$${(costs.bom_total_cost || 0).toFixed(2)}`;
        document.getElementById('erpLowStock').textContent = inv.low_stock_count || 0;
    } catch (e) {}
}

async function loadERPOrders() {
    try {
        const res = await fetch('/api/erp/orders');
        const data = await res.json();
        const container = document.getElementById('erpOrdersContent');

        if (!data.orders?.length) {
            container.innerHTML = '<div class="empty-state" style="padding:20px;"><p>No orders yet. Run an analysis to auto-generate.</p></div>';
            return;
        }

        container.innerHTML = data.orders.map(o => `
            <div class="order-item">
                <div class="order-header">
                    <span class="order-id">${o.id}</span>
                    <span class="badge badge-${o.priority === 'urgent' ? 'high' : o.priority === 'high' ? 'medium' : 'low'}">${o.priority}</span>
                    <span class="badge badge-${o.status === 'draft' ? 'medium' : o.status === 'completed' ? 'low' : 'high'}">${o.status}</span>
                </div>
                <div class="order-detail">
                    <span>${o.part_name || 'Unknown'} • ${o.order_type}</span>
                    <span>$${(o.estimated_cost || 0).toFixed(0)} • ${o.estimated_hours || 0}h</span>
                </div>
                ${o.notes ? `<div class="order-notes">${o.notes}</div>` : ''}
            </div>
        `).join('');
    } catch (e) {}
}

async function loadERPWorkflow() {
    try {
        const res = await fetch('/api/erp/workflow');
        const data = await res.json();
        const container = document.getElementById('erpWorkflowContent');

        if (!data.orders?.length) {
            container.innerHTML = '<div class="empty-state" style="padding:20px;"><p>No change orders yet.</p></div>';
            return;
        }

        container.innerHTML = data.orders.map(o => `
            <div class="workflow-item">
                <div class="workflow-header">
                    <span class="order-id">${o.change_id || o.id}</span>
                    <span class="badge badge-${o.status === 'draft' ? 'medium' : o.status === 'approved' ? 'low' : o.status === 'rejected' ? 'high' : 'medium'}">${o.status}</span>
                </div>
                <div class="workflow-title">${o.title || 'No title'}</div>
                <div class="workflow-meta">
                    ${o.classification ? `<span class="badge badge-${o.classification.toLowerCase()}">${o.classification}</span>` : ''}
                    ${o.risk_level ? `<span class="badge badge-${o.risk_level.toLowerCase()}">${o.risk_level}</span>` : ''}
                    <span style="font-size:11px;color:var(--text-muted);">${o.affected_count || 0} affected • $${(o.total_cost || 0).toFixed(0)}</span>
                </div>
                <div class="workflow-steps">
                    ${['draft','review','approved','in_progress','completed'].map(s => 
                        `<div class="wf-step ${o.status === s ? 'active' : ''} ${['draft','review','approved','in_progress','completed'].indexOf(s) < ['draft','review','approved','in_progress','completed'].indexOf(o.status) ? 'done' : ''}">${s.replace('_',' ')}</div>`
                    ).join('<div class="wf-arrow">→</div>')}
                </div>
            </div>
        `).join('');
    } catch (e) {}
}

async function loadERPInventory() {
    try {
        const res = await fetch('/api/erp/inventory');
        const data = await res.json();
        const container = document.getElementById('erpInventoryContent');

        if (!data.items?.length) {
            container.innerHTML = '<div class="empty-state" style="padding:20px;"><p>No inventory data. Load demo first.</p></div>';
            return;
        }

        container.innerHTML = `
            <table class="pdm-table">
                <thead><tr><th>Part</th><th>Stock</th><th>Min</th><th>Reorder</th><th>Location</th><th>Status</th></tr></thead>
                <tbody>
                    ${data.items.map(i => {
                        const low = (i.stock_quantity || 0) <= (i.reorder_point || 10);
                        return `
                            <tr class="${low ? 'row-warning' : ''}">
                                <td>${i.name}</td>
                                <td><strong>${i.stock_quantity}</strong></td>
                                <td>${i.min_stock}</td>
                                <td>${i.reorder_point}</td>
                                <td><code>${i.warehouse_location}</code></td>
                                <td>${low ? '<span class="badge badge-high">LOW</span>' : '<span class="badge badge-low">OK</span>'}</td>
                            </tr>
                        `;
                    }).join('')}
                </tbody>
            </table>
        `;
    } catch (e) {}
}

async function loadERPSuppliers() {
    try {
        const res = await fetch('/api/erp/suppliers');
        const data = await res.json();
        const container = document.getElementById('erpSuppliersContent');

        if (!data.suppliers?.length) {
            container.innerHTML = '<div class="empty-state" style="padding:20px;"><p>No supplier data.</p></div>';
            return;
        }

        container.innerHTML = `
            <table class="pdm-table">
                <thead><tr><th>Supplier</th><th>Contact</th><th>Materials</th><th>Lead Time</th><th>Rating</th></tr></thead>
                <tbody>
                    ${data.suppliers.map(s => `
                        <tr>
                            <td><strong>${s.name}</strong></td>
                            <td style="font-size:11px;">${s.contact || '—'}</td>
                            <td style="font-size:11px;">${s.material_types || '—'}</td>
                            <td>${s.lead_time_days}d</td>
                            <td>⭐ ${(s.rating || 0).toFixed(1)}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    } catch (e) {}
}
