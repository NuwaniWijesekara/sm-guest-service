import threading
import time
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def cleanup_expired_records():
    from ..main import SessionLocal, SavedFace, SearchHistory
    
    db = SessionLocal()
    now = datetime.utcnow()
    try:
        # 1. Delete expired Search History records (for anonymous guests' embeddings after 24 hours)
        expired_history = db.query(SearchHistory).filter(
            SearchHistory.expires_at != None,
            SearchHistory.expires_at < now
        ).all()
        if expired_history:
            for h in expired_history:
                db.delete(h)
            db.commit()
            logger.info(f"Cleanup: Deleted {len(expired_history)} expired search history records.")
            
        # 2. Delete expired Saved Face records (after 30 days of inactivity/upload)
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

def cleanup_loop(interval_seconds: int = 3600):
    logger.info("Cleanup scheduler loop started.")
    # Run once immediately on startup
    try:
        cleanup_expired_records()
    except Exception as e:
        logger.error(f"Initial cleanup error: {e}")
        
    while True:
        time.sleep(interval_seconds)
        try:
            cleanup_expired_records()
        except Exception as e:
            logger.error(f"Cleanup loop error: {e}")

def start_cleanup_scheduler(interval_seconds: int = 3600):
    thread = threading.Thread(target=cleanup_loop, args=(interval_seconds,), daemon=True, name="VectorCleanupDaemon")
    thread.start()
    logger.info("✓ Cleanup background daemon thread scheduled.")
