import base64
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from starlette import status
from db import get_db
from dotenv import load_dotenv
from models import Users

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/user/login")


def _credentials_exception():
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Your credentials are invalid.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def create_access_token(data: dict, extra: dict = None):
    to_encode = data.copy()
    if extra:
        to_encode.update(extra)
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise _credentials_exception()


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    payload = _decode_token(token)
    username: str = payload.get("sub")
    if username is None:
        raise _credentials_exception()

    user = db.query(Users).filter(Users.name == username).first()
    if user is None:
        raise _credentials_exception()
    return user


def get_current_dek(token: str = Depends(oauth2_scheme)) -> bytes:
    """Return the caller's data encryption key embedded in the JWT.

    The DEK is only ever available to the logged-in user's own session; an
    admin (or anyone reading the DB) never receives another user's DEK.
    """
    payload = _decode_token(token)
    dek_b64 = payload.get("dek")
    if not dek_b64:
        raise _credentials_exception()
    return base64.b64decode(dek_b64)


def require_admin(current_user: Users = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    return current_user
