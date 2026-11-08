from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from starlette import status

from auth import require_admin
from config import MAX_ACCOUNT
from db import get_db
from models import Users, AccountRequests
from schemas import UserResponse, AccountRequestResponse
from users import (
    get_user_by_id, get_all_users, create_user_record, delete_user,
    lock_user, unlock_user, activate_dormant, set_storage_limit,
)

router = APIRouter(prefix="/api/admin")


@router.get("/users", response_model=list[UserResponse])
def admin_get_users(
    db: Session = Depends(get_db),
    current_user: Users = Depends(require_admin)
):
    return get_all_users(db)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: Users = Depends(require_admin)
):
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete admin account.")
    delete_user(db, user)


@router.patch("/users/{user_id}/lock", status_code=status.HTTP_204_NO_CONTENT)
def admin_lock_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: Users = Depends(require_admin)
):
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot lock admin account.")
    lock_user(db, user)


@router.patch("/users/{user_id}/unlock", status_code=status.HTTP_204_NO_CONTENT)
def admin_unlock_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: Users = Depends(require_admin)
):
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    unlock_user(db, user)


@router.patch("/users/{user_id}/dormant-unlock", status_code=status.HTTP_204_NO_CONTENT)
def admin_dormant_unlock(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: Users = Depends(require_admin)
):
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    activate_dormant(db, user)


@router.patch("/users/{user_id}/storage-limit")
def admin_set_storage_limit(
    user_id: int,
    limit_gb: float = None,
    db: Session = Depends(get_db),
    current_user: Users = Depends(require_admin)
):
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    limit_bytes = int(limit_gb * 1073741824) if limit_gb is not None else None
    set_storage_limit(db, user, limit_bytes)
    return {"message": "Storage limit updated."}


@router.get("/config")
def get_config(current_user: Users = Depends(require_admin)):
    return {"max_account": MAX_ACCOUNT}


@router.get("/requests", response_model=list[AccountRequestResponse])
def admin_get_requests(
    db: Session = Depends(get_db),
    current_user: Users = Depends(require_admin)
):
    return db.query(AccountRequests).filter(
        AccountRequests.status == "pending"
    ).order_by(AccountRequests.created_at.desc()).all()


@router.post("/requests/{req_id}/approve", status_code=status.HTTP_204_NO_CONTENT)
def admin_approve_request(
    req_id: int,
    db: Session = Depends(get_db),
    current_user: Users = Depends(require_admin)
):
    req = db.query(AccountRequests).filter(AccountRequests.id == req_id).first()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found.")

    if db.query(Users).filter(Users.name == req.name).first():
        req.status = "rejected"
        db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken. Request rejected.")
    if db.query(Users).filter(Users.email == req.email).first():
        req.status = "rejected"
        db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use. Request rejected.")

    user_count = db.query(Users).filter(Users.is_admin == False).count()
    if user_count >= MAX_ACCOUNT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Max account limit ({MAX_ACCOUNT}) reached.")

    create_user_record(db, req.name, req.passwd, req.email, is_admin=False)
    db.delete(req)
    db.commit()


@router.delete("/requests/{req_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
def admin_reject_request(
    req_id: int,
    db: Session = Depends(get_db),
    current_user: Users = Depends(require_admin)
):
    req = db.query(AccountRequests).filter(AccountRequests.id == req_id).first()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found.")
    db.delete(req)
    db.commit()
