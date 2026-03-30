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

    CORS(app)
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
    """Auto-add missing columns to existing tables."""
    from sqlalchemy import text, inspect

    ALLOWED_COLUMNS = {"sequence_log": "TEXT", "buffer_log": "TEXT"}

    try:
        inspector = inspect(db.engine)
        existing = {col["name"] for col in inspector.get_columns("defect_reports")}
        dialect = db.engine.dialect.name  # sqlite, mysql, postgresql
        with db.engine.connect() as conn:
            for col_name, col_type in ALLOWED_COLUMNS.items():
                if col_name not in existing:
                    # col_name and col_type are from hardcoded allowlist only
                    if dialect == "sqlite":
                        conn.execute(text(f"ALTER TABLE defect_reports ADD COLUMN {col_name} {col_type}"))
                    else:
                        conn.execute(text(f"ALTER TABLE defect_reports ADD COLUMN {col_name} {col_type} NULL"))
                    conn.commit()
                    app.logger.info(f"Added missing column: {col_name}")
    except Exception as e:
        app.logger.warning(f"Column migration skipped: {e}")


def _seed_defaults():
    from models.user import User
    from models.system_config import SystemConfig

    # Seed default admin if no users exist
    if User.query.count() == 0:
        admin = User(username="admin", role="admin")
        admin.set_password("admin123")
        db.session.add(admin)
        db.session.commit()

    # Seed default config
    if not db.session.get(SystemConfig, "gemini_api_key"):
        db.session.add(SystemConfig(config_key="gemini_api_key", config_value=""))
        db.session.commit()


app = create_app()

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=debug, host="0.0.0.0", port=port)
