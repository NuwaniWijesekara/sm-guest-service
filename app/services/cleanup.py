import threading
import time
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def cleanup_expired_records():
    from ..main import GuestSessionLocal
    from ..models.guest_models import SavedFace, SearchHistory
    
    db = GuestSessionLocal()
    now = datetime.utcnow()
    try:
        # 1. Delete expired Search History records (anonymous guests, 24h)
        expired_history = db.query(SearchHistory).filter(
            SearchHistory.expires_at != None,
            SearchHistory.expires_at < now
        ).all()
        if expired_history:
            for h in expired_history:
                db.delete(h)
            db.commit()
            logger.info(f"Cleanup: Deleted {len(expired_history)} expired search history records.")

        # 2. Delete expired Saved Face records (30 days)
        expired_faces = db.query(SavedFace).filter(
            SavedFace.expires_at < now
        ).all()
        if expired_faces:
            for f in expired_faces:
                db.delete(f)
            db.commit()
            logger.info(f"Cleanup: Deleted {len(expired_faces)} expired saved face records.")

    except Exception as e:
        db.rollback()
        logger.error(f"Error during cleanup execution: {e}")
    finally:
        db.close()


def prune_unreferenced_search_history():
    """
    Safety-net sweep: catches SearchHistory rows whose event no longer exists
    in the photographer DB but were never caught by the event.deleted stream
    (e.g. an Event row removed directly in Postgres, bypassing the API).
    """
    from ..main import GuestSessionLocal, PhotographerSessionLocal, SearchHistory
    from ..models.photographer_models import Event

    guest_db = GuestSessionLocal()
    photo_db = PhotographerSessionLocal()
    try:
        ids_in_history = {row.event_id for row in guest_db.query(SearchHistory.event_id).distinct()}
        if not ids_in_history:
            return

        existing_ids = {
            row.id for row in photo_db.query(Event.id).filter(Event.id.in_(ids_in_history))
        }
        orphaned_ids = ids_in_history - existing_ids

        if orphaned_ids:
            deleted = guest_db.query(SearchHistory).filter(
                SearchHistory.event_id.in_(orphaned_ids)
            ).delete(synchronize_session=False)
            guest_db.commit()
            logger.info(f"Cleanup: Pruned {deleted} orphaned SearchHistory row(s) (safety-net sweep).")

    except Exception as e:
        guest_db.rollback()
        logger.error(f"Error during orphan-prune sweep: {e}")
    finally:
        guest_db.close()
        photo_db.close()


def cleanup_loop(interval_seconds: int = 3600):
    logger.info("Cleanup scheduler loop started.")
    try:
        cleanup_expired_records()
        prune_unreferenced_search_history()
    except Exception as e:
        logger.error(f"Initial cleanup error: {e}")

    while True:
        time.sleep(interval_seconds)
        try:
            cleanup_expired_records()
            prune_unreferenced_search_history()
        except Exception as e:
            logger.error(f"Cleanup loop error: {e}")


def start_cleanup_scheduler(interval_seconds: int = 3600):
    thread = threading.Thread(target=cleanup_loop, args=(interval_seconds,), daemon=True, name="VectorCleanupDaemon")
    thread.start()
    logger.info("✓ Cleanup background daemon thread scheduled.")