from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
from ..utils.security import get_current_guest, get_guest_db, get_photo_db
from ..models.photographer_models import Event, EventStatus, Image, Face
from ..models.guest_models import SavedFace, SearchHistory
from ..config.settings import settings
from ..services.face_engine import face_engine
from ..services.s3 import s3_service

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

    clean_event_id = event_id.strip().lower().lstrip('@')
    event = photo_db.query(Event).filter(
        or_(Event.id == event_id, Event.qr_token == clean_event_id, Event.username == clean_event_id)
    ).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.status != EventStatus.READY:
        raise HTTPException(status_code=409, detail="Event still processing")
    event_id = event.id

    raw_matches = []
    primary_face_id = None

    if saved_face_id:
        face = guest_db.query(SavedFace).filter(
            SavedFace.id == saved_face_id,
            SavedFace.guest_user_id == current_guest.id
        ).first()
        if not face:
            raise HTTPException(status_code=404, detail="Saved face not found")

        primary_face_id = face.rekognition_face_id
        if primary_face_id:
            raw_matches = face_engine.search_faces(
                face_id=primary_face_id,
                collection_id=event_id,
                threshold=80.0
            )

        face.expires_at = datetime.utcnow() + timedelta(days=30)
        guest_db.commit()
    else:
        if selfie.content_type not in ["image/jpeg", "image/png", "image/webp"]:
            raise HTTPException(status_code=415, detail="Invalid image type")

        selfie_bytes = await selfie.read()
        if len(selfie_bytes) > settings.max_selfie_bytes:
            raise HTTPException(status_code=413, detail="Selfie too large")

        # Pass guest's selfie bytes to AWS Rekognition search_faces_by_image
        raw_matches = face_engine.search_faces_by_image(
            selfie_bytes=selfie_bytes,
            collection_id=event_id,
            threshold=80.0
        )

        if raw_matches:
            primary_face_id = raw_matches[0]['face_id']
        else:
            primary_face_id = face_engine.index_selfie(selfie_bytes, collection_id=event_id)

        del selfie_bytes

        if not raw_matches and not primary_face_id:
            raise HTTPException(status_code=422, detail="No face detected in selfie")

        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        face = SavedFace(
            guest_user_id=current_guest.id,
            nickname=f"Search Selfie - {now_str}",
            rekognition_face_id=primary_face_id,
            expires_at=datetime.utcnow() + timedelta(days=30)
        )
        guest_db.add(face)
        guest_db.commit()
        guest_db.refresh(face)

    # Extract matched FaceIds from Rekognition response and query DB for matching image URLs
    matched_face_ids = [m['face_id'] for m in raw_matches]
    similarity_map = {m['face_id']: m['similarity'] for m in raw_matches}

    matches = []
    if matched_face_ids:
        rows = photo_db.query(
            Image.id.label("photo_id"),
            Image.s3_url,
            Image.thumbnail_url,
            Face.rekognition_face_id
        ).join(Face, Face.image_id == Image.id)\
         .filter(Image.event_id == event_id, Face.rekognition_face_id.in_(matched_face_ids))\
         .all()

        photo_dict = {}
        for row in rows:
            score = similarity_map.get(row.rekognition_face_id, 80.0)
            if row.photo_id not in photo_dict or score > photo_dict[row.photo_id]["similarity_score"]:
                photo_dict[row.photo_id] = {
                    "photo_id": row.photo_id,
                    "s3_url": s3_service.generate_presigned_url(row.s3_url, expiration=3600),
                    "thumbnail_url": s3_service.generate_presigned_url(row.thumbnail_url, expiration=3600) if row.thumbnail_url else None,
                    "similarity_score": round(float(score), 4)
                }

        matches = [MatchResultOut(**item) for item in photo_dict.values()]
        matches.sort(key=lambda x: x.similarity_score, reverse=True)
        if settings.max_match_results:
            matches = matches[:settings.max_match_results]

    # Log search history — writes to guest DB
    try:
        expires_at = datetime.utcnow() + timedelta(hours=24) if current_guest.is_anonymous else None

        history = SearchHistory(
            guest_user_id=current_guest.id,
            event_id=event_id,
            rekognition_face_id=primary_face_id,
            matched_photos=[
                {"id": m.photo_id, "s3_url": m.s3_url, "thumbnail_url": m.thumbnail_url}
                for m in matches
            ],
            expires_at=expires_at
        )
        guest_db.add(history)
        guest_db.commit()
    except Exception as e:
        guest_db.rollback()
        print(f"Failed to log search history: {e}")

    return MatchResponse(matches=matches, total=len(matches))