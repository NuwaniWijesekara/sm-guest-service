from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
from ..utils.security import CurrentUser, get_guest_db, get_current_user
from ..models.guest_models import SavedFace

# Saved faces are only created by selfie searches now (see api/match.py) and
# surface in the UI through search history. The standalone upload endpoint
# (POST /guest/saved-faces) was removed: it indexed faces into a separate
# "saved-faces" Rekognition collection that event searches can never reach.
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
    current_user: CurrentUser = Depends(get_current_user),
):
    faces = db.query(SavedFace).filter(SavedFace.user_id == current_user.id).order_by(SavedFace.created_at.desc()).all()
    return faces

@router.patch("/{face_id}", response_model=SavedFaceOut)
def update_saved_face(
    face_id: str,
    data: SavedFaceUpdate,
    db: Session = Depends(get_guest_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    face = db.query(SavedFace).filter(
        SavedFace.id == face_id,
        SavedFace.user_id == current_user.id
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
    current_user: CurrentUser = Depends(get_current_user),
):
    face = db.query(SavedFace).filter(
        SavedFace.id == face_id,
        SavedFace.user_id == current_user.id
    ).first()
    if not face:
        raise HTTPException(status_code=404, detail="Saved face not found")

    db.delete(face)
    db.commit()
    return
