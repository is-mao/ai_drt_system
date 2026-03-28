# AI DRT System (Defect Report Tracking)

A Flask-based Defect Report Tracking system with AI-powered log analysis using Google Gemini.

## Features

- **Defect Reports** — CRUD with sorting, filtering, pagination, Excel export/import
- **Cesium Import** — Import raw test data from Cesium system as pending drafts
- **AI Log Analysis** — Auto-classify defects using Gemini AI
- **AI Beautification** — Polish Root Cause & Action text with AI
- **Dashboard** — KPIs, charts (defect class, weekly trend, top stations/servers/PCAP/failures)
- **Multi-DB Support** — SQLite (zero-setup) or MySQL

## Quick Start

```bash
# 1. Clone
git clone https://github.com/is-mao/ai_drt_system.git
cd ai_drt_system

# 2. Create virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — set DRT_DB_TYPE and GEMINI_API_KEY

# 5. Run
python app.py
# Open http://127.0.0.1:5001
# Default login: admin / admin123
```

## Windows Deployment (Background)

```powershell
powershell -ExecutionPolicy Bypass -File .\start_drt.ps1          # Start
powershell -ExecutionPolicy Bypass -File .\start_drt.ps1 -Stop    # Stop
powershell -ExecutionPolicy Bypass -File .\start_drt.ps1 -Status  # Check status
```

Logs saved to `logs/` directory.

## Database Options

| Mode | Config | Use Case |
|------|--------|----------|
| **SQLite** (default) | `DRT_DB_TYPE=sqlite` | Single user, local, zero setup |
| **MySQL** | `DRT_DB_TYPE=mysql` | Multi-user, shared, production |

- SQLite: DB file auto-created at `instance/drt.db`, portable
- MySQL: Configure host/port/user/password in `.env`

## Data Portability

- **Export**: Defect Reports → Export Excel (with or without logs)
- **Import**: Excel or Cesium `.xlsx` files
- **Migrate**: Export from SQLite → Import to MySQL (or vice versa)

## Project Structure

```
ai_drt_system/
├── app.py              # Flask app factory, entry point
├── config.py           # Configuration (DB, defect classes/values, BU options)
├── .env.example        # Environment variables template
├── requirements.txt    # Python dependencies
├── start_drt.ps1       # Windows deployment script
├── models/             # SQLAlchemy models
├── routes/             # Flask blueprints (auth, defects, import/export, dashboard, AI)
├── services/           # AI service (Gemini integration)
├── templates/          # Jinja2 HTML templates
├── static/             # CSS, JS, images
└── docs/               # User guide, API key guide
```

## License

Private use only.
