import socket
# Force IPv4 to prevent connection timeouts on systems with broken IPv6 routing
orig_getaddrinfo = socket.getaddrinfo
def patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = patched_getaddrinfo

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from .config.settings import settings
from .services.face_engine import face_engine

from sqlalchemy import create_engine, text, Column, String, DateTime, Enum as SAEnum, ForeignKey, Integer, Table, Boolean
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from pgvector.sqlalchemy import Vector
import uuid, enum
from datetime import datetime

Base = declarative_base()
def _uuid(): return str(uuid.uuid4())

class EventStatus(str, enum.Enum):
    PENDING    = "pending"
    PROCESSING = "processing"
    READY      = "ready"
    FAILED     = "failed"

class Event(Base):
    __tablename__ = "events"
    id              = Column(String, primary_key=True, default=_uuid)
    name            = Column(String, nullable=False)
    date            = Column(DateTime, nullable=False)
    cover_photo_url = Column(String, nullable=True)
    qr_token        = Column(String, unique=True, nullable=False, index=True)
    status          = Column(SAEnum(EventStatus), default=EventStatus.PENDING, nullable=False)
    photographer_id = Column(String, ForeignKey("users.id"), nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    total_photos    = Column(Integer, default=0)
    images          = relationship("Image", back_populates="event")

class Image(Base):
    __tablename__ = "images"
    id             = Column(String, primary_key=True, default=_uuid)
    event_id       = Column(String, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    s3_url         = Column(String, nullable=False)
    thumbnail_url  = Column(String, nullable=True)
    filename       = Column(String, nullable=False)
    face_embedding = Column(Vector(512), nullable=True)
    created_at     = Column(DateTime, default=datetime.utcnow)
    event          = relationship("Event", back_populates="images")

# Association table for Search History and Images
search_history_photos = Table(
    "search_history_photos",
    Base.metadata,
    Column("search_history_id", String, ForeignKey("search_history.id", ondelete="CASCADE"), primary_key=True),
    Column("image_id", String, ForeignKey("images.id", ondelete="CASCADE"), primary_key=True)
)

class GuestUser(Base):
    __tablename__ = "guest_users"
    id              = Column(String, primary_key=True, default=_uuid)
    email           = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String, nullable=True)
    name            = Column(String, nullable=True)
    is_anonymous    = Column(Boolean, default=False, nullable=False)
    created_at      = Column(DateTime, default=datetime.utcnow)
    
    saved_faces     = relationship("SavedFace", back_populates="guest", cascade="all, delete-orphan")
    search_history  = relationship("SearchHistory", back_populates="guest", cascade="all, delete-orphan")

class SavedFace(Base):
    __tablename__ = "saved_faces"
    id              = Column(String, primary_key=True, default=_uuid)
    guest_user_id   = Column(String, ForeignKey("guest_users.id", ondelete="CASCADE"), nullable=False)
    nickname        = Column(String, nullable=False)
    face_embedding  = Column(Vector(512), nullable=False)
    created_at      = Column(DateTime, default=datetime.utcnow)
    expires_at      = Column(DateTime, nullable=False)
    
    guest           = relationship("GuestUser", back_populates="saved_faces")

class SearchHistory(Base):
    __tablename__ = "search_history"
    id              = Column(String, primary_key=True, default=_uuid)
    guest_user_id   = Column(String, ForeignKey("guest_users.id", ondelete="CASCADE"), nullable=True)
    event_id        = Column(String, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    face_embedding  = Column(Vector(512), nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    expires_at      = Column(DateTime, nullable=True)
    
    guest           = relationship("GuestUser", back_populates="search_history")
    event           = relationship("Event")
    photos          = relationship("Image", secondary=search_history_photos)

engine = create_engine(settings.database_url, pool_pre_ping=True, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text("ALTER TABLE guest_users ADD COLUMN IF NOT EXISTS name VARCHAR"))
        conn.commit()
    Base.metadata.create_all(bind=engine)
    face_engine.load()
    
    from .services.cleanup import start_cleanup_scheduler
    start_cleanup_scheduler()
    
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
from .api.auth import router as guest_auth_router
from .api.saved_faces import router as saved_faces_router
from .api.history import router as guest_history_router

app.include_router(match_router)
app.include_router(guest_auth_router)
app.include_router(saved_faces_router)
app.include_router(guest_history_router)
app.include_router(guest_router)

@app.get("/health")
def health():
    return {"service": "guest-bff", "status": "healthy"}