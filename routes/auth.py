from models import db
from models.user import User
from flask import Blueprint, request, session, jsonify, render_template, redirect, url_for
from functools import wraps
from datetime import datetime
from collections import defaultdict
import time
from werkzeug.security import check_password_hash
from config import Config

auth_bp = Blueprint("auth", __name__, url_prefix="")

# Simple in-memory rate limiter for login
_login_attempts = defaultdict(list)  # ip -> [timestamp, ...]
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW = 300  # 5 minutes
TOTP_VALID_SECONDS = 300  # 5 minutes


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)

    return decorated_function


def superadmin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("auth.login"))
        if session.get("role") != "superadmin":
            if request.path.startswith("/api/"):
                return jsonify({"error": "Superadmin access required"}), 403
            return redirect(url_for("dashboard.dashboard_page"))
        return f(*args, **kwargs)

    return decorated_function


def totp_required(f):
    """Require TOTP verification for sensitive operations (if user has 2FA enabled)."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = User.query.get(session.get("user_id"))
        if user and user.totp_enabled:
            verified_at = session.get("totp_verified_at")
            if not verified_at or (time.time() - verified_at) > TOTP_VALID_SECONDS:
                return jsonify({"error": "TOTP verification required", "totp_required": True}), 403
        return f(*args, **kwargs)

    return decorated_function


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)

    return decorated_function


def superadmin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("auth.login"))
        if session.get("role") != "superadmin":
            if request.path.startswith("/api/"):
                return jsonify({"error": "Superadmin access required"}), 403
            return redirect(url_for("dashboard.dashboard_page"))
        return f(*args, **kwargs)

    return decorated_function


@auth_bp.route("/login", methods=["GET"])
def login():
    return render_template("login.html", bu_options=Config.BU_OPTIONS)


@auth_bp.route("/register", methods=["GET"])
def register_page():
    return redirect(url_for("auth.login"))


@auth_bp.route("/api/auth/register", methods=["POST"])
def api_register():
    """Public registration is disabled. Users are created by superadmin."""
    return jsonify({"success": False, "error": "Registration is disabled. Contact admin."}), 403


@auth_bp.route("/api/auth/login", methods=["POST"])
def api_login():
    data = request.get_json()

    if not data:
        return jsonify({"success": False, "error": "Invalid request body"}), 400

    # Rate limiting
    client_ip = request.remote_addr
    now = time.time()
    _login_attempts[client_ip] = [t for t in _login_attempts[client_ip] if now - t < LOGIN_WINDOW]
    if len(_login_attempts[client_ip]) >= MAX_LOGIN_ATTEMPTS:
        return jsonify({"success": False, "error": "Too many login attempts. Please try again later."}), 429

    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"success": False, "error": "Username and password are required"}), 400

    user = User.query.filter_by(username=username).first()

    if not user or not user.check_password(password):
        _login_attempts[client_ip].append(now)
        return jsonify({"success": False, "error": "Invalid username or password"}), 401

    if not user.is_active:
        return jsonify({"success": False, "error": "Account is pending approval. Please contact admin."}), 403

    user.last_login = datetime.now()
    db.session.commit()

    # Regenerate session to prevent session fixation
    session.clear()
    session.permanent = True
    session["user_id"] = user.id
    session["username"] = user.username
    session["role"] = user.role
    session["mode"] = "online"
    session["user_bu"] = "" if user.role == "superadmin" else (user.bu or "")

    return jsonify(
        {
            "success": True,
            "message": "Login successful",
            "user": user.to_dict(),
        }
    )


@auth_bp.route("/api/auth/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"success": True, "message": "Logged out successfully"})


@auth_bp.route("/api/auth/verify-totp", methods=["POST"])
@login_required
def verify_totp():
    """Verify a TOTP code and mark session as verified for 5 minutes."""
    import pyotp

    data = request.get_json()
    code = data.get("code", "").strip() if data else ""

    user = User.query.get(session["user_id"])
    if not user or not user.totp_enabled or not user.totp_secret:
        return jsonify({"success": False, "error": "2FA is not enabled."}), 400

    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(code, valid_window=1):
        return jsonify({"success": False, "error": "Invalid code."}), 401

    session["totp_verified_at"] = time.time()
    return jsonify({"success": True, "message": "Verified."})


@auth_bp.route("/api/auth/status", methods=["GET"])
def auth_status():
    if session.get("user_id"):
        user = User.query.get(session["user_id"])
        if user:
            return jsonify({"authenticated": True, "user": user.to_dict()})
    return jsonify({"authenticated": False, "user": None})


# ---------------------------------------------------------------------------
# User Management (superadmin only)
# ---------------------------------------------------------------------------


@auth_bp.route("/admin/users", methods=["GET"])
@superadmin_required
def user_management_page():
    return render_template("user_management.html")


@auth_bp.route("/api/admin/users/create", methods=["POST"])
@superadmin_required
@totp_required
def admin_create_user():
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400

    username = data.get("username", "").strip()
    password = data.get("password", "")
    bu = data.get("bu", "").strip().upper()

    if not username or not password:
        return jsonify({"success": False, "error": "Username and password are required"}), 400
    if len(username) < 3 or len(username) > 64:
        return jsonify({"success": False, "error": "Username must be 3-64 characters"}), 400
    if len(password) < 8:
        return jsonify({"success": False, "error": "Password must be at least 8 characters"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"success": False, "error": "Username already exists"}), 409

    from werkzeug.security import generate_password_hash

    user = User(
        username=username,
        password_hash=generate_password_hash(password, method="pbkdf2:sha256"),
        role="user",
        bu=bu,
        is_active=True,
    )
    db.session.add(user)
    db.session.commit()
    return jsonify({"success": True, "user": user.to_dict()})


@auth_bp.route("/api/admin/users", methods=["GET"])
@superadmin_required
def list_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify({"success": True, "users": [u.to_dict() for u in users]})


@auth_bp.route("/api/admin/users/<int:user_id>", methods=["PUT"])
@superadmin_required
def update_user(user_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    if "is_active" in data:
        user.is_active = bool(data["is_active"])
    if "role" in data and data["role"] in ("user",):
        user.role = data["role"]
    if "bu" in data:
        user.bu = data["bu"]

    db.session.commit()
    return jsonify({"success": True, "user": user.to_dict()})


@auth_bp.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
@superadmin_required
@totp_required
def delete_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user.role == "superadmin":
        return jsonify({"error": "Cannot delete superadmin"}), 403
    db.session.delete(user)
    db.session.commit()
    return jsonify({"success": True, "message": "User deleted"})
