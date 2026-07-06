from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import numpy as np
from ..utils.security import get_current_guest, get_guest_db, get_photo_db
from ..models.photographer_models import Event, EventStatus
from ..models.guest_models import SavedFace, SearchHistory
from ..config.settings import settings
from ..services.face_engine import face_engine

router = APIRouter(prefix="/match", tags=["Selfie Matching"])

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
    photo_db: Session = Depends(get_photo_db),
    guest_db: Session = Depends(get_guest_db),
    current_guest = Depends(get_current_guest)
):
    if selfie is None and saved_face_id is None:
        raise HTTPException(status_code=400, detail="Must provide either selfie image or saved_face_id")
    if selfie is not None and saved_face_id is not None:
        raise HTTPException(status_code=400, detail="Cannot provide both selfie image and saved_face_id")

    event = photo_db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.status != EventStatus.READY:
        raise HTTPException(status_code=409, detail="Event still processing")

    query_embedding = None

    if saved_face_id:
        face = guest_db.query(SavedFace).filter(
            SavedFace.id == saved_face_id,
            SavedFace.guest_user_id == current_guest.id
        ).first()
        if not face:
            raise HTTPException(status_code=404, detail="Saved face not found")

        query_embedding = np.array(face.face_embedding)
        face.expires_at = datetime.utcnow() + timedelta(days=30)
        guest_db.commit()
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

        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        face = SavedFace(
            guest_user_id=current_guest.id,
            nickname=f"Search Selfie - {now_str}",
            face_embedding=query_embedding.tolist(),
            expires_at=datetime.utcnow() + timedelta(days=30)
        )
        guest_db.add(face)
        guest_db.commit()
        guest_db.refresh(face)

    # pgvector similarity search — runs against photographer DB
    results = photo_db.execute(
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

    # Log search history — writes to guest DB, matched photos stored as JSON snapshot
    try:
        expires_at = datetime.utcnow() + timedelta(hours=24) if current_guest.is_anonymous else None

        history = SearchHistory(
            guest_user_id=current_guest.id,
            event_id=event_id,
            face_embedding=query_embedding.tolist() if hasattr(query_embedding, "tolist") else list(query_embedding),
            matched_photos=[
                {"id": row.photo_id, "s3_url": row.s3_url, "thumbnail_url": row.thumbnail_url}
                for row in results
            ],
            expires_at=expires_at
        )
        guest_db.add(history)
        guest_db.commit()
    except Exception as e:
        guest_db.rollback()
        print(f"Failed to log search history: {e}")

    return MatchResponse(matches=matches, total=len(matches))