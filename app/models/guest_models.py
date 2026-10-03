import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, JSON
from sqlalchemy.orm import declarative_base

GuestBase = declarative_base()

def _uuid():
    return str(uuid.uuid4())

# There is no local user table here anymore — every user (anonymous or not)
# lives in the unified `users` table owned by sm-photographer-service.
# `user_id` below is that table's id, stored as a plain string (not a FK:
# it's a different physical database — see PHOTOGRAPHER_DATABASE_URL, which
# this service only has read access to).

class SavedFace(GuestBase):
    __tablename__ = "saved_faces"
    id                  = Column(String, primary_key=True, default=_uuid)
    user_id             = Column(String, nullable=False, index=True)
    nickname            = Column(String, nullable=False)
    rekognition_face_id = Column(String, nullable=True)
    created_at          = Column(DateTime, default=datetime.utcnow)
    expires_at          = Column(DateTime, nullable=False)

class SearchHistory(GuestBase):
    __tablename__ = "search_history"
    id                  = Column(String, primary_key=True, default=_uuid)
    user_id             = Column(String, nullable=True, index=True)
    event_id            = Column(String, nullable=False)  # Stored as string, reference to external photographer DB
    rekognition_face_id = Column(String, nullable=True)
    matched_photos      = Column(JSON, nullable=True)     # JSON array containing matched photos metadata
    created_at          = Column(DateTime, default=datetime.utcnow)
    expires_at          = Column(DateTime, nullable=True)
