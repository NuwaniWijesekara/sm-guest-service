from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from ..utils.security import get_db, get_current_guest
from ..main import SearchHistory

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

    class Config:
        from_attributes = True

class SearchHistoryOut(BaseModel):
    id: str
    created_at: datetime
    event: EventHistoryOut
    photos: list[PhotoHistoryOut]

    class Config:
        from_attributes = True

@router.get("", response_model=list[SearchHistoryOut])
def get_search_history(
    db: Session = Depends(get_db),
    current_guest = Depends(get_current_guest)
):
    history = db.query(SearchHistory).filter(
        SearchHistory.guest_user_id == current_guest.id
    ).order_by(SearchHistory.created_at.desc()).all()
    return history
