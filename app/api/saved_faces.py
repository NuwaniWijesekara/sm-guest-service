from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
from ..utils.security import get_guest_db, get_current_guest
from ..models.guest_models import SavedFace
from ..services.face_engine import face_engine
from ..config.settings import settings

router = APIRouter(prefix="/guest/saved-faces", tags=["Saved Faces"])

class SavedFaceOut(BaseModel):
    id: str
    nickname: str
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True

class SavedFaceUpdate(BaseModel):
    nickname: str

@router.get("", response_model=list[SavedFaceOut])
def list_saved_faces(
    db: Session = Depends(get_guest_db),
    current_guest = Depends(get_current_guest)
):
    faces = db.query(SavedFace).filter(SavedFace.guest_user_id == current_guest.id).order_by(SavedFace.created_at.desc()).all()
    return faces

@router.post("", response_model=SavedFaceOut, status_code=status.HTTP_201_CREATED)
async def create_saved_face(
    nickname: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_guest_db),
    current_guest = Depends(get_current_guest)
):
    if file.content_type not in ["image/jpeg", "image/png", "image/webp"]:
        raise HTTPException(status_code=415, detail="Invalid image type")

    file_bytes = await file.read()
    if len(file_bytes) > settings.max_selfie_bytes:
        raise HTTPException(status_code=413, detail="Selfie too large")

    query_embedding = face_engine.extract_single_embedding(file_bytes)
    del file_bytes

    if query_embedding is None:
        raise HTTPException(status_code=422, detail="No face detected in selfie")

    expires_at = datetime.utcnow() + timedelta(days=30)
    face = SavedFace(
        guest_user_id=current_guest.id,
        nickname=nickname,
        face_embedding=query_embedding.tolist(),
        expires_at=expires_at
    )
    db.add(face)
    db.commit()
    db.refresh(face)
    return face

@router.patch("/{face_id}", response_model=SavedFaceOut)
def update_saved_face(
    face_id: str,
    data: SavedFaceUpdate,
    db: Session = Depends(get_guest_db),
    current_guest = Depends(get_current_guest)
):
    face = db.query(SavedFace).filter(
        SavedFace.id == face_id,
        SavedFace.guest_user_id == current_guest.id
    ).first()
    if not face:
        raise HTTPException(status_code=404, detail="Saved face not found")

    face.nickname = data.nickname
    db.commit()
    db.refresh(face)
    return face

@router.delete("/{face_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_face(
    face_id: str,
    db: Session = Depends(get_guest_db),
    current_guest = Depends(get_current_guest)
):
    face = db.query(SavedFace).filter(
        SavedFace.id == face_id,
        SavedFace.guest_user_id == current_guest.id
    ).first()
    if not face:
        raise HTTPException(status_code=404, detail="Saved face not found")

    db.delete(face)
    db.commit()
    return