import os
import shutil
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import OAuth2PasswordRequestForm
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from starlette import status

import crypto
import mailer
from auth import create_access_token, get_current_user
from config import (
    UPLOAD_DIR, MAX_FAILED_LOGIN, LOCKOUT_MINUTES,
    DORMANT_DAYS, ADMIN_USERNAME, ADMIN_PASSWORD, ADMIN_EMAIL, RECOVERY_KEY
)
from db import get_db
from models import Users, Files, AccountRequests
from schemas import (
    Token, UserResponse, UserUpdateName, UserUpdateEmail, UserUpdatePassword,
    UserDelete, UserVerifyPassword, AccountRequestCreate, PasswordResetConfirm,
)

passwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter(prefix="/api/user")


# ---- User database operations ---------------------------------------------

def get_user(db: Session, username: str):
    return db.query(Users).filter(Users.name == username).first()


def get_user_by_id(db: Session, user_id: int):
    return db.query(Users).filter(Users.id == user_id).first()


def get_user_by_email(db: Session, email: str):
    return db.query(Users).filter(Users.email == email).first()


def get_all_users(db: Session):
    return db.query(Users).all()


def create_user_record(db: Session, name: str, passwd_hash: str, email: str, is_admin: bool = False):
    """Create a user row plus its on-disk storage directory."""
    user = Users(name=name, passwd=passwd_hash, email=email, is_admin=is_admin)
    db.add(user)
    db.flush()

    date_str = datetime.now().strftime("%Y%m%d")
    dir_name = f"{user.id}_{user.name}_{date_str}"
    storage_path = os.path.join(UPLOAD_DIR, dir_name)
    os.makedirs(storage_path, exist_ok=True)
    user.storage_path = storage_path
    db.commit()
    return user


def create_admin_if_not_exists(db: Session):
    if not ADMIN_USERNAME or not ADMIN_PASSWORD:
        return
    if get_user(db, ADMIN_USERNAME):
        return
    create_user_record(
        db,
        ADMIN_USERNAME,
        passwd_context.hash(ADMIN_PASSWORD),
        ADMIN_EMAIL or f"{ADMIN_USERNAME}@localhost",
        is_admin=True,
    )


def verify_password(db: Session, user: Users, password: str):
    return passwd_context.verify(password, user.passwd)


def check_login(db: Session, username: str, password: str):
    user = get_user(db, username)
    if not user:
        return None, "User not found.", None
    if user.is_dormant:
        return None, "dormant", user
    if user.locked_until and datetime.now() < user.locked_until:
        remaining = int((user.locked_until - datetime.now()).total_seconds() / 60) + 1
        return None, f"Account locked. Try again in {remaining} minute(s).", None
    if not passwd_context.verify(password, user.passwd):
        user.failed_login = (user.failed_login or 0) + 1
        if user.failed_login >= MAX_FAILED_LOGIN:
            user.locked_until = datetime.now() + timedelta(minutes=LOCKOUT_MINUTES)
            user.failed_login = 0
            db.commit()
            return None, f"Too many failed attempts. Account locked for {LOCKOUT_MINUTES} minutes.", None
        db.commit()
        remaining_attempts = MAX_FAILED_LOGIN - user.failed_login
        return None, f"Incorrect password. {remaining_attempts} attempt(s) remaining.", None
    user.failed_login = 0
    user.locked_until = None
    user.last_login = datetime.now()
    db.commit()
    return user, None, None


def check_login_by_email(db: Session, email: str, password: str):
    user = get_user_by_email(db, email)
    if not user:
        return None, "No account found with this email.", None
    return check_login(db, user.name, password)


def check_dormant_accounts(db: Session):
    threshold = datetime.now() - timedelta(days=DORMANT_DAYS)
    users = db.query(Users).filter(
        Users.is_admin == False,
        Users.is_dormant == False,
        Users.last_login != None,
        Users.last_login < threshold
    ).all()
    for user in users:
        user.is_dormant = True
    db.commit()


def update_name(db: Session, user: Users, new_name: str):
    user.name = new_name
    db.commit()


def update_email(db: Session, user: Users, new_email: str):
    user.email = new_email
    db.commit()


def delete_user(db: Session, user: Users):
    if user.storage_path and os.path.exists(user.storage_path):
        shutil.rmtree(user.storage_path)
    db.delete(user)
    db.commit()


def unlock_user(db: Session, user: Users):
    user.failed_login = 0
    user.locked_until = None
    db.commit()


def lock_user(db: Session, user: Users):
    user.locked_until = datetime.now() + timedelta(days=36500)
    db.commit()


def activate_dormant(db: Session, user: Users):
    user.is_dormant = False
    user.last_login = datetime.now()
    db.commit()


def get_storage_used(db: Session, user_id: int):
    files = db.query(Files).filter(
        Files.file_owner == user_id,
        Files.is_deleted == False,
        Files.is_folder == False
    ).all()
    return sum(f.file_size or 0 for f in files)


def set_storage_limit(db: Session, user: Users, limit_bytes):
    user.storage_limit = limit_bytes
    db.commit()


def clean_old_trash(db: Session):
    threshold = datetime.now() - timedelta(days=30)
    old = db.query(Files).filter(
        Files.is_deleted == True,
        Files.deleted_at != None,
        Files.deleted_at < threshold,
        Files.is_folder == False
    ).all()
    for f in old:
        if f.file_path and os.path.exists(f.file_path):
            os.remove(f.file_path)
        db.delete(f)
    db.commit()


# ---- Encryption key management --------------------------------------------

# The admin recovery key is derived from the RECOVERY_KEY server secret. It is
# used only to recover a user's DEK during a forgot-password reset.
RECOVERY_KEY_BYTES = crypto.recovery_key_from_secret(RECOVERY_KEY)


def _store_password_dek(user: Users, dek: bytes, password: str):
    material = crypto.wrap_dek(dek, password)
    user.dek_wrapped = material["dek_wrapped"]
    user.dek_nonce = material["dek_nonce"]
    user.dek_tag = material["dek_tag"]
    user.kek_salt = material["kek_salt"]


def _store_recovery_dek(user: Users, dek: bytes):
    material = crypto.wrap_with_key(dek, RECOVERY_KEY_BYTES)
    user.dek_wrapped_recovery = material["dek_wrapped"]
    user.dek_nonce_recovery = material["dek_nonce"]
    user.dek_tag_recovery = material["dek_tag"]


def _store_dek_keys(user: Users, dek: bytes, password: str):
    _store_password_dek(user, dek, password)
    _store_recovery_dek(user, dek)


def ensure_user_dek(db: Session, user: Users, password: str):
    """Create and wrap a DEK on first login if the user has none yet."""
    if user.dek_wrapped:
        if not user.dek_wrapped_recovery:
            # Backfill the recovery copy for users created before it existed.
            _store_recovery_dek(user, crypto.unwrap_dek(user, password))
            db.commit()
        return
    _store_dek_keys(user, crypto.generate_dek(), password)
    db.commit()


def rewrap_user_dek(db: Session, user: Users, old_password: str, new_password: str):
    """Re-wrap the existing DEK under a new password."""
    if user.dek_wrapped:
        dek = crypto.unwrap_dek(user, old_password)
    else:
        dek = crypto.generate_dek()
    _store_dek_keys(user, dek, new_password)
    user.passwd = passwd_context.hash(new_password)
    db.commit()


def reset_user_dek_for_password(db: Session, user: Users, new_password: str):
    """Recover the DEK via the admin recovery key and re-wrap it under a new
    password, so a forgot-password reset does not lose the user's files."""
    if user.dek_wrapped_recovery:
        dek = crypto.unwrap_with_key(
            user.dek_wrapped_recovery,
            user.dek_nonce_recovery,
            user.dek_tag_recovery,
            RECOVERY_KEY_BYTES,
        )
    else:
        dek = crypto.generate_dek()
    _store_dek_keys(user, dek, new_password)
    user.passwd = passwd_context.hash(new_password)
    db.commit()


def build_token(user: Users, password: str):
    dek = crypto.unwrap_dek(user, password)
    return create_access_token(
        data={"sub": user.name},
        extra={"dek": crypto.b64e(dek)},
    )


# ---- Routes ----------------------------------------------------------------

@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user, error, dormant_user = check_login_by_email(db, form_data.username, form_data.password)
    if dormant_user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="dormant")
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error)

    ensure_user_dek(db, user, form_data.password)
    access_token = build_token(user, form_data.password)
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
def get_me(current_user: Users = Depends(get_current_user)):
    return current_user


@router.post("/request", status_code=status.HTTP_204_NO_CONTENT)
def submit_account_request(body: AccountRequestCreate, db: Session = Depends(get_db)):
    if get_user(db, body.name):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken.")
    if get_user_by_email(db, body.email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use.")
    existing = db.query(AccountRequests).filter(
        AccountRequests.name == body.name,
        AccountRequests.status == "pending"
    ).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A request with this username is already pending.")
    req = AccountRequests(
        name=body.name,
        email=body.email,
        passwd=passwd_context.hash(body.passwd1),
        message=body.message,
        status="pending"
    )
    db.add(req)
    db.commit()


@router.post("/settings/verify")
def verify_password_for_settings(
    body: UserVerifyPassword,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not verify_password(db, current_user, body.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password.")
    return {"message": "Password verified."}


@router.patch("/settings/name")
def change_name(
    body: UserUpdateName,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not verify_password(db, current_user, body.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password.")
    if get_user(db, body.new_name):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken.")
    update_name(db, current_user, body.new_name)
    dek = crypto.unwrap_dek(current_user, body.password)
    new_token = create_access_token(data={"sub": body.new_name}, extra={"dek": crypto.b64e(dek)})
    return {"message": "Username updated.", "access_token": new_token}


@router.patch("/settings/email")
def change_email(
    body: UserUpdateEmail,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not verify_password(db, current_user, body.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password.")
    if get_user_by_email(db, body.new_email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use.")
    update_email(db, current_user, body.new_email)
    return {"message": "Email updated."}


@router.patch("/settings/password")
def change_password(
    body: UserUpdatePassword,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not verify_password(db, current_user, body.current_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect.")
    rewrap_user_dek(db, current_user, body.current_password, body.new_password)
    return {"message": "Password updated."}


@router.delete("/settings/delete", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    body: UserDelete,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin account cannot be deleted this way.")
    if not verify_password(db, current_user, body.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password.")
    delete_user(db, current_user)


@router.post("/password/reset-request")
def password_reset_request(email: str = Query(...), db: Session = Depends(get_db)):
    user = get_user_by_email(db, email)
    if user:
        mailer.send_reset_code(email)
    return {"message": "If the email exists, a verification code has been sent."}


@router.post("/password/reset")
def password_reset(body: PasswordResetConfirm, db: Session = Depends(get_db)):
    if not mailer.verify_code(body.email, body.code, "reset"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired code.")
    user = get_user_by_email(db, body.email)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    reset_user_dek_for_password(db, user, body.new_password)
    return {"message": "Password reset. Files uploaded with your old password are no longer readable."}

