from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import bcrypt
from ..config.settings import settings

oauth2_scheme = HTTPBearer()

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.jwt_expire_minutes))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)

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

def get_current_guest(
    credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
    db: Session = Depends(get_guest_db)
):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        guest_id = payload.get("sub")
        if not guest_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    from ..models.guest_models import GuestUser
    guest = db.query(GuestUser).filter(GuestUser.id == guest_id).first()
    if not guest:
        raise HTTPException(status_code=401, detail="Guest user not found")
    return guest

def get_logged_in_guest(guest = Depends(get_current_guest)):
    if guest.is_anonymous:
        raise HTTPException(status_code=403, detail="Saved faces are only available to logged-in guests")
    return guest