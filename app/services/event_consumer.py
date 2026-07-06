import logging
import time
import threading
import redis
from ..config.settings import settings

logger = logging.getLogger(__name__)

STREAM_NAME    = "event.deleted"
CONSUMER_GROUP = "guest-cleanup"
CONSUMER_NAME  = "guest-worker-1"

r = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_timeout=10,
    socket_connect_timeout=5,
    retry_on_timeout=True,
)


def ensure_group():
    try:
        r.xgroup_create(STREAM_NAME, CONSUMER_GROUP, id="0", mkstream=True)
        logger.info(f"Consumer group '{CONSUMER_GROUP}' created")
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" in str(e):
            logger.info("Consumer group already exists")
        else:
            raise


def handle_event_deleted(event_id: str):
    from ..main import GuestSessionLocal
    from ..models.guest_models import SearchHistory

    db = GuestSessionLocal()
    try:
        deleted = db.query(SearchHistory).filter(SearchHistory.event_id == event_id).delete()
        db.commit()
        logger.info(f"Pruned {deleted} SearchHistory row(s) for deleted event {event_id}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def consume_loop():
    ensure_group()
    logger.info("Guest event-deleted consumer started — listening on Redis Stream")

    while True:
        try:
            messages = r.xreadgroup(
                CONSUMER_GROUP,
                CONSUMER_NAME,
                {STREAM_NAME: ">"},
                count=10,
                block=5000
            )

            if not messages:
                continue

            for _stream, entries in messages:
                for msg_id, data in entries:
                    event_id = data.get("event_id")
                    try:
                        handle_event_deleted(event_id)
                        r.xack(STREAM_NAME, CONSUMER_GROUP, msg_id)  # ack only on success
                    except Exception as e:
                        logger.error(f"Failed processing message {msg_id} (event {event_id}): {e}")
                        # Not acked → redelivered later, same guarantee as the ingestion worker

        except redis.exceptions.ConnectionError:
            logger.warning("Redis connection lost, retrying in 5s...")
            time.sleep(5)
        except KeyboardInterrupt:
            logger.info("Guest event consumer stopped")
            break


def start_event_consumer():
    thread = threading.Thread(target=consume_loop, daemon=True, name="EventDeletedConsumer")
    thread.start()
    logger.info("✓ Guest event-deleted consumer thread scheduled")