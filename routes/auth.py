from models import db
from models.user import User
from flask import Blueprint, request, session, jsonify, render_template, redirect, url_for
from functools import wraps
from datetime import datetime

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
    return redirect(url_for("auth.login_page"))


@auth_bp.route("/api/auth/register", methods=["POST"])
def api_register():
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

    if User.query.filter_by(username=username).first():
        return jsonify({"success": False, "error": "Username already exists"}), 409

    user = User(username=username, role="user", is_active=False)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    return jsonify({"success": True, "message": "Registration successful. Please wait for admin approval."})


@auth_bp.route("/api/auth/login", methods=["POST"])
def api_login():
    data = request.get_json()

    if not data:
        return jsonify({"success": False, "error": "Invalid request body"}), 400

    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"success": False, "error": "Username and password are required"}), 400

    user = User.query.filter_by(username=username).first()

    if not user or not user.check_password(password):
        return jsonify({"success": False, "error": "Invalid username or password"}), 401

    if not user.is_active:
        return jsonify({"success": False, "error": "Account is pending approval. Please contact admin."}), 403

    # Update last login timestamp
    user.last_login = datetime.now()
    db.session.commit()

    # Set session data
    session.permanent = True
    session["user_id"] = user.id
    session["username"] = user.username
    session["role"] = user.role
    session["db_access"] = user.db_access

    return jsonify({"success": True, "message": "Login successful", "user": user.to_dict()})


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
    if "role" in data and data["role"] in ("user", "admin"):
        # Only allow setting user/admin, not superadmin
        if user.role != "superadmin":
            user.role = data["role"]
            # Admin automatically gets SQLite + Remote access
            if data["role"] == "admin":
                user.db_access = "both"
            elif user.db_access == "both":
                # Downgrading from admin to user: reset to sqlite
                user.db_access = "sqlite"
    if "db_access" in data and data["db_access"] in ("sqlite", "remote", "both"):
        if user.role != "superadmin":
            user.db_access = data["db_access"]

    db.session.commit()
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
    return jsonify({"success": True, "message": f'User "{user.username}" deleted'})
