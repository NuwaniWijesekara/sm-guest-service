from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from ..utils.security import verify_password, get_password_hash, create_access_token, get_db
from ..main import GuestUser

router = APIRouter(prefix="/guest/auth", tags=["Guest Authentication"])

class GuestRegister(BaseModel):
    name: str
    email: str
    password: str

class GuestLogin(BaseModel):
    email: str
    password: str

class GoogleLoginRequest(BaseModel):
    id_token: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    is_anonymous: bool

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(data: GuestRegister, db: Session = Depends(get_db)):
    if not data.name or not data.email or not data.password:
        raise HTTPException(status_code=400, detail="Name, email, and password are required")
    
    existing = db.query(GuestUser).filter(GuestUser.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_pwd = get_password_hash(data.password)
    user = GuestUser(name=data.name, email=data.email, hashed_password=hashed_pwd, is_anonymous=False)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": "Guest account created successfully", "user_id": user.id}

@router.post("/login", response_model=TokenResponse)
def login(data: GuestLogin, db: Session = Depends(get_db)):
    if not data.email or not data.password:
        raise HTTPException(status_code=400, detail="Email and password are required")
        
    user = db.query(GuestUser).filter(GuestUser.email == data.email).first()
    if not user or user.is_anonymous or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({
        "sub": user.id,
        "email": user.email or "",
        "name": user.name or "",
        "is_anonymous": False
    })
    return {"access_token": token, "token_type": "bearer", "is_anonymous": False}

@router.post("/anonymous", response_model=TokenResponse)
def login_anonymous(db: Session = Depends(get_db)):
    user = GuestUser(is_anonymous=True)
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({
        "sub": user.id,
        "email": "Anonymous Guest",
        "name": "Guest",
        "is_anonymous": True
    })
    return {"access_token": token, "token_type": "bearer", "is_anonymous": True}

@router.post("/google", response_model=TokenResponse)
def login_google(data: GoogleLoginRequest, db: Session = Depends(get_db)):
    from google.oauth2 import id_token
    from google.auth.transport import requests
    from ..config.settings import settings

    if not data.id_token:
        raise HTTPException(status_code=400, detail="Google id_token is required")

    try:
        # Verify token using google-auth library
        idinfo = id_token.verify_oauth2_token(
            data.id_token,
            requests.Request(),
            settings.google_client_id
        )
        print(f"Google Token verified successfully for Client ID: {settings.google_client_id}")

        email = idinfo.get("email")
        name = idinfo.get("name")
        if not email:
            raise HTTPException(status_code=400, detail="Google token does not contain email")
    except ValueError as e:
        error_msg = f"Google token verification failed: {str(e)} (Audience/Client ID configured: '{settings.google_client_id}')"
        print(error_msg)
        raise HTTPException(status_code=400, detail=error_msg)

    user = db.query(GuestUser).filter(GuestUser.email == email).first()
    if not user:
        # Auto-register google user
        user = GuestUser(email=email, name=name, is_anonymous=False)
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # Sync name if missing
        if not user.name and name:
            user.name = name
            db.commit()

    token = create_access_token({
        "sub": user.id,
        "email": user.email or "",
        "name": user.name or "",
        "is_anonymous": False
    })
    return {"access_token": token, "token_type": "bearer", "is_anonymous": False}
