from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import numpy as np
from ..utils.security import get_current_guest

router = APIRouter(prefix="/match", tags=["Selfie Matching"])

def get_db():
    from ..main import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class MatchResultOut(BaseModel):
    photo_id: str
    s3_url: str
    thumbnail_url: Optional[str] = None
    similarity_score: float

class MatchResponse(BaseModel):
    matches: list[MatchResultOut]
    total: int

@router.post("/selfie", response_model=MatchResponse)
async def match_selfie(
    selfie: Optional[UploadFile] = File(None),
    saved_face_id: Optional[str] = Form(None),
    event_id: str = Form(...),
    db: Session = Depends(get_db),
    current_guest = Depends(get_current_guest)
):
    from ..main import Event, EventStatus, settings, SavedFace, SearchHistory, Image
    from ..services.face_engine import face_engine

    if selfie is None and saved_face_id is None:
        raise HTTPException(status_code=400, detail="Must provide either selfie image or saved_face_id")
    if selfie is not None and saved_face_id is not None:
        raise HTTPException(status_code=400, detail="Cannot provide both selfie image and saved_face_id")

    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.status != EventStatus.READY:
        raise HTTPException(status_code=409, detail="Event still processing")

    query_embedding = None

    if saved_face_id:
        # Resolve face embedding from SavedFace database record
        face = db.query(SavedFace).filter(
            SavedFace.id == saved_face_id,
            SavedFace.guest_user_id == current_guest.id
        ).first()
        if not face:
            raise HTTPException(status_code=404, detail="Saved face not found")
        
        query_embedding = np.array(face.face_embedding)
        # Update inactivity deletion timer (extend by 30 days)
        face.expires_at = datetime.utcnow() + timedelta(days=30)
        db.commit()
    else:
        if selfie.content_type not in ["image/jpeg", "image/png", "image/webp"]:
            raise HTTPException(status_code=415, detail="Invalid image type")

        selfie_bytes = await selfie.read()
        if len(selfie_bytes) > settings.max_selfie_bytes:
            raise HTTPException(status_code=413, detail="Selfie too large")

        query_embedding = face_engine.extract_single_embedding(selfie_bytes)
        del selfie_bytes

        if query_embedding is None:
            raise HTTPException(status_code=422, detail="No face detected in selfie")

        # Auto-save selfie to saved faces list
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        face = SavedFace(
            guest_user_id=current_guest.id,
            nickname=f"Search Selfie - {now_str}",
            face_embedding=query_embedding.tolist(),
            expires_at=datetime.utcnow() + timedelta(days=30)
        )
        db.add(face)
        db.commit()
        db.refresh(face)

    # Match vector search query using pgvector
    results = db.execute(
        text("""
            SELECT id AS photo_id, s3_url, thumbnail_url,
                   1 - (face_embedding <=> CAST(:qv AS vector)) AS similarity_score
            FROM images
            WHERE event_id = :event_id
              AND face_embedding IS NOT NULL
              AND (face_embedding <=> CAST(:qv AS vector)) < :threshold
            ORDER BY face_embedding <=> CAST(:qv AS vector) ASC
            LIMIT :max_results
        """),
        {"qv": str(query_embedding.tolist()), "event_id": event_id,
         "threshold": settings.similarity_threshold, "max_results": settings.max_match_results}
    ).fetchall()

    matches = []
    seen_urls = set()
    for row in results:
        if row.s3_url not in seen_urls:
            seen_urls.add(row.s3_url)
            matches.append(
                MatchResultOut(
                    photo_id=row.photo_id,
                    s3_url=row.s3_url,
                    thumbnail_url=row.thumbnail_url,
                    similarity_score=round(float(row.similarity_score), 4)
                )
            )

    # Log Search History record
    try:
        matched_photo_ids = [row.photo_id for row in results]
        matched_images = []
        if matched_photo_ids:
            matched_images = db.query(Image).filter(Image.id.in_(matched_photo_ids)).all()

        expires_at = datetime.utcnow() + timedelta(hours=24) if current_guest.is_anonymous else None
        
        history = SearchHistory(
            guest_user_id=current_guest.id,
            event_id=event_id,
            face_embedding=query_embedding.tolist() if hasattr(query_embedding, "tolist") else list(query_embedding),
            expires_at=expires_at
        )
        history.photos = matched_images
        db.add(history)
        db.commit()
    except Exception as e:
        db.rollback()
        # Log error but don't fail search results delivery
        print(f"Failed to log search history: {e}")

    return MatchResponse(matches=matches, total=len(matches))