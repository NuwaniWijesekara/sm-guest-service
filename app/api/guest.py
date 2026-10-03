from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from ..utils.security import CurrentUser, get_optional_user, get_photo_db
from ..utils.access import require_gallery_access
from ..config.settings import settings
from ..models.photographer_models import Event, EventStatus, Image

router = APIRouter(prefix="/guest", tags=["Guest Access"])

class EventOut(BaseModel):
    id: str
    name: str
    date: datetime
    cover_photo_url: Optional[str] = None
    qr_token: Optional[str] = None
    username: Optional[str] = None
    total_photos: int
    status: str

class PhotoOut(BaseModel):
    id: str
    display_url: str
    thumbnail_url: Optional[str] = None

class EventPageResponse(BaseModel):
    event: EventOut
    photos: list[PhotoOut]

from ..services.s3 import s3_service

def _build_response(event, images) -> EventPageResponse:
    cover_url = s3_service.generate_presigned_url(event.cover_photo_url, expiration=settings.photo_url_ttl_seconds) if event.cover_photo_url else None
    return EventPageResponse(
        event=EventOut(
            id=event.id, name=event.name, date=event.date,
            cover_photo_url=cover_url,
            qr_token=event.qr_token, username=event.username,
            total_photos=len(images), status=event.status.value
        ),
        photos=[
            PhotoOut(
                id=img.id,
                display_url=s3_service.display_url(img.enhanced_url, img.s3_url, expiration=settings.photo_url_ttl_seconds),
                thumbnail_url=s3_service.generate_presigned_url(img.thumbnail_url, expiration=settings.photo_url_ttl_seconds) if img.thumbnail_url else None
            )
            for img in images
        ]
    )

@router.get("/validate/{qr_token}", response_model=EventPageResponse)
def validate_token(
    qr_token: str,
    db: Session = Depends(get_photo_db),
    user: Optional[CurrentUser] = Depends(get_optional_user),
):
    clean_token = qr_token.strip().lower().lstrip('@')
    event = db.query(Event).filter(
        or_(Event.qr_token == clean_token, Event.username == clean_token, Event.id == qr_token)
    ).first()
    if not event:
        raise HTTPException(status_code=404, detail="Invalid QR code or Collection Username")
    require_gallery_access(db, event, user)
    if event.status != EventStatus.READY:
        raise HTTPException(status_code=409, detail="Event still processing")
    images = db.query(Image).filter(Image.event_id == event.id).order_by(Image.created_at).all()
    return _build_response(event, images)

@router.get("/{event_id}", response_model=EventPageResponse)
def guest_by_id(
    event_id: str,
    db: Session = Depends(get_photo_db),
    user: Optional[CurrentUser] = Depends(get_optional_user),
):
    clean_id = event_id.strip().lower().lstrip('@')
    event = db.query(Event).filter(
        or_(Event.id == event_id, Event.qr_token == clean_id, Event.username == clean_id)
    ).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    require_gallery_access(db, event, user)
    if event.status != EventStatus.READY:
        raise HTTPException(status_code=409, detail="Event still processing")
    images = db.query(Image).filter(Image.event_id == event.id).order_by(Image.created_at).all()
    return _build_response(event, images)