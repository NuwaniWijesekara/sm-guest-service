import socket
orig_getaddrinfo = socket.getaddrinfo
def patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = patched_getaddrinfo

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from .config.settings import settings
from .services.face_engine import face_engine
from .models.guest_models import GuestBase, SavedFace, SearchHistory
from .models.photographer_models import PhotographerBase, Event, EventStatus, Image

# ── Guest DB (owned — read/write) ────────────────────────────
guest_engine = create_engine(settings.guest_database_url, pool_pre_ping=True, pool_size=10, max_overflow=20)
GuestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=guest_engine)

# ── Photographer DB (foreign — read-only) ────────────────────
photographer_engine = create_engine(settings.photographer_database_url, pool_pre_ping=True, pool_size=5, max_overflow=10)
PhotographerSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=photographer_engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    with guest_engine.connect() as conn:
        conn.execute(text("ALTER TABLE saved_faces ADD COLUMN IF NOT EXISTS rekognition_face_id VARCHAR(255);"))
        conn.execute(text("ALTER TABLE saved_faces DROP COLUMN IF EXISTS face_embedding;"))
        conn.execute(text("ALTER TABLE search_history ADD COLUMN IF NOT EXISTS rekognition_face_id VARCHAR(255);"))
        conn.execute(text("ALTER TABLE search_history DROP COLUMN IF EXISTS face_embedding;"))

        # ── Unified User Model migration ──
        # guest_users no longer exists (merged into sm-photographer-service's
        # `users`), so saved_faces/search_history drop their FK to it and
        # keep a plain user_id string instead (see models/guest_models.py).
        for _table in ("saved_faces", "search_history"):
            conn.execute(text(f"ALTER TABLE {_table} DROP CONSTRAINT IF EXISTS {_table}_guest_user_id_fkey;"))
            conn.execute(text(f"""
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='{_table}' AND column_name='guest_user_id')
                    THEN ALTER TABLE {_table} RENAME COLUMN guest_user_id TO user_id; END IF;
                END $$;
            """))
        conn.execute(text("DROP TABLE IF EXISTS guest_users;"))
        conn.commit()
    GuestBase.metadata.create_all(bind=guest_engine)   # only guest-owned tables

    from .services.cleanup import start_cleanup_scheduler
    start_cleanup_scheduler()

    from .services.event_consumer import start_event_consumer
    start_event_consumer()

    print("✓ Guest service running on :8002")
    yield


app = FastAPI(title="ScanMe — Guest BFF", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from .api.guest import router as guest_router
from .api.match import router as match_router
from .api.saved_faces import router as saved_faces_router
from .api.history import router as guest_history_router

app.include_router(match_router)
app.include_router(saved_faces_router)
app.include_router(guest_history_router)
app.include_router(guest_router)


@app.get("/health")
def health():
    return {"service": "guest-bff", "status": "healthy"}