# 🔧 Prompt-driven Intelligent Engineering Change Management System

> AI-driven system that interprets natural language engineering change requests, 
> modifies CAD models in **Fusion 360 via API**, traces dependency impacts, and 
> generates professional change impact reports.

## 🏗️ Architecture

```
Browser UI (localhost:8000)
    │
    ├─→ FastAPI Server (NLP + Analysis + Reports)
    │       │
    │       ╰─→ Fusion 360 Add-in Bridge (localhost:5001)
    │               │
    │               ╰─→ Fusion 360 API (modifies .f3d model live)
    │
    ╰─→ Three.js 3D Viewer (before/after STL)
```

## ✨ Features

| Feature | Status |
|---------|--------|
| Natural language change requests (NLP via spaCy) | ✅ |
| Live CAD modification via Fusion 360 API | ✅ |
| Before/after 3D visualization (Three.js) | ✅ |
| Dependency impact analysis (6+ affected parts) | ✅ |
| Change classification (MAJOR/MINOR) | ✅ |
| Risk assessment (LOW/MEDIUM/HIGH) | ✅ |
| Engineering effort estimation | ✅ |
| BOM impact analysis | ✅ |
| Document impact tracking | ✅ |
| Professional HTML impact report | ✅ |
| Modified STEP file download | ✅ |
| Simulation mode (without Fusion 360) | ✅ |

## 📁 Project Structure

```
e:\Change Management System\
├── backend/                    # Python backend
│   ├── main.py                 # FastAPI server
│   ├── nlp_parser.py           # spaCy NLP engine
│   ├── cad_engine.py           # Fusion 360 bridge client
│   ├── impact_analyzer.py      # Dependency analysis
│   ├── report_generator.py     # Jinja2 report engine
│   ├── database.py             # SQLite database
│   └── models.py               # Pydantic models
├── frontend/                   # Web UI
│   ├── index.html              # Main dashboard
│   ├── style.css               # Premium dark theme
│   ├── app.js                  # Frontend logic
│   └── three_viewer.js         # Three.js 3D viewer
├── fusion_addin/               # Fusion 360 add-in
│   ├── FusionBridge/           # HTTP bridge add-in
│   │   ├── FusionBridge.py
│   │   └── FusionBridge.manifest
│   └── DemoGearboxBuilder/     # Demo model script
│       ├── DemoGearboxBuilder.py
│       └── DemoGearboxBuilder.manifest
├── templates/                  # Report HTML template
├── data/                       # SQLite DB + init script
├── docs/                       # Documentation
│   └── FUSION_SETUP.md         # Fusion 360 setup guide
└── requirements.txt
```

## 🚀 Quick Start

### 1. Install Python Dependencies

```powershell
cd "e:\Change Management System"
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

### 2. Set Up Fusion 360

Follow the detailed guide: **[docs/FUSION_SETUP.md](docs/FUSION_SETUP.md)**

Quick version:
1. Copy `fusion_addin/FusionBridge/` → `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\`
2. Copy `fusion_addin/DemoGearboxBuilder/` → `%APPDATA%\Autodesk\Autodesk Fusion 360\API\Scripts\`
3. In Fusion 360: Utilities → Scripts → Run **DemoGearboxBuilder** (once)
4. In Fusion 360: Utilities → Add-Ins → Run **FusionBridge**

### 3. Start the Server

```powershell
$env:PYTHONIOENCODING="utf-8"
python backend/main.py
```

### 4. Open the App

Go to **http://localhost:8000** → Click "Connect Fusion 360" → Type a change request → Click "Analyze & Apply"

## 🧪 Example Change Requests

```
Reduce wall thickness of Housing by 2 mm
Increase input shaft diameter to 30 mm
Change gear_a_face_width to 25 mm
Reduce housing height by 10 mm
```

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Python, FastAPI |
| NLP | spaCy (en_core_web_sm) |
| CAD Engine | Fusion 360 Desktop API |
| Database | SQLite |
| Frontend | Vanilla HTML/JS/CSS |
| 3D Viewer | Three.js |
| Reports | Jinja2 HTML |
