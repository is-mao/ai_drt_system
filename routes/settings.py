from flask import Blueprint, request, jsonify, render_template, session
from routes.auth import login_required
from models import db
from models.system_config import SystemConfig
from models.user import User
from services.ai_service import test_ai_connection
import os

settings_bp = Blueprint("settings", __name__)

# Path to .env file
_ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")

_ENV_KEY_MAP = {
    "gemini_api_key": "GEMINI_API_KEY",
    "glm_api_key": "GLM_API_KEY",
}


def _read_env_var(env_name):
    """Read a single env var from .env file."""
    if not os.path.exists(_ENV_FILE):
        return ""
    with open(_ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith(env_name + "="):
                return line.split("=", 1)[1].strip()
    return ""


def _write_env_var(env_name, value):
    """Write a single env var to .env file and runtime env."""
    lines = []
    found = False
    if os.path.exists(_ENV_FILE):
        with open(_ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith(env_name + "="):
                    found = True
                    if value:
                        lines.append(f"{env_name}={value}\n")
                    # If value is empty, skip this line (remove it)
                else:
                    lines.append(line)
    if not found and value:
        lines.append(f"{env_name}={value}\n")

    with open(_ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)

    # Also update the runtime environment variable
    if value:
        os.environ[env_name] = value
    elif env_name in os.environ:
        del os.environ[env_name]


def _mask_secret(value):
    if not value:
        return ""
    return value[:4] + "*" * (len(value) - 8) + value[-4:] if len(value) > 8 else "****"


@settings_bp.route("/settings")
@login_required
def settings_page():
    return render_template("settings.html")


@settings_bp.route("/api/settings/ai", methods=["GET"])
@login_required
def get_ai_settings():
    gemini_key = _read_env_var(_ENV_KEY_MAP["gemini_api_key"]) or SystemConfig.get_value("gemini_api_key", "") or ""
    glm_key = _read_env_var(_ENV_KEY_MAP["glm_api_key"]) or SystemConfig.get_value("glm_api_key", "") or ""
    return jsonify(
        {
            "has_gemini_key": bool(gemini_key),
            "masked_gemini_key": _mask_secret(gemini_key),
            "has_glm_key": bool(glm_key),
            "masked_glm_key": _mask_secret(glm_key),
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

    updates = {
        "gemini_api_key": data.get("gemini_api_key"),
        "glm_api_key": data.get("glm_api_key"),
    }
    for config_key, value in updates.items():
        if value is None:
            continue
        clean_value = str(value).strip()
        _write_env_var(_ENV_KEY_MAP[config_key], clean_value)
        SystemConfig.set_value(config_key, clean_value)

    return jsonify({"success": True, "message": "AI provider settings updated successfully"})


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
    provider = data.get("provider", "gemini").strip().lower() or "gemini"
    setting_key = {
        "gemini": "gemini_api_key",
        "glm": "glm_api_key",
    }.get(provider, "gemini_api_key")
    env_name = _ENV_KEY_MAP.get(setting_key, _ENV_KEY_MAP["gemini_api_key"])

    api_key = data.get("api_key", "").strip()
    key_source = "input"
    if not api_key:
        api_key = _read_env_var(env_name)
        key_source = ".env file"
    if not api_key:
        api_key = SystemConfig.get_value(setting_key) or ""
        key_source = "database"

    if not api_key:
        return jsonify(
            {
                "success": False,
                "message": "No API key configured. Please enter a key first.",
                "debug": f"provider={provider}, no key found in input, .env, or database",
            }
        )

    key_count = len([k for k in api_key.split(",") if k.strip()])
    debug_info = f"provider={provider}, source={key_source}, keys={key_count}, first_key={api_key[:8]}...{api_key.split(',')[0].strip()[-4:]}"

    success, message = test_ai_connection(provider, api_key)
    return jsonify({"success": success, "message": message, "debug": debug_info})


# ---------------------------------------------------------------------------
# Per-User API Key Management
# ---------------------------------------------------------------------------


@settings_bp.route("/api/settings/user-ai", methods=["GET"])
@login_required
def get_user_ai_settings():
    user = db.session.get(User, session["user_id"])
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(
        {
            "has_gemini_key": bool(user.gemini_api_key),
            "masked_gemini_key": _mask_secret(user.gemini_api_key or ""),
            "has_glm_key": bool(user.glm_api_key),
            "masked_glm_key": _mask_secret(user.glm_api_key or ""),
        }
    )


@settings_bp.route("/api/settings/user-ai", methods=["PUT"])
@login_required
def update_user_ai_settings():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    user = db.session.get(User, session["user_id"])
    if not user:
        return jsonify({"error": "User not found"}), 404
    if "gemini_api_key" in data:
        user.gemini_api_key = str(data["gemini_api_key"]).strip()
    if "glm_api_key" in data:
        user.glm_api_key = str(data["glm_api_key"]).strip()
    db.session.commit()
    return jsonify({"success": True, "message": "Your API keys updated successfully"})
