from dataclasses import dataclass
from typing import Optional
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from ..config.settings import settings

oauth2_scheme = HTTPBearer()
optional_oauth2_scheme = HTTPBearer(auto_error=False)

@dataclass
class CurrentUser:
    """The caller identified by a unified-auth JWT (issued by
    sm-photographer-service). No local DB lookup — the same trust model the
    issuing service itself uses for its own `get_current_user`."""
    id: str
    email: str
    name: str
    # True only for Google sign-ins — see create_access_token in
    # sm-photographer-service. Required for invite-only galleries.
    email_verified: bool = False

def get_guest_db():
    from ..main import GuestSessionLocal
    db = GuestSessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_photo_db():
    from ..main import PhotographerSessionLocal
    db = PhotographerSessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
) -> CurrentUser:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Anonymous sessions were removed; a still-unexpired token from the old
    # POST /auth/anonymous must not keep granting access.
    if payload.get("is_anonymous"):
        raise HTTPException(status_code=401, detail={
            "code": "login_required",
            "message": "Please sign in to continue.",
        })

    return CurrentUser(
        id=user_id,
        email=payload.get("email", ""),
        name=payload.get("name", ""),
        email_verified=payload.get("email_verified") is True,
    )

def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_oauth2_scheme),
) -> Optional[CurrentUser]:
    """The caller if they sent a valid account token, else None — for
    endpoints that public events serve without login. A missing, expired,
    invalid or anonymous token is treated as "not signed in" rather than a
    401, so a stale token in the browser never blocks a public gallery."""
    if credentials is None:
        return None
    try:
        return get_current_user(credentials)
    except HTTPException:
        return None