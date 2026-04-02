import os
import click
from flask import Flask, redirect, url_for
from flask_cors import CORS

# Load .env file BEFORE importing Config (class vars read os.environ at import time)
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from config import Config
from models import db


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.permanent_session_lifetime = Config.PERMANENT_SESSION_LIFETIME

    CORS(app, origins=os.environ.get("CORS_ORIGINS", "*").split(","))
    db.init_app(app)

    # Register blueprints
    from routes.auth import auth_bp
    from routes.defect_reports import defects_bp
    from routes.dashboard import dashboard_bp
    from routes.import_export import import_export_bp
    from routes.ai_analysis import ai_bp
    from routes.settings import settings_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(defects_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(import_export_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(settings_bp)

    @app.route("/")
    def index():
        return redirect(url_for("dashboard.dashboard_page"))

    # Create tables and migrate schema
    with app.app_context():
        db.create_all()
        _migrate_columns(app)
        _seed_defaults()

        # Initialize tables in SQLite and Remote databases
        from services.db_routing import init_all_tables, cleanup_user_db

        init_all_tables()

    # Cleanup non-primary DB sessions after each request
    @app.teardown_appcontext
    def _teardown_user_db(exc):
        from services.db_routing import cleanup_user_db

        cleanup_user_db(exc)

    # CLI commands
    @app.cli.command("create-admin")
    @click.option("--username", default="admin", help="Admin username")
    @click.option("--password", default="admin123", help="Admin password")
    def create_admin(username, password):
        from models.user import User

        with app.app_context():
            if User.query.filter_by(username=username).first():
                click.echo(f'User "{username}" already exists.')
                return
            user = User(username=username, role="admin")
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            click.echo(f'Admin user "{username}" created.')

    return app


def _migrate_columns(app):
    """Auto-add missing columns to existing SQLite tables."""
    from sqlalchemy import text, inspect

    MIGRATIONS = {
        "defect_reports": {"sequence_log": "TEXT", "buffer_log": "TEXT"},
        "users": {"is_active": "BOOLEAN DEFAULT 1", "bu": "VARCHAR(20) DEFAULT ''"},
    }

    try:
        inspector = inspect(db.engine)
        with db.engine.connect() as conn:
            for table, columns in MIGRATIONS.items():
                try:
                    existing = {col["name"] for col in inspector.get_columns(table)}
                except Exception:
                    continue
                for col_name, col_type in columns.items():
                    if col_name not in existing:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"))
                        conn.commit()
                        app.logger.info(f"Added missing column: {table}.{col_name}")
    except Exception as e:
        app.logger.warning(f"Column migration skipped: {e}")


def _seed_defaults():
    from models.user import User
    from models.system_config import SystemConfig

    # Seed superadmin if not exists
    if not User.query.filter_by(username="ismao").first():
        sa = User(username="ismao", role="superadmin", is_active=True)
        sa.set_password("maomao123")
        db.session.add(sa)
        db.session.commit()

    # Seed the default offline account (cisco/cisco) — the only local account for offline mode
    cisco = User.query.filter_by(username="cisco").first()
    if not cisco:
        cisco = User(username="cisco", role="user", is_active=True)
        cisco.set_password("cisco")
        db.session.add(cisco)
        db.session.commit()

    # Ensure existing users without is_active flag are set to active
    User.query.filter(User.is_active.is_(None)).update({"is_active": True})
    db.session.commit()

    # Seed default config
    if not db.session.get(SystemConfig, "gemini_api_key"):
        db.session.add(SystemConfig(config_key="gemini_api_key", config_value=""))
        db.session.commit()


app = create_app()

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    port = int(os.environ.get("PORT", 5001))
    app.run(
        debug=debug,
        host="0.0.0.0",
        port=port,
        exclude_patterns=["*.pyc", ".*", ".venv/*", "venv/*", "__pycache__/*", "logs/*"],
    )
