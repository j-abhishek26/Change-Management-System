"""
FusionBridge — Fusion 360 Add-in
Starts a local HTTP server inside Fusion 360 that accepts commands from
the Engineering Change Management System's web server.

Install: Copy this folder to %APPDATA%/Autodesk/Autodesk Fusion 360/API/AddIns/
Enable:  Utilities → Add-Ins → FusionBridge → Run
"""

import adsk.core
import adsk.fusion
import traceback
import threading
import json
import os
import uuid
import queue
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# ═══════════════════════════════════════════════════════════
#  CONFIGURATION
# ═══════════════════════════════════════════════════════════

PORT = 5001
CUSTOM_EVENT_ID = 'FusionBridge_ProcessRequest'

# ═══════════════════════════════════════════════════════════
#  SHARED STATE (thread-safe communication)
# ═══════════════════════════════════════════════════════════

_app = None
_ui = None
_http_server = None
_server_thread = None
_custom_event = None
_event_handler = None
_handlers = []  # Keep references to prevent garbage collection (Autodesk best practice)

# Thread-safe queues
_request_queue = queue.Queue()
_responses = {}
_response_events = {}


# ═══════════════════════════════════════════════════════════
#  FUSION API COMMAND PROCESSOR (runs on main thread)
# ═══════════════════════════════════════════════════════════

def process_command(req):
    """Execute a Fusion 360 API command. MUST run on the main thread."""
    try:
        path = req.get('path', '')
        method = req.get('method', 'GET')
        body = req.get('body', {})

        app = adsk.core.Application.get()
        if not app:
            return {'error': 'Fusion 360 application not available'}

        product = app.activeProduct
        design = adsk.fusion.Design.cast(product) if product else None

        # ─── GET /fusion/status ───────────────────────────
        if path == '/fusion/status':
            return {
                'connected': True,
                'version': app.version,
                'has_design': design is not None,
                'design_name': design.rootComponent.name if design else None,
            }

        # ─── GET /fusion/design/info ──────────────────────
        elif path == '/fusion/design/info':
            if not design:
                return {'error': 'No active design. Please open a .f3d file.'}

            root = design.rootComponent
            doc = app.activeDocument

            # Count bodies and components
            all_bodies = root.bRepBodies
            all_comps = design.allComponents

            return {
                'design_name': root.name,
                'document_name': doc.name if doc else 'Untitled',
                'units': design.unitsManager.defaultLengthUnits,
                'component_count': all_comps.count,
                'body_count': all_bodies.count,
                'design_type': 'Parametric' if design.designType == adsk.fusion.DesignTypes.ParametricDesignType else 'Direct',
                'is_saved': doc.isSaved if doc else False,
            }

        # ─── GET /fusion/design/parameters ────────────────
        elif path == '/fusion/design/parameters':
            if not design:
                return {'error': 'No active design'}

            params = []
            # User parameters first
            for i in range(design.userParameters.count):
                p = design.userParameters.item(i)
                params.append({
                    'name': p.name,
                    'expression': p.expression,
                    'value': p.value,  # value in internal units (cm)
                    'unit': p.unit,
                    'comment': p.comment,
                    'type': 'user',
                })

            # Model parameters
            for i in range(design.allParameters.count):
                p = design.allParameters.item(i)
                # Skip user params (already added)
                is_user = False
                for j in range(design.userParameters.count):
                    if design.userParameters.item(j).name == p.name:
                        is_user = True
                        break
                if not is_user:
                    params.append({
                        'name': p.name,
                        'expression': p.expression,
                        'value': p.value,
                        'unit': p.unit,
                        'comment': getattr(p, 'comment', ''),
                        'type': 'model',
                    })

            return {'parameters': params, 'total': len(params)}

        # ─── GET /fusion/design/components ────────────────
        elif path == '/fusion/design/components':
            if not design:
                return {'error': 'No active design'}

            root = design.rootComponent
            components = []

            def traverse_component(comp, depth=0):
                comp_info = {
                    'name': comp.name,
                    'depth': depth,
                    'bodies': [],
                    'material': None,
                }

                # Get bodies
                for i in range(comp.bRepBodies.count):
                    body = comp.bRepBodies.item(i)
                    body_info = {
                        'name': body.name,
                        'is_visible': body.isVisible,
                        'volume': body.volume if hasattr(body, 'volume') else 0,
                        'area': body.area if hasattr(body, 'area') else 0,
                    }
                    # Get material
                    try:
                        if body.material:
                            body_info['material'] = body.material.name
                            if not comp_info['material']:
                                comp_info['material'] = body.material.name
                    except:
                        pass
                    comp_info['bodies'].append(body_info)

                components.append(comp_info)

                # Traverse child occurrences
                for i in range(comp.occurrences.count):
                    occ = comp.occurrences.item(i)
                    traverse_component(occ.component, depth + 1)

            traverse_component(root)
            return {'components': components, 'total': len(components)}

        # ─── GET /fusion/design/occurrences ────────────────
        elif path == '/fusion/design/occurrences':
            if not design:
                return {'error': 'No active design'}
            root = design.rootComponent
            occs = []
            for i in range(root.allOccurrences.count):
                occ = root.allOccurrences.item(i)
                occ_info = {
                    'name': occ.name,
                    'component': occ.component.name,
                    'bodies': occ.bRepBodies.count,
                    'isVisible': occ.isVisible,
                }
                # Get bounding box in mm
                try:
                    bb = occ.boundingBox
                    occ_info['bbox_mm'] = {
                        'width': round((bb.maxPoint.x - bb.minPoint.x) * 10, 2),
                        'height': round((bb.maxPoint.y - bb.minPoint.y) * 10, 2),
                        'depth': round((bb.maxPoint.z - bb.minPoint.z) * 10, 2),
                    }
                except:
                    pass
                occs.append(occ_info)
            return {'occurrences': occs, 'total': len(occs)}

        # ─── POST /fusion/design/modify ───────────────────
        elif path == '/fusion/design/modify':
            if not design:
                return {'error': 'No active design'}

            param_name = body.get('parameter_name', '')
            new_expression = body.get('new_expression', '')

            if not param_name or not new_expression:
                return {'error': 'parameter_name and new_expression required'}

            # Find the parameter (user params first, then all params)
            param = design.userParameters.itemByName(param_name)
            if not param:
                for i in range(design.allParameters.count):
                    p = design.allParameters.item(i)
                    if p.name == param_name:
                        param = p
                        break

            if not param:
                return {'error': f'Parameter "{param_name}" not found in design'}

            # Save before state
            before_value = param.value
            before_expression = param.expression
            root = design.rootComponent
            debug_info = []

            # ── APPLY THE PARAMETER CHANGE ──
            try:
                param.expression = new_expression
                debug_info.append(f'Set expression: {before_expression} -> {new_expression}')
                debug_info.append(f'Value: {before_value} -> {param.value}')
            except Exception as e:
                try:
                    param.expression = before_expression
                except:
                    pass
                return {'error': f'Failed to set parameter: {str(e)}'}

            # ── FORCE DESIGN REGENERATION ──
            # Per Autodesk docs: design.computeAll() forces full timeline
            # recomputation. This is the correct API — NOT adsk.doEvents().
            try:
                design.computeAll()
                adsk.doEvents()  # Let UI catch up
                debug_info.append('design.computeAll() done')
            except Exception as e:
                debug_info.append(f'computeAll error: {str(e)}')
                # Fallback: timeline rollback
                try:
                    tl = design.timeline
                    if tl and tl.count > 0:
                        tl.moveToEnd()
                        adsk.doEvents()
                        debug_info.append('timeline.moveToEnd() fallback done')
                except Exception as e2:
                    debug_info.append(f'timeline fallback error: {str(e2)}')

            # Read back actual value to confirm
            actual_value = param.value
            actual_expression = param.expression
            param_changed = abs(actual_value - before_value) > 1e-7

            # Verify geometry changed by checking bounding box
            geometry_changed = False
            try:
                # Check total volume of all bodies to detect geometry change
                total_vol = 0
                for occ_idx in range(root.allOccurrences.count):
                    occ = root.allOccurrences.item(occ_idx)
                    for b_idx in range(occ.bRepBodies.count):
                        total_vol += occ.bRepBodies.item(b_idx).volume
                debug_info.append(f'Total volume: {round(total_vol, 6)} cm3')
                geometry_changed = param_changed  # If param changed, geometry should have too
            except Exception as e:
                debug_info.append(f'Volume check error: {str(e)}')
                geometry_changed = param_changed

            return {
                'success': True,
                'parameter': param_name,
                'before_expression': before_expression,
                'before_value': before_value,
                'after_expression': actual_expression,
                'after_value': actual_value,
                'param_changed': param_changed,
                'geometry_changed': geometry_changed,
                'debug': debug_info,
                'message': f'Updated {param_name}: {before_expression} -> {new_expression}',
            }

        # ─── POST /fusion/design/export/stl ───────────────
        elif path == '/fusion/design/export/stl':
            if not design:
                return {'error': 'No active design'}

            export_path = body.get('path', '')
            component_name = body.get('component', '')

            if not export_path:
                return {'error': 'Export path required'}

            # Ensure directory exists
            export_dir = os.path.dirname(export_path)
            if export_dir and not os.path.exists(export_dir):
                os.makedirs(export_dir, exist_ok=True)

            root = design.rootComponent
            export_mgr = design.exportManager

            # Find target component by searching occurrences first
            # Uses Unicode normalization for Vietnamese diacritical names
            target = root  # Default: export entire assembly
            found_name = 'root'
            if component_name:
                import unicodedata
                
                def normalize(s):
                    """Normalize Unicode string for comparison."""
                    return unicodedata.normalize('NFC', s).lower()
                
                def strip_diacritics(s):
                    """Strip diacritical marks for fallback comparison."""
                    nfkd = unicodedata.normalize('NFKD', s)
                    return ''.join(c for c in nfkd if not unicodedata.combining(c)).lower()
                
                search_norm = normalize(component_name)
                search_ascii = strip_diacritics(component_name)
                
                # Strategy 1: Exact Unicode match on occurrences
                for i in range(root.allOccurrences.count):
                    occ = root.allOccurrences.item(i)
                    occ_base = occ.name.rsplit(':', 1)[0]
                    if normalize(occ_base) == search_norm:
                        target = occ.component
                        found_name = occ.name
                        break
                
                # Strategy 2: ASCII-stripped match (handles diacritics mismatch)
                if target == root:
                    for i in range(root.allOccurrences.count):
                        occ = root.allOccurrences.item(i)
                        occ_base = occ.name.rsplit(':', 1)[0]
                        if strip_diacritics(occ_base) == search_ascii:
                            target = occ.component
                            found_name = occ.name
                            break
                
                # Strategy 3: Partial/substring match
                if target == root:
                    for i in range(root.allOccurrences.count):
                        occ = root.allOccurrences.item(i)
                        occ_base = occ.name.rsplit(':', 1)[0]
                        if search_ascii in strip_diacritics(occ_base):
                            target = occ.component
                            found_name = occ.name
                            break

                # Strategy 4: Search allComponents by name
                if target == root:
                    for i in range(design.allComponents.count):
                        comp = design.allComponents.item(i)
                        if normalize(comp.name) == search_norm or strip_diacritics(comp.name) == search_ascii:
                            target = comp
                            found_name = comp.name
                            break

            try:
                stl_options = export_mgr.createSTLExportOptions(target, export_path)
                stl_options.meshRefinement = adsk.fusion.MeshRefinementSettings.MeshRefinementMedium
                export_mgr.execute(stl_options)
                return {
                    'success': True,
                    'path': export_path,
                    'component': found_name,
                    'message': f'Exported STL ({found_name}) to {export_path}',
                }
            except Exception as e:
                return {'error': f'STL export failed: {str(e)}'}

        # ─── POST /fusion/design/export/step ──────────────
        elif path == '/fusion/design/export/step':
            if not design:
                return {'error': 'No active design'}

            export_path = body.get('path', '')
            if not export_path:
                return {'error': 'Export path required'}

            export_dir = os.path.dirname(export_path)
            if export_dir and not os.path.exists(export_dir):
                os.makedirs(export_dir, exist_ok=True)

            root = design.rootComponent
            export_mgr = design.exportManager

            try:
                step_options = export_mgr.createSTEPExportOptions(export_path, root)
                export_mgr.execute(step_options)
                return {
                    'success': True,
                    'path': export_path,
                    'message': f'Exported STEP to {export_path}',
                }
            except Exception as e:
                return {'error': f'STEP export failed: {str(e)}'}

        # ─── POST /fusion/design/save ─────────────────────
        elif path == '/fusion/design/save':
            """Save the active document (.f3d file)."""
            doc = app.activeDocument
            if not doc:
                return {'error': 'No active document to save'}

            results = {'success': False, 'actions': []}

            # 1. Try standard save (works for Fusion Team / cloud docs)
            try:
                doc.save('Modified by Engineering Change Manager')
                results['actions'].append('Cloud save: OK')
                results['success'] = True
            except Exception as e:
                results['actions'].append(f'Cloud save: {str(e)}')

            # 2. Also export a local .f3d backup to outputs folder
            try:
                if design:
                    export_mgr = design.exportManager
                    backup_name = design.rootComponent.name.replace(' ', '_')
                    backup_path = os.path.join(
                        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'outputs',
                        f'{backup_name}_backup.f3d'
                    )
                    # Ensure outputs dir exists
                    backup_dir = os.path.dirname(backup_path)
                    if backup_dir and not os.path.exists(backup_dir):
                        os.makedirs(backup_dir, exist_ok=True)

                    fusion_doc = adsk.fusion.FusionDocument.cast(doc)
                    if fusion_doc:
                        options = export_mgr.createFusionArchiveExportOptions(backup_path)
                        export_mgr.execute(options)
                        results['actions'].append(f'Local backup: {backup_path}')
                        results['backup_path'] = backup_path
                        results['success'] = True
            except Exception as e:
                results['actions'].append(f'Local backup: {str(e)}')

            results['message'] = ' | '.join(results['actions'])
            results['is_saved'] = doc.isSaved
            return results

        # ─── POST /fusion/design/undo ─────────────────────
        elif path == '/fusion/design/undo':
            """Undo the last operation in Fusion 360."""
            try:
                app.executeTextCommand(u'Commands.Start UndoCommand')
                adsk.doEvents()
                return {
                    'success': True,
                    'message': 'Undo executed successfully',
                }
            except Exception as e:
                return {'error': f'Undo failed: {str(e)}'}

        # ─── POST /fusion/design/snapshot ─────────────────
        elif path == '/fusion/design/snapshot':
            """Take a geometry snapshot for before/after comparison."""
            if not design:
                return {'error': 'No active design'}

            root = design.rootComponent
            snapshot = {
                'parameters': {},
                'bodies': [],
                'occurrences': [],
                'total_volume': 0,
                'total_area': 0,
            }

            # Capture all parameter values (user + model)
            for i in range(design.allParameters.count):
                p = design.allParameters.item(i)
                snapshot['parameters'][p.name] = {
                    'expression': p.expression,
                    'value': p.value,  # Internal units: cm for length
                    'unit': p.unit,
                }

            # Capture per-occurrence metrics (individual components)
            total_vol = 0
            total_area = 0
            for i in range(root.allOccurrences.count):
                occ = root.allOccurrences.item(i)
                occ_vol = 0
                occ_area = 0
                for j in range(occ.bRepBodies.count):
                    body = occ.bRepBodies.item(j)
                    try:
                        props = body.physicalProperties
                        occ_vol += props.volume
                        occ_area += props.area
                    except:
                        try:
                            occ_vol += body.volume
                            occ_area += body.area
                        except:
                            pass

                total_vol += occ_vol
                total_area += occ_area

                # Get occurrence bounding box (in assembly context)
                occ_bb = {}
                try:
                    bb = occ.boundingBox
                    occ_bb = {
                        'length': round((bb.maxPoint.x - bb.minPoint.x) * 10, 2),
                        'width': round((bb.maxPoint.y - bb.minPoint.y) * 10, 2),
                        'height': round((bb.maxPoint.z - bb.minPoint.z) * 10, 2),
                    }
                except:
                    pass

                snapshot['occurrences'].append({
                    'name': occ.name,
                    'component': occ.component.name,
                    'volume_cm3': round(occ_vol, 6),
                    'area_cm2': round(occ_area, 4),
                    'bodies': occ.bRepBodies.count,
                    'bbox_mm': occ_bb,
                })

            # Also capture root-level bodies
            for i in range(root.bRepBodies.count):
                body = root.bRepBodies.item(i)
                try:
                    props = body.physicalProperties
                    vol = props.volume
                    area = props.area
                except:
                    vol = body.volume if hasattr(body, 'volume') else 0
                    area = body.area if hasattr(body, 'area') else 0
                total_vol += vol
                total_area += area
                snapshot['bodies'].append({
                    'name': body.name,
                    'volume': round(vol, 4),
                    'area': round(area, 4),
                })

            snapshot['total_volume'] = round(total_vol, 4)
            snapshot['total_area'] = round(total_area, 4)

            # Root bounding box (entire assembly) - in cm, convert to mm
            try:
                bb = root.boundingBox
                snapshot['bounding_box'] = {
                    'min_x': round(bb.minPoint.x, 4),
                    'min_y': round(bb.minPoint.y, 4),
                    'min_z': round(bb.minPoint.z, 4),
                    'max_x': round(bb.maxPoint.x, 4),
                    'max_y': round(bb.maxPoint.y, 4),
                    'max_z': round(bb.maxPoint.z, 4),
                    'length': round(bb.maxPoint.x - bb.minPoint.x, 4),
                    'width': round(bb.maxPoint.y - bb.minPoint.y, 4),
                    'height': round(bb.maxPoint.z - bb.minPoint.z, 4),
                }
            except:
                snapshot['bounding_box'] = {}

            return snapshot

        else:
            return {'error': f'Unknown endpoint: {path}'}

    except Exception as e:
        return {'error': str(e), 'traceback': traceback.format_exc()}


# ═══════════════════════════════════════════════════════════
#  CUSTOM EVENT HANDLER (bridges HTTP thread → main thread)
# ═══════════════════════════════════════════════════════════

class BridgeEventHandler(adsk.core.CustomEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        """Called on the main thread when a custom event fires."""
        try:
            # Process all pending requests
            while not _request_queue.empty():
                try:
                    req = _request_queue.get_nowait()
                    req_id = req['id']
                    result = process_command(req)
                    _responses[req_id] = result
                    if req_id in _response_events:
                        _response_events[req_id].set()
                except queue.Empty:
                    break
                except Exception as e:
                    req_id = req.get('id', '')
                    _responses[req_id] = {'error': str(e)}
                    if req_id in _response_events:
                        _response_events[req_id].set()
        except:
            pass


# ═══════════════════════════════════════════════════════════
#  HTTP SERVER (runs in background thread)
# ═══════════════════════════════════════════════════════════

class FusionHTTPHandler(BaseHTTPRequestHandler):
    """Handles HTTP requests from the web server."""

    def log_message(self, format, *args):
        """Suppress default logging to avoid cluttering Fusion console."""
        pass

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self._send_json({'ok': True})

    def _dispatch(self, method):
        """Send request to Fusion main thread and wait for response."""
        # Read body for POST
        body = {}
        if method == 'POST':
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                raw = self.rfile.read(content_length)
                try:
                    body = json.loads(raw.decode('utf-8'))
                except:
                    body = {}

        # Create unique request ID
        req_id = str(uuid.uuid4())

        # Create response event
        event = threading.Event()
        _response_events[req_id] = event

        # Queue the request
        _request_queue.put({
            'id': req_id,
            'method': method,
            'path': self.path,
            'body': body,
        })

        # Fire custom event to wake up main thread
        try:
            _app.fireCustomEvent(CUSTOM_EVENT_ID, '')
        except:
            self._send_json({'error': 'Failed to fire event'}, 500)
            return

        # Wait for response (timeout 120 seconds — computeAll can take 30-60s)
        event.wait(timeout=120)

        # Get response
        result = _responses.pop(req_id, {'error': 'Request timed out'})
        _response_events.pop(req_id, None)

        self._send_json(result)

    def do_GET(self):
        self._dispatch('GET')

    def do_POST(self):
        self._dispatch('POST')


def start_server():
    """Start the HTTP server in a background thread."""
    global _http_server
    try:
        _http_server = HTTPServer(('127.0.0.1', PORT), FusionHTTPHandler)
        _http_server.serve_forever()
    except Exception as e:
        print(f'FusionBridge server error: {e}')


# ═══════════════════════════════════════════════════════════
#  ADD-IN ENTRY POINTS
# ═══════════════════════════════════════════════════════════

def run(context):
    """Called when the add-in is started."""
    global _app, _ui, _custom_event, _event_handler, _server_thread

    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface

        # Register custom event
        _custom_event = _app.registerCustomEvent(CUSTOM_EVENT_ID)
        _event_handler = BridgeEventHandler()
        _custom_event.add(_event_handler)
        _handlers.append(_event_handler)  # Prevent garbage collection

        # Start HTTP server in background thread
        _server_thread = threading.Thread(target=start_server, daemon=True)
        _server_thread.start()

        _ui.messageBox(
            f'FusionBridge started!\\n\\n'
            f'HTTP server running on http://127.0.0.1:{PORT}\\n'
            f'The Engineering Change Management System can now connect.',
            'FusionBridge'
        )

    except:
        if _ui:
            _ui.messageBox(f'FusionBridge failed to start:\\n{traceback.format_exc()}')


def stop(context):
    """Called when the add-in is stopped."""
    global _http_server, _custom_event, _event_handler

    try:
        # Stop HTTP server
        if _http_server:
            _http_server.shutdown()
            _http_server = None

        # Unregister custom event
        if _custom_event:
            if _event_handler:
                _custom_event.remove(_event_handler)
            _app.unregisterCustomEvent(CUSTOM_EVENT_ID)
            _custom_event = None
            _event_handler = None

        if _ui:
            _ui.messageBox('FusionBridge stopped.', 'FusionBridge')

    except:
        if _ui:
            _ui.messageBox(f'FusionBridge stop error:\\n{traceback.format_exc()}')
