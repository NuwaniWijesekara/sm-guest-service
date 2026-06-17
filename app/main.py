from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from .config.settings import settings
from .services.face_engine import face_engine

from sqlalchemy import create_engine, text, Column, String, DateTime, Enum as SAEnum, ForeignKey, Integer
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

engine = create_engine(settings.database_url, pool_pre_ping=True, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    face_engine.load()
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
app.include_router(guest_router)
app.include_router(match_router)

@app.get("/health")
def health():
    return {"service": "guest-bff", "status": "healthy"}