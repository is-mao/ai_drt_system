from models import db
from models.user import User
from flask import Blueprint, request, session, jsonify, render_template, redirect, url_for
from functools import wraps
from datetime import datetime
from werkzeug.security import check_password_hash
from services.db_routing import (
    sync_user_to_remote,
    delete_user_from_remote,
    get_user_from_remote,
    update_user_login_remote,
    is_remote_configured,
    register_user_to_remote,
)

# The sole offline account — hardcoded, never synced to remote
OFFLINE_USERNAME = "cisco"

auth_bp = Blueprint("auth", __name__, url_prefix="")


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
    return render_template("login.html")


@auth_bp.route("/register", methods=["GET"])
def register_page():
    return redirect(url_for("auth.login"))


@auth_bp.route("/api/auth/register", methods=["POST"])
def api_register():
    """Register a new online account (written to remote DB only, not local)."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Invalid request body"}), 400

    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"success": False, "error": "Username and password are required"}), 400

    if len(username) < 3 or len(username) > 64:
        return jsonify({"success": False, "error": "Username must be 3-64 characters"}), 400

    if len(password) < 8:
        return jsonify({"success": False, "error": "Password must be at least 8 characters"}), 400

    # Block the reserved offline account name
    if username.lower() == OFFLINE_USERNAME:
        return jsonify({"success": False, "error": "This username is reserved"}), 409

    # Register directly to remote — never store in local
    from werkzeug.security import generate_password_hash

    password_hash = generate_password_hash(password, method="pbkdf2:sha256")
    ok, msg = register_user_to_remote(username, password_hash)
    if not ok:
        return jsonify({"success": False, "error": msg}), 409

    return jsonify({"success": True, "message": msg})


@auth_bp.route("/api/auth/login", methods=["POST"])
def api_login():
    data = request.get_json()

    if not data:
        return jsonify({"success": False, "error": "Invalid request body"}), 400

    username = data.get("username", "").strip()
    password = data.get("password", "")
    mode = data.get("mode", "offline").strip().lower()  # "offline" or "online"

    if mode not in ("offline", "online"):
        mode = "offline"

    if not username or not password:
        return jsonify({"success": False, "error": "Username and password are required"}), 400

    if mode == "online":
        # --- Online mode: authenticate against remote DB only ---
        remote_user = get_user_from_remote(username)
        if not remote_user:
            return jsonify({"success": False, "error": "Unable to connect to remote server, or user not found."}), 401

        if not check_password_hash(remote_user["password_hash"], password):
            return jsonify({"success": False, "error": "Invalid username or password"}), 401

        if not remote_user["is_active"]:
            return jsonify({"success": False, "error": "Account is pending approval. Please contact admin."}), 403

        now = datetime.now()
        update_user_login_remote(remote_user["id"], now)

        session.permanent = True
        session["user_id"] = remote_user["id"]
        session["username"] = remote_user["username"]
        session["role"] = remote_user["role"]
        session["mode"] = "online"

        return jsonify(
            {
                "success": True,
                "message": "Login successful (online mode)",
                "mode": "online",
                "user": remote_user,
            }
        )

    else:
        # --- Offline mode: only the reserved cisco account ---
        if username.lower() != OFFLINE_USERNAME:
            return jsonify({"success": False, "error": "Offline mode only supports the default cisco account."}), 401

        user = User.query.filter_by(username=OFFLINE_USERNAME).first()

        if not user or not user.check_password(password):
            return jsonify({"success": False, "error": "Invalid username or password"}), 401

        user.last_login = datetime.now()
        db.session.commit()

        session.permanent = True
        session["user_id"] = user.id
        session["username"] = user.username
        session["role"] = user.role
        session["mode"] = "offline"

        return jsonify(
            {
                "success": True,
                "message": "Login successful (offline mode)",
                "mode": "offline",
                "user": user.to_dict(),
            }
        )


@auth_bp.route("/api/auth/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"success": True, "message": "Logged out successfully"})


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


@auth_bp.route("/api/admin/users", methods=["GET"])
@superadmin_required
def list_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify({"success": True, "users": [u.to_dict() for u in users]})


@auth_bp.route("/api/admin/users/<int:user_id>", methods=["PUT"])
@superadmin_required
def update_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Prevent modifying the superadmin account
    if user.role == "superadmin" and user.id != session.get("user_id"):
        return jsonify({"error": "Cannot modify superadmin"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    if "is_active" in data:
        user.is_active = bool(data["is_active"])
    if "role" in data and data["role"] in ("user",):
        # Only allow setting user, not superadmin
        if user.role != "superadmin":
            user.role = data["role"]

    db.session.commit()

    # Sync changes to remote (include password_hash which to_dict omits)
    sync_user_to_remote(
        {
            "id": user.id,
            "username": user.username,
            "password_hash": user.password_hash,
            "role": user.role,
            "is_active": user.is_active,
        }
    )

    return jsonify({"success": True, "user": user.to_dict()})


@auth_bp.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
@superadmin_required
def delete_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    if user.role == "superadmin":
        return jsonify({"error": "Cannot delete superadmin"}), 403

    db.session.delete(user)
    db.session.commit()

    # Sync delete to remote
    delete_user_from_remote(user_id)

    return jsonify({"success": True, "message": f'User "{user.username}" deleted'})
