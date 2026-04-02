# AI DRT System (Defect Report Tracking)

A Flask-based Defect Report Tracking system with AI-powered log analysis using Google Gemini.

## Features

- **Defect Reports** — CRUD with sorting, filtering (cascading Class→Value), column resize, pagination, Excel export/import
- **Cesium Import** — Import raw test data from Cesium system as pending drafts
- **Pending Management** — Full filtering, sorting, batch operations on draft records
- **AI Log Analysis** — Auto-classify defects using Gemini AI (4-tier fallback)
- **AI Beautification** — Polish Root Cause & Action text with AI
- **Dashboard** — KPIs, charts (defect class, weekly trend, top stations/servers/PCAP/failures)
- **Offline / Online Mode** — Users choose at login; offline = local SQLite, online = remote Supabase
- **User Management** — Superadmin approves/deletes accounts

## Architecture

```
┌──────────────────────────────────────────────────┐
│                  Login Page                       │
│           [ Offline ]   [ Online ]               │
└────────┬───────────────────────┬─────────────────┘
         │                       │
    Offline Mode            Online Mode
         │                       │
    ┌────▼────┐            ┌─────▼──────┐
    │ SQLite  │            │  Supabase  │
    │ (local) │            │ (remote)   │
    └─────────┘            └────────────┘
```

### Two Modes

| Mode | Local DB | Auth | Data Source | Use Case |
|------|----------|------|-------------|----------|
| **Offline** | SQLite | Local only (cisco/cisco) | SQLite | No network, quick access |
| **Online** | — | Remote (Supabase) | Supabase/PostgreSQL | Shared data, multi-user |

### Accounts

| Account | Where | Purpose |
|---------|-------|---------|
| `cisco` / `cisco` | Local SQLite (auto-created) | The sole offline account |
| Registered users | Remote DB only | Online access, needs admin approval |
| `ismao` (superadmin) | Local SQLite (auto-created) | User management |

- **Register** = writes to remote DB only (never stored locally)
- **"cisco" username** is reserved and cannot be registered to remote
- Superadmin manages users at `/admin/users`

## Quick Start

```bash
# 1. Clone
git clone <repo-url>
cd ai_drt_system

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run
python app.py
# Open http://localhost:5001
# Offline login: cisco / cisco
```

### Enable Online Mode

To use online mode, set the `DATABASE_URL` environment variable:

```bash
# .env file
DATABASE_URL=postgresql://user:pass@host:5432/dbname
```

Or configure it in the Settings page (superadmin only).

## Windows Deployment

```powershell
.\start_drt.ps1              # Start
.\start_drt.ps1 -Stop        # Stop
.\start_drt.ps1 -Restart     # Restart
.\start_drt.ps1 -Status      # Check status
```

Logs saved to `logs/` directory.

## Configuration

All configuration via environment variables (or `.env` file):

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | *(empty)* | Remote DB URL for online mode (PostgreSQL/Supabase) |
| `GEMINI_API_KEY` | *(empty)* | Google Gemini API key for AI features |
| `DRT_SECRET_KEY` | *(auto)* | Flask session secret key |
| `FLASK_DEBUG` | `0` | Set `1` for development mode |
| `PORT` | `5001` | Server port |

## Project Structure

```
ai_drt_system/
├── app.py              # Flask app factory, entry point
├── config.py           # Configuration (SQLite + remote DB)
├── requirements.txt    # Python dependencies
├── start_drt.ps1       # Windows deployment script
├── .env.example        # Environment variables template
├── drt_system.db       # SQLite database (auto-created)
├── models/             # SQLAlchemy models (User, DefectReport, SystemConfig)
├── routes/             # Flask blueprints (auth, defects, import/export, dashboard, AI, settings)
├── services/           # DB routing, AI service (Gemini integration)
├── templates/          # Jinja2 HTML templates
├── static/             # CSS, JS
└── logs/               # Server logs (auto-created)
```

## Data Portability

- **Export**: Defect Reports → Export Excel (with or without logs)
- **Import**: Excel or Cesium `.xlsx` files

## License

Private use only.
