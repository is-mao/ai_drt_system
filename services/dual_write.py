"""Dual-write database service.

When LOCAL_DB_URI is configured alongside DATABASE_URL (remote),
all write operations are mirrored to both databases.
Remote failures are logged but never raise exceptions.
"""

import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

_remote_engine = None
_RemoteSession = None


def _get_remote_engine():
    """Lazily create the remote database engine."""
    global _remote_engine, _RemoteSession
    if _remote_engine is not None:
        return _remote_engine

    remote_url = os.environ.get("DATABASE_URL", "")
    if not remote_url:
        return None

    # Normalize postgres:// to postgresql://
    if remote_url.startswith("postgres://"):
        remote_url = remote_url.replace("postgres://", "postgresql://", 1)

    try:
        _remote_engine = create_engine(remote_url, pool_pre_ping=True, pool_size=2, max_overflow=3)
        _RemoteSession = sessionmaker(bind=_remote_engine)
        logger.info("Remote database engine initialized.")
        return _remote_engine
    except Exception as e:
        logger.warning(f"Failed to initialize remote database: {e}")
        _remote_engine = None
        return None


def is_dual_write_enabled():
    """Check if dual-write mode is active (both LOCAL_DB_URI and DATABASE_URL set)."""
    return bool(os.environ.get("LOCAL_DB_URI")) and bool(os.environ.get("DATABASE_URL"))


def sync_to_remote(report_dict):
    """Write a defect report dict to the remote database.
    Never raises — all errors are logged silently."""
    if not is_dual_write_enabled():
        return

    engine = _get_remote_engine()
    if not engine:
        return

    try:
        session = _RemoteSession()
        try:
            # Build INSERT with conflict handling
            columns = [k for k in report_dict if report_dict[k] is not None]
            col_names = ", ".join(columns)
            placeholders = ", ".join(f":{c}" for c in columns)
            params = {c: report_dict[c] for c in columns}

            sql = text(f"INSERT INTO defect_reports ({col_names}) VALUES ({placeholders})")
            session.execute(sql, params)
            session.commit()
            logger.debug("Remote sync: record written successfully.")
        except Exception as e:
            session.rollback()
            logger.warning(f"Remote sync failed (write): {e}")
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"Remote sync failed (session): {e}")


def sync_update_to_remote(report_id, report_dict):
    """Update a defect report on the remote database by id.
    Never raises."""
    if not is_dual_write_enabled():
        return

    engine = _get_remote_engine()
    if not engine:
        return

    try:
        session = _RemoteSession()
        try:
            columns = [k for k in report_dict if k != "id" and report_dict[k] is not None]
            set_clause = ", ".join(f"{c} = :{c}" for c in columns)
            params = {c: report_dict[c] for c in columns}
            params["_id"] = report_id

            sql = text(f"UPDATE defect_reports SET {set_clause} WHERE id = :_id")
            session.execute(sql, params)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.warning(f"Remote sync failed (update): {e}")
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"Remote sync failed (session): {e}")


def sync_delete_to_remote(report_id):
    """Delete a defect report from the remote database by id.
    Never raises."""
    if not is_dual_write_enabled():
        return

    engine = _get_remote_engine()
    if not engine:
        return

    try:
        session = _RemoteSession()
        try:
            session.execute(text("DELETE FROM defect_reports WHERE id = :_id"), {"_id": report_id})
            session.commit()
        except Exception as e:
            session.rollback()
            logger.warning(f"Remote sync failed (delete): {e}")
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"Remote sync failed (session): {e}")


def init_remote_tables():
    """Create tables on remote database if they don't exist. Never raises."""
    if not is_dual_write_enabled():
        return

    engine = _get_remote_engine()
    if not engine:
        return

    try:
        from models import db

        db.metadata.create_all(bind=engine)
        logger.info("Remote database tables synced.")
    except Exception as e:
        logger.warning(f"Remote table creation failed: {e}")
