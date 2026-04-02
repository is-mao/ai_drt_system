"""Database routing service.

Architecture:
- Offline mode: SQLite (local, zero-config) via Flask-SQLAlchemy db.session
- Online mode: Remote database (MySQL) via DATABASE_URL
- All users follow the same routing. Superadmin has no special DB treatment.
"""

import os
import logging
from flask import g, session as flask_session
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

# Lazy-initialized remote engine
_remote_engine = None
_remote_session_factory = None


def reset_remote_engine():
    """Reset the cached remote engine so it will be re-initialized on next use."""
    global _remote_engine, _remote_session_factory
    if _remote_engine is not None:
        try:
            _remote_engine.dispose()
        except Exception:
            pass
    _remote_engine = None
    _remote_session_factory = None


def _get_remote_engine():
    global _remote_engine, _remote_session_factory
    if _remote_engine is not None:
        return _remote_engine, _remote_session_factory
    remote_url = os.environ.get("DATABASE_URL", "")
    if not remote_url:
        # Fallback: check system_config table for database_url
        try:
            from models.system_config import SystemConfig

            remote_url = SystemConfig.get_value("database_url", "") or ""
        except Exception:
            pass
    if not remote_url:
        return None, None
    if remote_url.startswith("postgres://"):
        remote_url = remote_url.replace("postgres://", "postgresql://", 1)
    try:
        _remote_engine = create_engine(remote_url, pool_pre_ping=True, pool_size=2, max_overflow=3)
        _remote_session_factory = sessionmaker(bind=_remote_engine)
        logger.info("Remote database engine initialized.")
        return _remote_engine, _remote_session_factory
    except Exception as e:
        logger.warning("Failed to init remote engine: %s", e)
        return None, None


class UserDB:
    """Database adapter routed to the current user's assigned database."""

    def __init__(self, session_obj, is_primary=False, sync_remote=False):
        self.session = session_obj
        self._is_primary = is_primary
        self._sync_remote = sync_remote

    @property
    def should_sync_remote(self):
        return self._sync_remote

    def get_or_404(self, model, ident):
        obj = self.session.get(model, ident)
        if obj is None:
            from flask import abort

            abort(404)
        return obj

    def close(self):
        if not self._is_primary:
            try:
                self.session.close()
            except Exception:
                pass


def is_remote_configured():
    """Return True if a remote DATABASE_URL is available (env or system_config)."""
    if os.environ.get("DATABASE_URL", ""):
        return True
    try:
        from models.system_config import SystemConfig

        return bool(SystemConfig.get_value("database_url", ""))
    except Exception:
        return False


def get_user_db():
    """Get the UserDB adapter for the current request's user.

    Routing based on session['mode']:
    - online: Remote database via global DATABASE_URL
    - offline (default): SQLite
    """
    if "user_db" in g:
        return g.user_db

    from models import db

    mode = flask_session.get("mode", "offline")

    if mode == "online":
        _, factory = _get_remote_engine()
        if factory:
            udb = UserDB(factory(), is_primary=False, sync_remote=False)
        else:
            logger.warning("Online mode but no DATABASE_URL configured, falling back to SQLite")
            udb = UserDB(db.session, is_primary=True, sync_remote=False)
    else:
        # offline mode — use SQLite (which is the primary db.session)
        udb = UserDB(db.session, is_primary=True, sync_remote=False)

    g.user_db = udb
    return udb


def cleanup_user_db(exc=None):
    """Close non-primary sessions after each request."""
    udb = g.pop("user_db", None)
    if udb:
        udb.close()


# ---------------------------------------------------------------------------
# Remote sync helpers (for ismao's dual-write to Supabase)
# ---------------------------------------------------------------------------


def sync_to_remote(report_dict):
    """Write a defect report dict to the remote database. Never raises."""
    engine, _ = _get_remote_engine()
    if not engine:
        return
    try:
        sess = _remote_session_factory()
        try:
            columns = [k for k in report_dict if report_dict[k] is not None]
            col_names = ", ".join(columns)
            placeholders = ", ".join(f":{c}" for c in columns)
            params = {c: report_dict[c] for c in columns}
            sess.execute(text(f"INSERT INTO defect_reports ({col_names}) VALUES ({placeholders})"), params)
            sess.commit()
        except Exception as e:
            sess.rollback()
            logger.warning("Remote sync failed (write): %s", e)
        finally:
            sess.close()
    except Exception as e:
        logger.warning("Remote sync failed (session): %s", e)


def sync_update_to_remote(report_id, report_dict):
    """Update a defect report on the remote database. Never raises."""
    engine, _ = _get_remote_engine()
    if not engine:
        return
    try:
        sess = _remote_session_factory()
        try:
            columns = [k for k in report_dict if k != "id" and report_dict[k] is not None]
            set_clause = ", ".join(f"{c} = :{c}" for c in columns)
            params = {c: report_dict[c] for c in columns}
            params["_id"] = report_id
            sess.execute(text(f"UPDATE defect_reports SET {set_clause} WHERE id = :_id"), params)
            sess.commit()
        except Exception as e:
            sess.rollback()
            logger.warning("Remote sync failed (update): %s", e)
        finally:
            sess.close()
    except Exception as e:
        logger.warning("Remote sync failed (session): %s", e)


def sync_delete_to_remote(report_id):
    """Delete a defect report from the remote database. Never raises."""
    engine, _ = _get_remote_engine()
    if not engine:
        return
    try:
        sess = _remote_session_factory()
        try:
            sess.execute(text("DELETE FROM defect_reports WHERE id = :_id"), {"_id": report_id})
            sess.commit()
        except Exception as e:
            sess.rollback()
            logger.warning("Remote sync failed (delete): %s", e)
        finally:
            sess.close()
    except Exception as e:
        logger.warning("Remote sync failed (session): %s", e)


# ---------------------------------------------------------------------------
# User sync helpers (sync user table to Remote for multi-machine auth)
# ---------------------------------------------------------------------------


def register_user_to_remote(username, password_hash, role="user", is_active=False, bu=""):
    """Register a new user directly to the remote database.

    Returns (True, message) on success, (False, error) on failure.
    """
    engine, _ = _get_remote_engine()
    if not engine:
        return False, "Remote database is not configured. Cannot register online accounts."
    try:
        sess = _remote_session_factory()
        try:
            # Check if username already exists
            row = sess.execute(
                text("SELECT id FROM users WHERE username = :u"),
                {"u": username},
            ).fetchone()
            if row:
                return False, "Username already exists"
            sess.execute(
                text(
                    "INSERT INTO users (username, password_hash, role, bu, is_active) "
                    "VALUES (:username, :password_hash, :role, :bu, :is_active)"
                ),
                {
                    "username": username,
                    "password_hash": password_hash,
                    "role": role,
                    "bu": bu,
                    "is_active": is_active,
                },
            )
            sess.commit()
            logger.info("User '%s' registered to remote (BU=%s).", username, bu)
            return True, "Registration successful. Please wait for admin approval."
        except Exception as e:
            sess.rollback()
            logger.warning("Remote registration failed: %s", e)
            return False, "Registration failed. Please try again later."
        finally:
            sess.close()
    except Exception as e:
        logger.warning("Remote registration failed (session): %s", e)
        return False, "Unable to connect to remote server."


def sync_user_to_remote(user_dict):
    """Upsert a user record to the remote database. Never raises."""
    engine, _ = _get_remote_engine()
    if not engine:
        return
    try:
        sess = _remote_session_factory()
        try:
            # Ensure is_active is bool (MySQL returns int, PostgreSQL needs bool)
            if "is_active" in user_dict:
                user_dict["is_active"] = bool(user_dict["is_active"])
            # Check if user exists
            row = sess.execute(
                text("SELECT id FROM users WHERE id = :_id"),
                {"_id": user_dict["id"]},
            ).fetchone()
            cols = [k for k in user_dict if k != "id" and user_dict[k] is not None]
            if row:
                set_clause = ", ".join(f"{c} = :{c}" for c in cols)
                params = {c: user_dict[c] for c in cols}
                params["_id"] = user_dict["id"]
                sess.execute(text(f"UPDATE users SET {set_clause} WHERE id = :_id"), params)
            else:
                all_cols = ["id"] + cols
                col_names = ", ".join(all_cols)
                placeholders = ", ".join(f":{c}" for c in all_cols)
                params = {c: user_dict[c] for c in all_cols}
                sess.execute(text(f"INSERT INTO users ({col_names}) VALUES ({placeholders})"), params)
            sess.commit()
            logger.info("User #%s synced to remote.", user_dict["id"])
        except Exception as e:
            sess.rollback()
            logger.warning("User sync failed (write): %s", e)
        finally:
            sess.close()
    except Exception as e:
        logger.warning("User sync failed (session): %s", e)


def delete_user_from_remote(user_id):
    """Delete a user from the remote database. Never raises."""
    engine, _ = _get_remote_engine()
    if not engine:
        return
    try:
        sess = _remote_session_factory()
        try:
            sess.execute(text("DELETE FROM users WHERE id = :_id"), {"_id": user_id})
            sess.commit()
        except Exception as e:
            sess.rollback()
            logger.warning("User delete sync failed: %s", e)
        finally:
            sess.close()
    except Exception as e:
        logger.warning("User delete sync failed (session): %s", e)


def get_user_from_remote(username):
    """Fetch a user dict from remote DB by username. Returns dict or None. Never raises."""
    engine, _ = _get_remote_engine()
    if not engine:
        return None
    try:
        sess = _remote_session_factory()
        try:
            row = sess.execute(
                text(
                    "SELECT id, username, password_hash, role, bu, is_active, last_login, created_at FROM users WHERE username = :u"
                ),
                {"u": username},
            ).fetchone()
            if row:
                return {
                    "id": row[0],
                    "username": row[1],
                    "password_hash": row[2],
                    "role": row[3],
                    "bu": row[4] or "",
                    "is_active": row[5],
                    "last_login": row[6],
                    "created_at": row[7],
                }
            return None
        except Exception as e:
            logger.warning("Remote user lookup failed: %s", e)
            return None
        finally:
            sess.close()
    except Exception as e:
        logger.warning("Remote user lookup failed (session): %s", e)
        return None


def update_user_login_remote(user_id, last_login):
    """Update last_login timestamp on remote. Never raises."""
    engine, _ = _get_remote_engine()
    if not engine:
        return
    try:
        sess = _remote_session_factory()
        try:
            sess.execute(text("UPDATE users SET last_login = :t WHERE id = :_id"), {"t": last_login, "_id": user_id})
            sess.commit()
        except Exception as e:
            sess.rollback()
            logger.warning("Remote login update failed: %s", e)
        finally:
            sess.close()
    except Exception as e:
        logger.warning("Remote login update failed (session): %s", e)


# ---------------------------------------------------------------------------
# Remote-first user management (for superadmin to manage remote users)
# ---------------------------------------------------------------------------


def list_all_remote_users():
    """List all users from the remote database. Returns list of dicts or None on error."""
    engine, _ = _get_remote_engine()
    if not engine:
        return None
    try:
        sess = _remote_session_factory()
        try:
            rows = sess.execute(
                text(
                    "SELECT id, username, role, bu, is_active, last_login, created_at "
                    "FROM users ORDER BY created_at DESC"
                )
            ).fetchall()
            return [
                {
                    "id": r[0],
                    "username": r[1],
                    "role": r[2],
                    "bu": r[3] or "",
                    "is_active": bool(r[4]) if r[4] is not None else True,
                    "last_login": r[5].strftime("%Y-%m-%d %H:%M:%S") if r[5] else None,
                    "created_at": r[6].strftime("%Y-%m-%d %H:%M:%S") if r[6] else None,
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning("Remote user list failed: %s", e)
            return None
        finally:
            sess.close()
    except Exception as e:
        logger.warning("Remote user list failed (session): %s", e)
        return None


def update_remote_user(user_id, updates):
    """Update a user record in the remote database.

    updates: dict of column->value (e.g. {"is_active": True}).
    Returns (True, user_dict) on success, (False, error_msg) on failure.
    """
    engine, _ = _get_remote_engine()
    if not engine:
        return False, "Remote database not configured."
    try:
        sess = _remote_session_factory()
        try:
            row = sess.execute(
                text("SELECT id, role FROM users WHERE id = :_id"),
                {"_id": user_id},
            ).fetchone()
            if not row:
                return False, "User not found"
            if row[1] == "superadmin" and "role" in updates:
                return False, "Cannot modify superadmin role"

            allowed = {"is_active", "role", "bu"}
            cols = {k: v for k, v in updates.items() if k in allowed}
            if not cols:
                return False, "No valid fields to update"

            set_clause = ", ".join(f"{c} = :{c}" for c in cols)
            params = dict(cols)
            params["_id"] = user_id
            sess.execute(text(f"UPDATE users SET {set_clause} WHERE id = :_id"), params)
            sess.commit()

            # Fetch updated row
            updated = sess.execute(
                text(
                    "SELECT id, username, role, bu, is_active, last_login, created_at "
                    "FROM users WHERE id = :_id"
                ),
                {"_id": user_id},
            ).fetchone()
            if updated:
                user_dict = {
                    "id": updated[0],
                    "username": updated[1],
                    "role": updated[2],
                    "bu": updated[3] or "",
                    "is_active": bool(updated[4]) if updated[4] is not None else True,
                    "last_login": updated[5].strftime("%Y-%m-%d %H:%M:%S") if updated[5] else None,
                    "created_at": updated[6].strftime("%Y-%m-%d %H:%M:%S") if updated[6] else None,
                }
                return True, user_dict
            return True, {}
        except Exception as e:
            sess.rollback()
            logger.warning("Remote user update failed: %s", e)
            return False, str(e)
        finally:
            sess.close()
    except Exception as e:
        logger.warning("Remote user update failed (session): %s", e)
        return False, str(e)


def delete_remote_user(user_id):
    """Delete a user from the remote database.

    Returns (True, message) on success, (False, error_msg) on failure.
    """
    engine, _ = _get_remote_engine()
    if not engine:
        return False, "Remote database not configured."
    try:
        sess = _remote_session_factory()
        try:
            row = sess.execute(
                text("SELECT id, username, role FROM users WHERE id = :_id"),
                {"_id": user_id},
            ).fetchone()
            if not row:
                return False, "User not found"
            if row[2] == "superadmin":
                return False, "Cannot delete superadmin"
            username = row[1]
            sess.execute(text("DELETE FROM users WHERE id = :_id"), {"_id": user_id})
            sess.commit()
            return True, f'User "{username}" deleted'
        except Exception as e:
            sess.rollback()
            logger.warning("Remote user delete failed: %s", e)
            return False, str(e)
        finally:
            sess.close()
    except Exception as e:
        logger.warning("Remote user delete failed (session): %s", e)
        return False, str(e)


def init_all_tables():
    """Create tables in remote database (if configured). Never raises.

    SQLite tables are handled by Flask-SQLAlchemy db.create_all() in app.py.
    """
    from models import db

    # Remote
    try:
        engine, _ = _get_remote_engine()
        if engine:
            db.metadata.create_all(bind=engine)
            # Migrate missing columns in remote DB
            _migrate_remote_columns(engine)
            logger.info("Remote tables synced.")
    except Exception as e:
        logger.warning("Remote table creation failed: %s", e)


def _migrate_remote_columns(engine):
    """Add missing columns to remote database tables. Never raises."""
    REMOTE_MIGRATIONS = {
        "users": {"bu": "VARCHAR(20) DEFAULT ''"},
    }
    try:
        from sqlalchemy import inspect as sa_inspect

        inspector = sa_inspect(engine)
        with engine.connect() as conn:
            for table, columns in REMOTE_MIGRATIONS.items():
                try:
                    existing = {col["name"] for col in inspector.get_columns(table)}
                except Exception:
                    continue
                for col_name, col_type in columns.items():
                    if col_name not in existing:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"))
                        conn.commit()
                        logger.info("Remote: added column %s.%s", table, col_name)
    except Exception as e:
        logger.warning("Remote column migration failed: %s", e)


# ---------------------------------------------------------------------------
# Bulk sync: push all local (SQLite) defect reports → remote database
# ---------------------------------------------------------------------------

def sync_all_local_to_remote():
    """Read all defect_reports from local SQLite and upsert to remote DB.

    Returns (synced_count, skipped_count, error_message_or_None).
    """
    engine, _ = _get_remote_engine()
    if not engine:
        return 0, 0, "Remote database is not configured."

    from models import db as local_db
    from models.defect_report import DefectReport

    # Read all local records
    local_reports = local_db.session.query(DefectReport).all()
    if not local_reports:
        return 0, 0, None  # nothing to sync

    columns = [
        "bu", "week_number", "pcap_n", "station", "server", "sn",
        "record_time", "failure", "defect_class", "defect_value",
        "root_cause", "action", "pn", "component_sn", "log_content",
        "sequence_log", "buffer_log", "ai_root_cause", "status",
        "created_by", "created_at", "updated_at",
    ]

    try:
        sess = _remote_session_factory()
    except Exception as e:
        return 0, 0, f"Failed to connect to remote: {e}"

    synced = 0
    skipped = 0
    try:
        # Build a set of existing remote SNs + record_times for dedup
        existing_rows = sess.execute(
            text("SELECT sn, record_time FROM defect_reports")
        ).fetchall()
        existing_keys = set()
        for row in existing_rows:
            key = (str(row[0] or "").strip(), str(row[1] or "").strip())
            existing_keys.add(key)

        for report in local_reports:
            # Dedup by (sn, record_time)
            rt_str = report.record_time.strftime("%Y-%m-%d %H:%M:%S") if report.record_time else ""
            local_key = (str(report.sn or "").strip(), rt_str)
            if local_key in existing_keys:
                skipped += 1
                continue

            params = {}
            for col in columns:
                val = getattr(report, col, None)
                if val is not None and hasattr(val, "strftime"):
                    val = val.strftime("%Y-%m-%d %H:%M:%S")
                params[col] = val

            non_null_cols = [c for c in columns if params[c] is not None]
            col_names = ", ".join(non_null_cols)
            placeholders = ", ".join(f":{c}" for c in non_null_cols)
            insert_params = {c: params[c] for c in non_null_cols}

            sess.execute(
                text(f"INSERT INTO defect_reports ({col_names}) VALUES ({placeholders})"),
                insert_params,
            )
            synced += 1

        sess.commit()
        logger.info("Bulk sync complete: %d synced, %d skipped (duplicates).", synced, skipped)
        return synced, skipped, None
    except Exception as e:
        sess.rollback()
        logger.warning("Bulk sync failed: %s", e)
        return synced, skipped, str(e)
    finally:
        sess.close()
