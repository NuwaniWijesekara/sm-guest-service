from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from ..utils.security import get_guest_db, get_photo_db, get_current_guest
from ..models.guest_models import SearchHistory
from ..models.photographer_models import Event

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
    current_guest = Depends(get_current_guest)
):
    history = guest_db.query(SearchHistory).filter(
        SearchHistory.guest_user_id == current_guest.id
    ).order_by(SearchHistory.created_at.desc()).all()

    event_ids = {h.event_id for h in history}
    events = {e.id: e for e in photo_db.query(Event).filter(Event.id.in_(event_ids)).all()} if event_ids else {}

    return [
        SearchHistoryOut(
            id=h.id,
            created_at=h.created_at,
            event=EventHistoryOut.model_validate(events[h.event_id]) if h.event_id in events else None,
            photos=[PhotoHistoryOut(**p) for p in (h.matched_photos or [])]
        )
        for h in history
    ]