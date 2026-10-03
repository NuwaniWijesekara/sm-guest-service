"""Per-event guest gallery access control.

An event's `access_mode` (set by its owner in sm-photographer-service) is
either "public" — anyone holding the link/QR/username — or "invite_only":
only the owner, or a collaborator signed in with a verified email. Only a
Google sign-in currently yields `email_verified` (password signup never
proves email ownership), so invite-only guests must use Google.

Every endpoint that exposes an event's photos (gallery, selfie match,
search history) goes through this module, so the rule lives in one place.
"""
from typing import Optional
from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session
from ..models.photographer_models import Event, EventCollaborator
from .security import CurrentUser

PUBLIC = "public"


def find_event(db: Session, key: str) -> Optional[Event]:
    """Resolve whatever a guest has — event id, QR token or collection
    username (with or without a leading @, any case) — to the event."""
    clean = key.strip().lower().lstrip("@")
    return db.query(Event).filter(
        or_(Event.id == key, Event.qr_token == clean, Event.username == clean)
    ).first()


def _denial(event, user: Optional[CurrentUser], db: Session) -> Optional[HTTPException]:
    """None if `user` may see `event`'s photos, else the error to raise."""
    if (event.access_mode or PUBLIC) == PUBLIC:
        return None
    if user is None or user.is_anonymous:
        return HTTPException(status_code=401, detail={
            "code": "login_required",
            "message": "This gallery is invite-only. Sign in with Google to continue.",
        })
    if user.id == event.owner_id:
        return None
    if not user.email_verified:
        return HTTPException(status_code=403, detail={
            "code": "verification_required",
            "message": "Sign in with Google using the email address you were invited with.",
        })
    invited = (
        db.query(EventCollaborator.id)
        .filter(EventCollaborator.event_id == event.id, EventCollaborator.user_id == user.id)
        .first()
    )
    if not invited:
        return HTTPException(status_code=403, detail={
            "code": "not_invited",
            "message": "Your account isn't on the guest list for this event.",
        })
    return None


def require_gallery_access(db: Session, event, user: Optional[CurrentUser]) -> None:
    denial = _denial(event, user, db)
    if denial:
        raise denial


def has_gallery_access(db: Session, event, user: Optional[CurrentUser]) -> bool:
    return _denial(event, user, db) is None
