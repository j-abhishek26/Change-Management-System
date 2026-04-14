/**
 * Three.js 3D Model Viewer for Engineering Change Management System
 * Renders STL models in before/after split view with orbit controls
 * and dimension annotations (bounding box, volume, surface area).
 */

import * as THREE from 'three';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

// ─── Viewer Instances ────────────────────────────────────

const viewers = {};

function createViewer(canvasId, containerId, placeholderId) {
    const canvas = document.getElementById(canvasId);
    const container = document.getElementById(containerId);
    const placeholder = document.getElementById(placeholderId);

    if (!canvas || !container) return null;

    // Scene
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0a0c14);

    // Camera
    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 10000);
    camera.position.set(150, 100, 150);

    // Renderer
    const renderer = new THREE.WebGLRenderer({
        canvas,
        antialias: true,
        alpha: false,
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.2;

    // Controls
    const controls = new OrbitControls(camera, canvas);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.minDistance = 10;
    controls.maxDistance = 2000;
    controls.autoRotate = false;
    controls.autoRotateSpeed = 1.0;

    // Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.4);
    scene.add(ambientLight);

    const dirLight1 = new THREE.DirectionalLight(0xffffff, 0.8);
    dirLight1.position.set(100, 200, 100);
    dirLight1.castShadow = true;
    scene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0x4488ff, 0.3);
    dirLight2.position.set(-100, 50, -100);
    scene.add(dirLight2);

    const hemisphereLight = new THREE.HemisphereLight(0x6688cc, 0x222233, 0.3);
    scene.add(hemisphereLight);

    // Grid helper
    const grid = new THREE.GridHelper(300, 30, 0x1a1e2a, 0x12141c);
    grid.material.opacity = 0.5;
    grid.material.transparent = true;
    scene.add(grid);

    // Current mesh reference
    let currentMesh = null;

    // Dimension lines group
    let dimensionGroup = new THREE.Group();
    dimensionGroup.name = 'dimensions';
    scene.add(dimensionGroup);

    // Store geometry metrics
    let metrics = null;

    // Animation loop
    function animate() {
        requestAnimationFrame(animate);
        controls.update();
        renderer.render(scene, camera);
    }
    animate();

    // Handle resize
    function resize() {
        const rect = container.getBoundingClientRect();
        const width = rect.width;
        const height = rect.height || 320;

        camera.aspect = width / height;
        camera.updateProjectionMatrix();
        renderer.setSize(width, height);
    }

    window.addEventListener('resize', resize);
    // Initial resize after a brief delay to let layout settle
    setTimeout(resize, 100);
    setTimeout(resize, 500);

    return { scene, camera, renderer, controls, container, placeholder, canvas, currentMesh, dimensionGroup, metrics, resize };
}

// ─── Initialize Viewers ──────────────────────────────────

function initViewers() {
    viewers.before = createViewer('canvasBefore', 'viewerBefore', 'beforePlaceholder');
    viewers.after = createViewer('canvasAfter', 'viewerAfter', 'afterPlaceholder');
}

// Wait for DOM
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initViewers);
} else {
    initViewers();
}

// ─── Create Dimension Lines ─────────────────────────────

function createDimensionLine(start, end, color, offset, label) {
    const group = new THREE.Group();
    group.name = `dim_${label}`;

    const dir = new THREE.Vector3().subVectors(end, start);
    const length = dir.length();

    // Main measurement line
    const lineGeo = new THREE.BufferGeometry().setFromPoints([start, end]);
    const lineMat = new THREE.LineBasicMaterial({ color: color, linewidth: 2, transparent: true, opacity: 0.9 });
    const line = new THREE.Line(lineGeo, lineMat);
    group.add(line);

    // End caps (small perpendicular lines)
    const capSize = length * 0.04;
    const perpDir = new THREE.Vector3();

    // Determine perpendicular direction based on axis
    if (Math.abs(dir.x) > Math.abs(dir.y) && Math.abs(dir.x) > Math.abs(dir.z)) {
        perpDir.set(0, capSize, 0);
    } else if (Math.abs(dir.y) > Math.abs(dir.z)) {
        perpDir.set(capSize, 0, 0);
    } else {
        perpDir.set(0, capSize, 0);
    }

    const cap1Geo = new THREE.BufferGeometry().setFromPoints([
        start.clone().add(perpDir), start.clone().sub(perpDir)
    ]);
    const cap2Geo = new THREE.BufferGeometry().setFromPoints([
        end.clone().add(perpDir), end.clone().sub(perpDir)
    ]);
    group.add(new THREE.Line(cap1Geo, lineMat.clone()));
    group.add(new THREE.Line(cap2Geo, lineMat.clone()));

    // Arrow heads
    const arrowSize = length * 0.05;
    const arrowDir = dir.clone().normalize();

    // Arrow at start pointing towards end
    const arrow1 = createArrowHead(start, arrowDir, color, arrowSize);
    // Arrow at end pointing towards start
    const arrow2 = createArrowHead(end, arrowDir.clone().negate(), color, arrowSize);
    group.add(arrow1);
    group.add(arrow2);

    return group;
}

function createArrowHead(position, direction, color, size) {
    const arrowGeo = new THREE.ConeGeometry(size * 0.3, size, 6);
    const arrowMat = new THREE.MeshBasicMaterial({ color: color, transparent: true, opacity: 0.9 });
    const arrow = new THREE.Mesh(arrowGeo, arrowMat);

    arrow.position.copy(position);

    // Align cone to direction
    const up = new THREE.Vector3(0, 1, 0);
    const quat = new THREE.Quaternion().setFromUnitVectors(up, direction.clone().normalize());
    arrow.quaternion.copy(quat);

    return arrow;
}

// ─── Add Dimension Annotations ──────────────────────────

function addDimensions(viewer, bbox, viewerKey) {
    // Clear old dimensions
    while (viewer.dimensionGroup.children.length > 0) {
        const child = viewer.dimensionGroup.children[0];
        viewer.dimensionGroup.remove(child);
        if (child.geometry) child.geometry.dispose();
        if (child.material) child.material.dispose();
    }

    const size = new THREE.Vector3();
    bbox.getSize(size);
    const center = new THREE.Vector3();
    bbox.getCenter(center);

    // Since we center the geometry, min/max are symmetric
    const halfX = size.x / 2;
    const halfY = size.y / 2;
    const halfZ = size.z / 2;
    const yBase = halfY; // mesh.position.y offset

    // Color scheme
    const colors = {
        x: 0xff4466,  // Red for width (X)
        y: 0x44ff88,  // Green for height (Y)
        z: 0x4488ff,  // Blue for depth (Z)
    };

    // Offsets to push dimension lines outside the model
    const offsetFactor = 1.3;

    // Width (X-axis) — bottom front
    const xLine = createDimensionLine(
        new THREE.Vector3(-halfX, 0, halfZ * offsetFactor),
        new THREE.Vector3(halfX, 0, halfZ * offsetFactor),
        colors.x, 0, 'width'
    );
    viewer.dimensionGroup.add(xLine);

    // Height (Y-axis) — right front
    const yLine = createDimensionLine(
        new THREE.Vector3(halfX * offsetFactor, 0, halfZ * offsetFactor),
        new THREE.Vector3(halfX * offsetFactor, size.y, halfZ * offsetFactor),
        colors.y, 0, 'height'
    );
    viewer.dimensionGroup.add(yLine);

    // Depth (Z-axis) — bottom right
    const zLine = createDimensionLine(
        new THREE.Vector3(halfX * offsetFactor, 0, -halfZ),
        new THREE.Vector3(halfX * offsetFactor, 0, halfZ),
        colors.z, 0, 'depth'
    );
    viewer.dimensionGroup.add(zLine);

    return {
        width: size.x,
        height: size.y,
        depth: size.z,
    };
}

// ─── Compute Geometry Metrics ───────────────────────────

function computeMetrics(geometry) {
    geometry.computeBoundingBox();
    const bbox = geometry.boundingBox;
    const size = new THREE.Vector3();
    bbox.getSize(size);

    // Compute surface area from triangles
    const position = geometry.attributes.position;
    let surfaceArea = 0;
    let volume = 0;
    const pA = new THREE.Vector3(), pB = new THREE.Vector3(), pC = new THREE.Vector3();
    const cross = new THREE.Vector3();

    for (let i = 0; i < position.count; i += 3) {
        pA.fromBufferAttribute(position, i);
        pB.fromBufferAttribute(position, i + 1);
        pC.fromBufferAttribute(position, i + 2);

        // Surface area: sum of triangle areas
        const ab = new THREE.Vector3().subVectors(pB, pA);
        const ac = new THREE.Vector3().subVectors(pC, pA);
        cross.crossVectors(ab, ac);
        surfaceArea += cross.length() * 0.5;

        // Volume: signed volume of tetrahedron with origin
        volume += pA.dot(cross.crossVectors(
            new THREE.Vector3().subVectors(pB, pA),
            new THREE.Vector3().subVectors(pC, pA)
        )) / 6.0;
    }
    volume = Math.abs(volume);

    return {
        width: parseFloat(size.x.toFixed(2)),
        height: parseFloat(size.y.toFixed(2)),
        depth: parseFloat(size.z.toFixed(2)),
        surfaceArea: parseFloat(surfaceArea.toFixed(2)),
        volume: parseFloat(volume.toFixed(2)),
        triangles: position.count / 3,
    };
}

// ─── Update Dimension Overlay ───────────────────────────

function updateDimensionOverlay(viewerKey, metrics) {
    const overlayId = `dimOverlay_${viewerKey}`;
    let overlay = document.getElementById(overlayId);

    const container = viewerKey === 'before'
        ? document.getElementById('viewerBefore')
        : document.getElementById('viewerAfter');

    if (!container) return;

    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = overlayId;
        overlay.className = 'dim-overlay';
        container.appendChild(overlay);
    }

    const accentColor = viewerKey === 'before' ? '#4488cc' : '#44cc88';

    overlay.innerHTML = `
        <div class="dim-row" style="border-left-color: #ff4466;">
            <span class="dim-label">Width (X)</span>
            <span class="dim-value">${metrics.width.toFixed(1)} mm</span>
        </div>
        <div class="dim-row" style="border-left-color: #44ff88;">
            <span class="dim-label">Height (Y)</span>
            <span class="dim-value">${metrics.height.toFixed(1)} mm</span>
        </div>
        <div class="dim-row" style="border-left-color: #4488ff;">
            <span class="dim-label">Depth (Z)</span>
            <span class="dim-value">${metrics.depth.toFixed(1)} mm</span>
        </div>
        <div class="dim-separator"></div>
        <div class="dim-row">
            <span class="dim-label">Volume</span>
            <span class="dim-value">${formatNumber(metrics.volume)} mm³</span>
        </div>
        <div class="dim-row">
            <span class="dim-label">Surface Area</span>
            <span class="dim-value">${formatNumber(metrics.surfaceArea)} mm²</span>
        </div>
        <div class="dim-row dim-minor">
            <span class="dim-label">Triangles</span>
            <span class="dim-value">${metrics.triangles.toLocaleString()}</span>
        </div>
    `;
}

function formatNumber(num) {
    if (num >= 1e6) return (num / 1e6).toFixed(2) + 'M';
    if (num >= 1e3) return (num / 1e3).toFixed(1) + 'K';
    return num.toFixed(1);
}

// ─── Update Comparison Panel ────────────────────────────

function updateComparisonPanel() {
    const panel = document.getElementById('geometryComparison');
    if (!panel) return;

    const beforeMetrics = viewers.before?.metrics;
    const afterMetrics = viewers.after?.metrics;

    if (!beforeMetrics || !afterMetrics) {
        panel.style.display = 'none';
        return;
    }

    panel.style.display = 'block';

    function pctChange(before, after) {
        if (before === 0) return '—';
        const pct = ((after - before) / before * 100);
        const sign = pct > 0 ? '+' : '';
        const color = Math.abs(pct) < 0.1 ? '#6b7089' : pct < 0 ? '#f87171' : '#4ade80';
        return `<span style="color:${color}; font-weight:600;">${sign}${pct.toFixed(1)}%</span>`;
    }

    panel.innerHTML = `
        <div class="comparison-header">
            <span class="comparison-icon">📐</span>
            <span class="comparison-title">Geometry Change Summary</span>
        </div>
        <div class="comparison-grid">
            <div class="comp-head"></div>
            <div class="comp-head" style="color:#4488cc;">Before</div>
            <div class="comp-head" style="color:#44cc88;">After</div>
            <div class="comp-head">Change</div>

            <div class="comp-label">Width (X)</div>
            <div class="comp-val">${beforeMetrics.width.toFixed(1)} mm</div>
            <div class="comp-val">${afterMetrics.width.toFixed(1)} mm</div>
            <div class="comp-val">${pctChange(beforeMetrics.width, afterMetrics.width)}</div>

            <div class="comp-label">Height (Y)</div>
            <div class="comp-val">${beforeMetrics.height.toFixed(1)} mm</div>
            <div class="comp-val">${afterMetrics.height.toFixed(1)} mm</div>
            <div class="comp-val">${pctChange(beforeMetrics.height, afterMetrics.height)}</div>

            <div class="comp-label">Depth (Z)</div>
            <div class="comp-val">${beforeMetrics.depth.toFixed(1)} mm</div>
            <div class="comp-val">${afterMetrics.depth.toFixed(1)} mm</div>
            <div class="comp-val">${pctChange(beforeMetrics.depth, afterMetrics.depth)}</div>

            <div class="comp-label">Volume</div>
            <div class="comp-val">${formatNumber(beforeMetrics.volume)} mm³</div>
            <div class="comp-val">${formatNumber(afterMetrics.volume)} mm³</div>
            <div class="comp-val">${pctChange(beforeMetrics.volume, afterMetrics.volume)}</div>

            <div class="comp-label">Surface Area</div>
            <div class="comp-val">${formatNumber(beforeMetrics.surfaceArea)} mm²</div>
            <div class="comp-val">${formatNumber(afterMetrics.surfaceArea)} mm²</div>
            <div class="comp-val">${pctChange(beforeMetrics.surfaceArea, afterMetrics.surfaceArea)}</div>
        </div>
    `;
}


// ─── Load STL Model ──────────────────────────────────────

function loadSTL(url, viewerKey) {
    const viewer = viewers[viewerKey];
    if (!viewer) {
        console.warn(`Viewer '${viewerKey}' not initialized`);
        return;
    }

    const loader = new STLLoader();

    loader.load(
        url,
        (geometry) => {
            // Remove existing mesh
            if (viewer.currentMesh) {
                viewer.scene.remove(viewer.currentMesh);
                viewer.currentMesh.geometry.dispose();
                viewer.currentMesh.material.dispose();
            }

            // Clear old dimension group
            while (viewer.dimensionGroup.children.length > 0) {
                const child = viewer.dimensionGroup.children[0];
                viewer.dimensionGroup.remove(child);
                if (child.geometry) child.geometry.dispose();
                if (child.material) child.material.dispose();
            }

            // Remove old sprites (SIMULATED label etc.)
            const spritesToRemove = [];
            viewer.scene.traverse(child => { if (child.isSprite) spritesToRemove.push(child); });
            spritesToRemove.forEach(s => { viewer.scene.remove(s); if (s.material) s.material.dispose(); });

            // Material
            const color = viewerKey === 'before' ? 0x4488cc : 0x44cc88;
            const material = new THREE.MeshPhysicalMaterial({
                color: color,
                metalness: 0.2,
                roughness: 0.4,
                clearcoat: 0.1,
                clearcoatRoughness: 0.3,
                side: THREE.DoubleSide,
            });

            const mesh = new THREE.Mesh(geometry, material);
            mesh.castShadow = true;
            mesh.receiveShadow = true;

            // Center the geometry
            geometry.computeBoundingBox();
            const bbox = geometry.boundingBox;
            const center = new THREE.Vector3();
            bbox.getCenter(center);
            geometry.translate(-center.x, -center.y, -center.z);

            // ── AUTO-NORMALIZE: match After to Before's coordinate space ──
            // Fusion 360 can export modified STLs at a different scale (cm vs mm, etc.)
            // Detect this by comparing bounding boxes and auto-correct.
            if (viewerKey === 'after' && viewers.before?.metrics) {
                geometry.computeBoundingBox();
                const afterSize = new THREE.Vector3();
                geometry.boundingBox.getSize(afterSize);

                const beforeMetrics = viewers.before.metrics;
                const beforeMaxDim = Math.max(beforeMetrics.width, beforeMetrics.height, beforeMetrics.depth);
                const afterMaxDim = Math.max(afterSize.x, afterSize.y, afterSize.z);

                if (beforeMaxDim > 0 && afterMaxDim > 0) {
                    const ratio = afterMaxDim / beforeMaxDim;

                    // If ratio is far from 1.0 (more than 30% difference),
                    // it's likely a unit mismatch, not an actual modification
                    if (ratio > 1.3 || ratio < 0.7) {
                        const normalizeScale = beforeMaxDim / afterMaxDim;
                        geometry.scale(normalizeScale, normalizeScale, normalizeScale);
                        console.log(`🔧 Auto-normalized After STL: scale ratio was ${ratio.toFixed(2)}x, applied ${normalizeScale.toFixed(4)}x correction`);
                    }
                }
            }

            // Recompute after centering (and possible normalization)
            geometry.computeBoundingBox();
            const centeredBbox = geometry.boundingBox;

            // Move mesh so bottom sits on grid
            const yOffset = (centeredBbox.max.y - centeredBbox.min.y) / 2;
            mesh.position.y = yOffset;

            viewer.scene.add(mesh);
            viewer.currentMesh = mesh;

            // Compute and store metrics
            const metrics = computeMetrics(geometry);
            viewer.metrics = metrics;

            // Add dimension lines
            addDimensions(viewer, centeredBbox, viewerKey);

            // Add dimension overlay panel
            updateDimensionOverlay(viewerKey, metrics);

            // Update comparison if both loaded
            updateComparisonPanel();

            // Fit camera to model
            const size = new THREE.Vector3();
            centeredBbox.getSize(size);
            const maxDim = Math.max(size.x, size.y, size.z);
            const distance = maxDim * 2.8; // Slightly further out to show dimension lines

            viewer.camera.position.set(distance * 0.7, distance * 0.5, distance * 0.7);
            viewer.controls.target.set(0, yOffset, 0);
            viewer.controls.update();

            // Show canvas, hide placeholder
            viewer.canvas.style.display = 'block';
            viewer.placeholder.style.display = 'none';

            // Trigger resize
            viewer.resize();

            console.log(`✅ Loaded STL: ${url} (${viewerKey}) — ${metrics.width.toFixed(1)} × ${metrics.height.toFixed(1)} × ${metrics.depth.toFixed(1)} mm`);
        },
        (progress) => {
            // Loading progress (optional)
        },
        (error) => {
            console.error(`❌ Failed to load STL: ${url}`, error);
        }
    );
}

// ─── Simulated After Viewer ─────────────────────────────
// When Fusion 360 is offline, clone the before model and apply
// visual transforms to represent the modification.
// Uses the SAME metrics pipeline as loadSTL for consistency.

function loadSTLSimulated(url, viewerKey, action, parameter, value) {
    const viewer = viewers[viewerKey];
    if (!viewer) return;

    const loader = new STLLoader();
    loader.load(url, (geometry) => {
        // Remove existing mesh (same as loadSTL)
        if (viewer.currentMesh) {
            viewer.scene.remove(viewer.currentMesh);
            viewer.currentMesh.geometry.dispose();
            viewer.currentMesh.material.dispose();
        }

        // Clear old dimension lines, sprites, extra lines
        while (viewer.dimensionGroup.children.length > 0) {
            const child = viewer.dimensionGroup.children[0];
            viewer.dimensionGroup.remove(child);
            if (child.geometry) child.geometry.dispose();
            if (child.material) child.material.dispose();
        }
        // Also remove any leftover sprites/lines from previous simulated loads
        const toRemove = [];
        viewer.scene.traverse(child => {
            if (child.isSprite) toRemove.push(child);
        });
        toRemove.forEach(obj => {
            viewer.scene.remove(obj);
            if (obj.material) obj.material.dispose();
        });

        // Remove old metrics-hud DOM elements
        const container = viewer.canvas.parentElement;
        const oldHud = container.querySelector('.metrics-hud');
        if (oldHud) oldHud.remove();

        // Center geometry (same as loadSTL)
        geometry.computeBoundingBox();
        const bb = geometry.boundingBox;
        const center = new THREE.Vector3();
        bb.getCenter(center);
        geometry.translate(-center.x, -center.y, -center.z);

        // ── Apply simulated transforms based on action/parameter ──
        const scale = new THREE.Vector3(1, 1, 1);
        const safeVal = value || 2;

        if (action === 'REDUCE') {
            if (parameter === 'wall_thickness' || parameter === 'thickness') {
                const factor = 1 - (safeVal * 0.02);
                scale.set(factor, 1, factor);
            } else if (parameter === 'height') {
                scale.setY(1 - safeVal * 0.015);
            } else if (parameter === 'diameter' || parameter === 'outer_diameter') {
                scale.set(1 - safeVal * 0.015, 1, 1 - safeVal * 0.015);
            } else {
                scale.multiplyScalar(1 - safeVal * 0.01);
            }
        } else if (action === 'INCREASE') {
            if (parameter === 'face_width' || parameter === 'width') {
                scale.setZ(1 + safeVal * 0.015);
            } else if (parameter === 'height') {
                scale.setY(1 + safeVal * 0.015);
            } else if (parameter === 'diameter' || parameter === 'outer_diameter') {
                scale.set(1 + safeVal * 0.015, 1, 1 + safeVal * 0.015);
            } else {
                scale.multiplyScalar(1 + safeVal * 0.01);
            }
        } else if (action === 'CHANGE') {
            scale.multiplyScalar(1 + safeVal * 0.005);
        }

        geometry.scale(scale.x, scale.y, scale.z);

        // ── Create mesh with green "modified" material ──
        const material = new THREE.MeshPhysicalMaterial({
            color: 0x44cc88,
            metalness: 0.2,
            roughness: 0.4,
            clearcoat: 0.1,
            clearcoatRoughness: 0.3,
            side: THREE.DoubleSide,
        });

        const mesh = new THREE.Mesh(geometry, material);
        mesh.castShadow = true;
        mesh.receiveShadow = true;

        // Recompute after scaling
        geometry.computeBoundingBox();
        const centeredBbox = geometry.boundingBox;

        // Move mesh so bottom sits on grid (same as loadSTL)
        const yOffset = (centeredBbox.max.y - centeredBbox.min.y) / 2;
        mesh.position.y = yOffset;

        viewer.scene.add(mesh);
        viewer.currentMesh = mesh;

        // ── Use the SAME metrics pipeline as loadSTL ──
        const metrics = computeMetrics(geometry);
        viewer.metrics = metrics;

        // Add dimension lines (same function as Before viewer)
        addDimensions(viewer, centeredBbox, viewerKey);

        // Add dimension overlay panel (same function as Before viewer)
        updateDimensionOverlay(viewerKey, metrics);

        // Update comparison panel (shows Before vs After with % change)
        updateComparisonPanel();

        // ── Fit camera ──
        const size = new THREE.Vector3();
        centeredBbox.getSize(size);
        const maxDim = Math.max(size.x, size.y, size.z);
        const distance = maxDim * 2.8;

        viewer.camera.position.set(distance * 0.7, distance * 0.5, distance * 0.7);
        viewer.controls.target.set(0, yOffset, 0);
        viewer.controls.update();

        // Show canvas, hide placeholder
        viewer.canvas.style.display = 'block';
        viewer.placeholder.style.display = 'none';
        viewer.resize();

        // ── Add "SIMULATED" label as floating sprite ──
        addSimulatedLabel(viewer, centeredBbox);

        console.log(`✅ Loaded simulated After: ${action} ${parameter} by ${value} — ${metrics.width.toFixed(1)} × ${metrics.height.toFixed(1)} × ${metrics.depth.toFixed(1)} mm`);
    },
    undefined,
    (error) => {
        console.error(`❌ Failed to load simulated STL: ${url}`, error);
    });
}

function addSimulatedLabel(viewer, bbox) {
    const canvas = document.createElement('canvas');
    canvas.width = 256;
    canvas.height = 48;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = 'rgba(234, 179, 8, 0.85)';
    ctx.roundRect(0, 0, 256, 48, 8);
    ctx.fill();
    ctx.font = 'bold 18px sans-serif';
    ctx.fillStyle = '#000';
    ctx.textAlign = 'center';
    ctx.fillText('⚡ SIMULATED', 128, 32);

    const texture = new THREE.CanvasTexture(canvas);
    const spriteMat = new THREE.SpriteMaterial({ map: texture, depthTest: false });
    const sprite = new THREE.Sprite(spriteMat);

    // Position above the model
    const topY = bbox.max.y + (bbox.max.y - bbox.min.y) * 0.3;
    sprite.position.set(0, topY + 5, 0);
    sprite.scale.set(4, 0.75, 1);
    viewer.scene.add(sprite);
}

// ─── Export to Global Scope ──────────────────────────────

window.loadSTL = loadSTL;
window.loadSTLSimulated = loadSTLSimulated;

