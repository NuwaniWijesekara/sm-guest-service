import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Enum as SAEnum, ForeignKey, Integer, Boolean
from sqlalchemy.orm import relationship, declarative_base

PhotographerBase = declarative_base()

def _uuid():
    return str(uuid.uuid4())

class EventStatus(str, enum.Enum):
    PENDING    = "pending"
    PROCESSING = "processing"
    READY      = "ready"
    FAILED     = "failed"

class User(PhotographerBase):
    __tablename__ = "users"
    id              = Column(String, primary_key=True, default=_uuid)
    name            = Column(String, nullable=True)
    email           = Column(String, unique=True, index=True, nullable=True)
    password_hash   = Column(String, nullable=True)
    is_anonymous    = Column(Boolean, default=False, nullable=False)
    created_at      = Column(DateTime, default=datetime.utcnow)
    events          = relationship("Event", back_populates="owner", cascade="all, delete-orphan")

class Event(PhotographerBase):
    __tablename__ = "events"
    id              = Column(String, primary_key=True, default=_uuid)
    name            = Column(String, nullable=False)
    date            = Column(DateTime, nullable=False)
    drive_url       = Column(String, nullable=True)
    cover_photo_url = Column(String, nullable=True)
    qr_token        = Column(String, unique=True, nullable=False, index=True)
    username        = Column(String, unique=True, nullable=True, index=True)
    status          = Column(SAEnum(EventStatus), default=EventStatus.PENDING, nullable=False)
    owner_id        = Column(String, ForeignKey("users.id"), nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    total_photos    = Column(Integer, default=0)
    owner           = relationship("User", back_populates="events")
    images          = relationship("Image", back_populates="event", cascade="all, delete-orphan")

class Image(PhotographerBase):
    __tablename__ = "images"
    id             = Column(String, primary_key=True, default=_uuid)
    event_id       = Column(String, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    s3_url         = Column(String, nullable=False)
    thumbnail_url  = Column(String, nullable=True)
    filename       = Column(String, nullable=False)
    created_at     = Column(DateTime, default=datetime.utcnow)
    event          = relationship("Event", back_populates="images")
    faces          = relationship("Face", back_populates="image", cascade="all, delete-orphan")

class Face(PhotographerBase):
    __tablename__ = "faces"
    id                  = Column(String, primary_key=True, default=_uuid)
    image_id            = Column(String, ForeignKey("images.id", ondelete="CASCADE"), nullable=False, index=True)
    rekognition_face_id = Column(String, nullable=False, index=True)
    created_at          = Column(DateTime, default=datetime.utcnow)
    image               = relationship("Image", back_populates="faces")
