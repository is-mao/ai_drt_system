"""Per-user database routing service.

Architecture:
- ismao (superadmin): MySQL (primary via Flask-SQLAlchemy) + auto-sync to Remote (Supabase)
- Other users: SQLite or Remote, as assigned by ismao via db_access field
"""

import os
import logging
from flask import g, session as flask_session
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

# Lazy-initialized engines
_sqlite_engine = None
_sqlite_session_factory = None
_remote_engine = None
_remote_session_factory = None


def _get_sqlite_engine():
    global _sqlite_engine, _sqlite_session_factory
    if _sqlite_engine is not None:
        return _sqlite_engine, _sqlite_session_factory
    from config import Config

    uri = Config.SQLITE_URI
    _sqlite_engine = create_engine(uri)
    _sqlite_session_factory = sessionmaker(bind=_sqlite_engine)
    logger.info("SQLite engine initialized: %s", uri)
    return _sqlite_engine, _sqlite_session_factory


def _get_remote_engine():
    global _remote_engine, _remote_session_factory
    if _remote_engine is not None:
        return _remote_engine, _remote_session_factory
    remote_url = os.environ.get("DATABASE_URL", "")
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


def get_user_db():
    """Get the UserDB adapter for the current request's user."""
    if "user_db" in g:
        return g.user_db

    from models import db

    role = flask_session.get("role")

    if role == "superadmin":
        udb = UserDB(db.session, is_primary=True, sync_remote=True)
    else:
        db_access = flask_session.get("db_access", "sqlite")
        if db_access == "both":
            # Admin: SQLite primary + remote sync
            _, factory = _get_sqlite_engine()
            if factory:
                udb = UserDB(factory(), is_primary=False, sync_remote=True)
            else:
                udb = UserDB(db.session, is_primary=True, sync_remote=True)
        elif db_access == "remote":
            _, factory = _get_remote_engine()
            if factory:
                udb = UserDB(factory(), is_primary=False, sync_remote=False)
            else:
                udb = UserDB(db.session, is_primary=True, sync_remote=False)
        else:
            _, factory = _get_sqlite_engine()
            if factory:
                udb = UserDB(factory(), is_primary=False, sync_remote=False)
            else:
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
                text("SELECT id, username, password_hash, role, db_access, is_active, last_login, created_at FROM users WHERE username = :u"),
                {"u": username},
            ).fetchone()
            if row:
                return {
                    "id": row[0], "username": row[1], "password_hash": row[2],
                    "role": row[3], "db_access": row[4], "is_active": row[5],
                    "last_login": row[6], "created_at": row[7],
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


def init_all_tables():
    """Create defect_reports table in SQLite and Remote databases. Never raises."""
    from models import db

    # SQLite
    try:
        engine, _ = _get_sqlite_engine()
        if engine:
            db.metadata.create_all(bind=engine)
            logger.info("SQLite tables synced.")
    except Exception as e:
        logger.warning("SQLite table creation failed: %s", e)

    # Remote
    try:
        engine, _ = _get_remote_engine()
        if engine:
            db.metadata.create_all(bind=engine)
            logger.info("Remote tables synced.")
    except Exception as e:
        logger.warning("Remote table creation failed: %s", e)
