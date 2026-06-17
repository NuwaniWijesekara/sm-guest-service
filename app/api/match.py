from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional

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
    selfie: UploadFile = File(...),
    event_id: str = Form(...),
    db: Session = Depends(get_db)
):
    from ..main import Event, EventStatus, settings
    from ..services.face_engine import face_engine

    if selfie.size and selfie.size > settings.max_selfie_bytes:
        raise HTTPException(status_code=413, detail="Selfie too large")
    if selfie.content_type not in ["image/jpeg", "image/png", "image/webp"]:
        raise HTTPException(status_code=415, detail="Invalid image type")

    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.status != EventStatus.READY:
        raise HTTPException(status_code=409, detail="Event still processing")

    selfie_bytes = await selfie.read()
    query_embedding = face_engine.extract_single_embedding(selfie_bytes)
    del selfie_bytes

    if query_embedding is None:
        raise HTTPException(status_code=422, detail="No face detected in selfie")

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

    matches = [
        MatchResultOut(
            photo_id=row.photo_id, s3_url=row.s3_url,
            thumbnail_url=row.thumbnail_url,
            similarity_score=round(float(row.similarity_score), 4)
        ) for row in results
    ]
    return MatchResponse(matches=matches, total=len(matches))