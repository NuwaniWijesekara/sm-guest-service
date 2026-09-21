from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from ..utils.security import get_guest_db, get_photo_db, get_current_user
from ..models.guest_models import SearchHistory
from ..models.photographer_models import Event

from ..services.s3 import s3_service

router = APIRouter(prefix="/guest/history", tags=["Search History"])

class EventHistoryOut(BaseModel):
    id: str
    name: str
    date: datetime
    cover_photo_url: Optional[str] = None
    qr_token: str

    class Config:
        from_attributes = True

class PhotoHistoryOut(BaseModel):
    id: str
    s3_url: str
    thumbnail_url: Optional[str] = None

class SearchHistoryOut(BaseModel):
    id: str
    created_at: datetime
    event: Optional[EventHistoryOut] = None
    photos: list[PhotoHistoryOut]

@router.get("", response_model=list[SearchHistoryOut])
def get_search_history(
    guest_db: Session = Depends(get_guest_db),
    photo_db: Session = Depends(get_photo_db),
    current_user = Depends(get_current_user)
):
    history = guest_db.query(SearchHistory).filter(
        SearchHistory.user_id == current_user.id
    ).order_by(SearchHistory.created_at.desc()).all()

    event_ids = {h.event_id for h in history}
    events = {e.id: e for e in photo_db.query(Event).filter(Event.id.in_(event_ids)).all()} if event_ids else {}

    res = []
    for h in history:
        ev_out = None
        if h.event_id in events:
            ev = events[h.event_id]
            cover_url = s3_service.generate_presigned_url(ev.cover_photo_url, expiration=3600) if ev.cover_photo_url else None
            ev_out = EventHistoryOut(
                id=ev.id,
                name=ev.name,
                date=ev.date,
                cover_photo_url=cover_url,
                qr_token=ev.qr_token
            )
        
        photos_out = [
            PhotoHistoryOut(
                id=p.get("id", ""),
                s3_url=s3_service.generate_presigned_url(p.get("s3_url"), expiration=3600),
                thumbnail_url=s3_service.generate_presigned_url(p.get("thumbnail_url"), expiration=3600) if p.get("thumbnail_url") else None
            )
            for p in (h.matched_photos or [])
        ]

        res.append(SearchHistoryOut(id=h.id, created_at=h.created_at, event=ev_out, photos=photos_out))

    return res