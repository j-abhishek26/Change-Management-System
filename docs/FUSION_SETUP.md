# Fusion 360 Integration — Complete Setup & Verification Guide

## Architecture

```
┌─────────────────────┐     HTTP (port 8000)    ┌──────────────┐
│   Web Browser UI    │ ◄─────────────────────► │  FastAPI      │
│   (localhost:8000)   │                        │  Backend      │
└─────────────────────┘                         └──────┬───────┘
                                                       │
                                                HTTP (port 5001)
                                                       │
                                                ┌──────▼───────┐
                                                │ FusionBridge  │
                                                │ (Add-in inside│
                                                │  Fusion 360)  │
                                                └──────┬───────┘
                                                       │
                                                ┌──────▼───────┐
                                                │ Fusion 360    │
                                                │ Desktop App   │
                                                │ (.f3d model)  │
                                                └──────────────┘
```

**Flow:** Web UI → FastAPI backend → FusionBridge add-in → Fusion 360 API → Modify parameter → Save .f3d → Export STL/STEP

---

## Step 1: Install the FusionBridge Add-in

### Copy to Fusion's Add-Ins folder:

**Open PowerShell and run:**
```powershell
# Auto-detect the Fusion add-ins path and copy
$fusionAddinPath = "$env:APPDATA\Autodesk\Autodesk Fusion 360\API\AddIns"
Copy-Item -Recurse -Force "E:\Change Management System\fusion_addin\FusionBridge" "$fusionAddinPath\FusionBridge"
Write-Host "✅ FusionBridge add-in copied to: $fusionAddinPath\FusionBridge"
```

**Verify** — the folder should contain:
```
%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\FusionBridge\
    ├── FusionBridge.py
    └── FusionBridge.manifest
```

---

## Step 2: Open Your Planet Gearbox Model

1. Open **Fusion 360**
2. **File → Open** → navigate to `E:\Change Management System\f3dmodel\`
3. Open the `.f3d` file (your planet gearbox from GrabCAD)
4. **Important:** The design MUST be in **Parametric** mode (check bottom bar)
   - If it says "Direct Modeling", right-click the timeline → "Convert to Parametric"

---

## Step 3: Start the FusionBridge Add-in

1. In Fusion 360: **Utilities** tab → **Add-Ins** (or press Shift+S)
2. Switch to the **Add-Ins** tab
3. Find **FusionBridge** in the list
4. Check **"Run on Startup"** (optional, for auto-start)
5. Click **Run**
6. You should see a message: *"FusionBridge started! HTTP server running on http://127.0.0.1:5001"*

### ✅ Verify the add-in is running:

Open a browser or PowerShell and check:
```powershell
# Test the bridge connection
Invoke-RestMethod http://127.0.0.1:5001/fusion/status | ConvertTo-Json
```

Expected output:
```json
{
  "connected": true,
  "version": "2.0.XXXX",
  "has_design": true,
  "design_name": "Planet Gearbox"
}
```

### ✅ Verify parameters are accessible:

```powershell
# List all parameters
(Invoke-RestMethod http://127.0.0.1:5001/fusion/design/parameters).parameters | 
    Select-Object name, expression, unit | Format-Table
```

You should see parameters like `wall_thickness`, `outer_diameter`, `height`, etc.

---

## Step 4: Start the Web Server

```powershell
cd "E:\Change Management System"
python backend/main.py
```

The server starts at **http://localhost:8000**. You should see:
```
═══ Engineering Change Manager v3.0 ═══
  Fusion 360 + PDM + ERP Integration
  [OK] Fusion 360 connected (v2.0.XXXX)
```

---

## Step 5: Connect from the Web UI

1. Open **http://localhost:8000** in your browser
2. Click the **"🔌 Connect Fusion 360"** button in the top-right
3. The status should change to: **🟢 LIVE from Fusion 360**
4. The Parts Registry in the sidebar will auto-populate from the Fusion model

---

## Step 6: Test a Change (End-to-End)

1. Click **"Reduce wall thickness"** in Quick Examples
2. Click **"🚀 Analyze & Apply"**

### What happens behind the scenes:

```
1. NLP parses: "Reduce wall_thickness of Ring Gear Top by 2 mm"
2. Backend finds matching Fusion parameter (e.g., 'wall_thickness')
3. Calculates: old expression "6 mm" → new expression "4 mm"
4. Sends to FusionBridge:
   POST http://127.0.0.1:5001/fusion/design/modify
   { "parameter_name": "wall_thickness", "new_expression": "4 mm" }
5. Fusion 360 updates the geometry in real-time
6. Exports BEFORE and AFTER STL/STEP files
7. AUTO-SAVES the .f3d file ← NEW
8. Impact analysis runs (cascading dependency check)
9. PDM creates revision, ERP generates manufacturing orders
```

### ✅ Verify in Fusion 360:

- The model's shape should visually change
- In the **Parameters** dialog (Modify → Change Parameters): the parameter should show the new value
- The **timeline** at the bottom should show the parameter edit
- The file should be **saved** (no unsaved changes indicator)

---

## Connection Verification Checklist

Run these to confirm everything works:

| # | Check | Command | Expected |
|---|-------|---------|----------|
| 1 | FusionBridge running | `curl http://127.0.0.1:5001/fusion/status` | `{"connected": true}` |
| 2 | Design loaded | `curl http://127.0.0.1:5001/fusion/design/info` | Shows design name, units |
| 3 | Parameters accessible | `curl http://127.0.0.1:5001/fusion/design/parameters` | Lists all parameters |
| 4 | Backend connected | `curl http://localhost:8000/api/fusion/connect` | `{"connected": true}` |
| 5 | Save works | `curl -X POST http://127.0.0.1:5001/fusion/design/save` | `{"success": true}` |
| 6 | STL export works | Via Analyze & Apply | Check `outputs/` folder for .stl files |

Or run all at once in PowerShell:
```powershell
Write-Host "=== Connection Test ===" -ForegroundColor Cyan

# 1. FusionBridge
try {
    $status = Invoke-RestMethod http://127.0.0.1:5001/fusion/status
    Write-Host "✅ FusionBridge: Connected ($($status.version))" -ForegroundColor Green
} catch { Write-Host "❌ FusionBridge: NOT running" -ForegroundColor Red }

# 2. Design Info
try {
    $info = Invoke-RestMethod http://127.0.0.1:5001/fusion/design/info
    Write-Host "✅ Design: $($info.design_name) ($($info.units))" -ForegroundColor Green
} catch { Write-Host "❌ Design: Not loaded" -ForegroundColor Red }

# 3. Parameters
try {
    $params = Invoke-RestMethod http://127.0.0.1:5001/fusion/design/parameters
    Write-Host "✅ Parameters: $($params.total) found" -ForegroundColor Green
} catch { Write-Host "❌ Parameters: Failed" -ForegroundColor Red }

# 4. Backend
try {
    $backend = Invoke-RestMethod http://localhost:8000/api/fusion/connect
    Write-Host "✅ Backend: $($backend.message)" -ForegroundColor Green
} catch { Write-Host "❌ Backend: NOT running" -ForegroundColor Red }

# 5. Save
try {
    $save = Invoke-RestMethod -Method Post http://127.0.0.1:5001/fusion/design/save
    Write-Host "✅ Save: $($save.message)" -ForegroundColor Green
} catch { Write-Host "⚠️ Save: $($_.Exception.Message)" -ForegroundColor Yellow }

Write-Host "`n=== All Checks Complete ===" -ForegroundColor Cyan
```

---

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| "Cannot reach Fusion 360" | FusionBridge not running | Utilities → Add-Ins → FusionBridge → Run |
| "No active design" | No .f3d file open | Open your planet gearbox .f3d file |
| "Parameter not found" | Name mismatch | Run the parameters check above — the NLP will try fuzzy matching |
| Port 5001 in use | Another app using port | Change PORT in FusionBridge.py line 26 |
| "Not parametric" | Direct modeling mode | Convert timeline to parametric |
| Changes not reflected | Fusion API delay | Wait 1-2 seconds, Fusion needs to regenerate |
| 3D viewer dimensions wrong | STL scale mismatch | Auto-corrected by the viewer's normalization |
| Save fails | Cloud document | Save locally first (File → Export → .f3d) |

---

## Simulation Mode (Fusion Not Available)

If Fusion 360 is not running, the system gracefully falls back to **simulation mode**:
- ✅ NLP parsing works
- ✅ Impact analysis with cascading dependencies works
- ✅ PDM revisions and BOM tracking works
- ✅ ERP manufacturing orders and cost analysis works
- ✅ 3D viewer shows simulated Before/After with visual transforms
- ❌ Real parameter modification (requires Fusion)
- ❌ .f3d file save (requires Fusion)
