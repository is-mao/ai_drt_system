from flask import Blueprint, request, jsonify, render_template, session
from routes.auth import login_required
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
    if session.get("role") != "admin":
        return jsonify({"error": "Admin access required"}), 403
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    api_key = data.get("api_key", "").strip()
    _write_env_key(api_key)

    return jsonify({"success": True, "message": "API key updated successfully"})


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
        return jsonify({"success": False, "message": "No API key configured. Please enter a key first.",
                        "debug": "No key found in input, .env, or database"})

    key_count = len([k for k in api_key.split(",") if k.strip()])
    debug_info = f"source={key_source}, keys={key_count}, first_key={api_key[:8]}...{api_key.split(',')[0].strip()[-4:]}"

    success, message = test_ai_connection(api_key)
    return jsonify({"success": success, "message": message, "debug": debug_info})
