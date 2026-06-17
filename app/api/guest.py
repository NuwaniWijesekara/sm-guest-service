from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session
from fastapi import Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

router = APIRouter(prefix="/guest", tags=["Guest Access"])

def get_db():
    from ..main import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class EventOut(BaseModel):
    id: str
    name: str
    date: datetime
    cover_photo_url: Optional[str] = None
    total_photos: int
    status: str

class PhotoOut(BaseModel):
    id: str
    s3_url: str
    thumbnail_url: Optional[str] = None

class EventPageResponse(BaseModel):
    event: EventOut
    photos: list[PhotoOut]

def _build_response(event, images) -> EventPageResponse:
    return EventPageResponse(
        event=EventOut(
            id=event.id, name=event.name, date=event.date,
            cover_photo_url=event.cover_photo_url,
            total_photos=len(images), status=event.status.value
        ),
        photos=[PhotoOut(id=img.id, s3_url=img.s3_url, thumbnail_url=img.thumbnail_url) for img in images]
    )

@router.get("/validate/{qr_token}", response_model=EventPageResponse)
def validate_token(qr_token: str, db: Session = Depends(get_db)):
    from ..main import Event, EventStatus, Image
    event = db.query(Event).filter(Event.qr_token == qr_token).first()
    if not event:
        raise HTTPException(status_code=404, detail="Invalid QR code")
    if event.status != EventStatus.READY:
        raise HTTPException(status_code=409, detail="Event still processing")
    images = db.query(Image).filter(Image.event_id == event.id).order_by(Image.created_at).all()
    return _build_response(event, images)

@router.get("/{event_id}", response_model=EventPageResponse)
def guest_by_id(event_id: str, db: Session = Depends(get_db)):
    from ..main import Event, EventStatus, Image
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.status != EventStatus.READY:
        raise HTTPException(status_code=409, detail="Event still processing")
    images = db.query(Image).filter(Image.event_id == event.id).order_by(Image.created_at).all()
    return _build_response(event, images)