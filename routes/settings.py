from flask import Blueprint, request, jsonify, render_template, session
from routes.auth import login_required
from models import db
from models.system_config import SystemConfig
from services.ai_service import test_ai_connection
import os

settings_bp = Blueprint("settings", __name__)

# Path to .env file
_ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")


def _read_env_key():
    """Read GEMINI_API_KEY from .env file."""
    if not os.path.exists(_ENV_FILE):
        return ""
    with open(_ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("GEMINI_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


def _write_env_key(value):
    """Write GEMINI_API_KEY to .env file."""
    lines = []
    found = False
    if os.path.exists(_ENV_FILE):
        with open(_ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("GEMINI_API_KEY="):
                    found = True
                    if value:
                        lines.append(f"GEMINI_API_KEY={value}\n")
                    # If value is empty, skip this line (remove it)
                else:
                    lines.append(line)
    if not found and value:
        lines.append(f"GEMINI_API_KEY={value}\n")

    with open(_ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)

    # Also update the runtime environment variable
    if value:
        os.environ["GEMINI_API_KEY"] = value
    elif "GEMINI_API_KEY" in os.environ:
        del os.environ["GEMINI_API_KEY"]


@settings_bp.route("/settings")
@login_required
def settings_page():
    return render_template("settings.html")


@settings_bp.route("/api/settings/ai", methods=["GET"])
@login_required
def get_ai_settings():
    api_key = _read_env_key()
    masked = ""
    if api_key:
        masked = api_key[:4] + "*" * (len(api_key) - 8) + api_key[-4:] if len(api_key) > 8 else "****"
    return jsonify(
        {
            "has_key": bool(api_key),
            "masked_key": masked,
        }
    )


@settings_bp.route("/api/settings/ai", methods=["PUT"])
@login_required
def update_ai_settings():
    if session.get("role") not in ("admin", "superadmin"):
        return jsonify({"error": "Admin access required"}), 403
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    api_key = data.get("api_key", "").strip()
    _write_env_key(api_key)

    return jsonify({"success": True, "message": "API key updated successfully"})


# ---------------------------------------------------------------------------
# Database URL Configuration (for remote DB on other machines)
# ---------------------------------------------------------------------------


@settings_bp.route("/api/settings/database", methods=["GET"])
@login_required
def get_database_settings():
    if session.get("role") != "superadmin":
        return jsonify({"error": "Superadmin access required"}), 403
    env_url = os.environ.get("DATABASE_URL", "")
    config_url = SystemConfig.get_value("database_url", "") or ""
    active_url = env_url or config_url
    masked = ""
    source = "none"
    if active_url:
        # Mask the password in the URL for display
        try:
            at_idx = active_url.index("@")
            prefix = active_url[: active_url.index("://") + 3]
            user_pass = active_url[len(prefix) : at_idx]
            rest = active_url[at_idx:]
            if ":" in user_pass:
                user, _ = user_pass.split(":", 1)
                masked = prefix + user + ":****" + rest
            else:
                masked = prefix + user_pass + rest
        except (ValueError, IndexError):
            masked = active_url[:20] + "..." if len(active_url) > 20 else active_url
        source = "env" if env_url else "config"
    return jsonify({"has_url": bool(active_url), "masked_url": masked, "source": source})


@settings_bp.route("/api/settings/database", methods=["PUT"])
@login_required
def update_database_settings():
    if session.get("role") != "superadmin":
        return jsonify({"error": "Superadmin access required"}), 403
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    database_url = data.get("database_url", "").strip()

    # Save to system_config table (persisted in local SQLite)
    config = db.session.get(SystemConfig, "database_url")
    if config:
        config.config_value = database_url
    else:
        db.session.add(SystemConfig(config_key="database_url", config_value=database_url))
    db.session.commit()

    # Also update runtime environment variable
    if database_url:
        os.environ["DATABASE_URL"] = database_url
    elif "DATABASE_URL" in os.environ:
        del os.environ["DATABASE_URL"]

    # Reset cached remote engine so it re-initializes with new URL
    from services.db_routing import reset_remote_engine, init_all_tables

    reset_remote_engine()

    # Initialize tables on the new remote DB
    if database_url:
        try:
            init_all_tables()
        except Exception:
            pass

    return jsonify({"success": True, "message": "Database URL updated. Please log out and log back in."})


@settings_bp.route("/api/settings/database/test", methods=["POST"])
@login_required
def test_database():
    if session.get("role") not in ("admin", "superadmin"):
        return jsonify({"error": "Admin access required"}), 403
    data = request.get_json(silent=True) or {}
    test_url = data.get("database_url", "").strip()
    if not test_url:
        test_url = os.environ.get("DATABASE_URL", "")
    if not test_url:
        test_url = SystemConfig.get_value("database_url", "") or ""
    if not test_url:
        return jsonify({"success": False, "message": "No Database URL configured"})

    try:
        from sqlalchemy import create_engine, text

        if test_url.startswith("postgres://"):
            test_url = test_url.replace("postgres://", "postgresql://", 1)
        engine = create_engine(test_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return jsonify({"success": True, "message": "Connected to remote database successfully!"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@settings_bp.route("/api/settings/ai/test", methods=["POST"])
@login_required
def test_ai():
    data = request.get_json(silent=True) or {}
    api_key = data.get("api_key", "").strip()
    key_source = "input"
    if not api_key:
        api_key = _read_env_key()
        key_source = ".env file"
    if not api_key:
        api_key = SystemConfig.get_value("gemini_api_key") or ""
        key_source = "database"
    if not api_key:
        return jsonify(
            {
                "success": False,
                "message": "No API key configured. Please enter a key first.",
                "debug": "No key found in input, .env, or database",
            }
        )

    key_count = len([k for k in api_key.split(",") if k.strip()])
    debug_info = (
        f"source={key_source}, keys={key_count}, first_key={api_key[:8]}...{api_key.split(',')[0].strip()[-4:]}"
    )

    success, message = test_ai_connection(api_key)
    return jsonify({"success": success, "message": message, "debug": debug_info})
