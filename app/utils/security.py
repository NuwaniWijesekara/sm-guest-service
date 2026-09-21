from dataclasses import dataclass
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from ..config.settings import settings

oauth2_scheme = HTTPBearer()

@dataclass
class CurrentUser:
    """The caller identified by a unified-auth JWT (issued by
    sm-photographer-service). No local DB lookup — the same trust model the
    issuing service itself uses for its own `get_current_user`."""
    id: str
    email: str
    name: str
    is_anonymous: bool

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

    return CurrentUser(
        id=user_id,
        email=payload.get("email", ""),
        name=payload.get("name", ""),
        is_anonymous=bool(payload.get("is_anonymous", False)),
    )