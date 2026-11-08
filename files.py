import io
import os
import re
import shutil
import uuid
import zipfile
import mimetypes
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Request
from fastapi.responses import StreamingResponse
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from starlette import status

import crypto
from auth import get_current_user, get_current_dek, SECRET_KEY, ALGORITHM
from config import UPLOAD_DIR
from db import get_db
from models import Users, Files, SharedLinks
from schemas import (
    FolderCreate, FileRename, FileMoveBody, FileCopyBody, ShareCreate,
    BatchDeleteBody, FileOut, SharedLinkOut,
)

os.makedirs(UPLOAD_DIR, exist_ok=True)

TRASH_DIR = os.path.join(UPLOAD_DIR, "_trash")
os.makedirs(TRASH_DIR, exist_ok=True)

PREVIEWABLE = {
    "image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml",
    "application/pdf", "text/plain",
    "video/mp4", "video/webm", "video/ogg", "video/quicktime"
}

router = APIRouter(prefix="/api/file")


# ---- Helpers ---------------------------------------------------------------

def _get_owned_file(db: Session, file_id: int, user: Users, include_deleted: bool = False):
    query = db.query(Files).filter(
        Files.id == file_id,
        Files.file_owner == user.id,
    )
    if not include_deleted:
        query = query.filter(Files.is_deleted == False)
    f = query.first()
    if not f:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")
    return f


def _get_owned_folder(db: Session, folder_id: int, user: Users):
    folder = db.query(Files).filter(
        Files.id == folder_id,
        Files.file_owner == user.id,
        Files.is_folder == True,
        Files.is_deleted == False
    ).first()
    if not folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found.")
    return folder


def _unique_path(path: str) -> str:
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 1
    while True:
        candidate = f"{base} ({i}){ext}"
        if not os.path.exists(candidate):
            return candidate
        i += 1


def _content_disposition(filename: str, attachment: bool = False) -> str:
    disposition = "attachment" if attachment else "inline"
    return f"{disposition}; filename*=UTF-8''{quote(filename)}"


def _token_payload(request: Request, token_query: str) -> dict:
    token = token_query
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")


def _resolve_user(request: Request, token_query: str, db: Session):
    payload = _token_payload(request, token_query)
    username = payload.get("sub")
    dek_b64 = payload.get("dek")
    if not username or not dek_b64:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")
    user = db.query(Users).filter(Users.name == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    return user, crypto.b64d(dek_b64)


def _iter_range(file_path: str, dek: bytes, iv_b64: str, start: int, length: int):
    produced = 0
    for chunk in crypto.iter_decrypted(file_path, dek, iv_b64, offset=start):
        if produced >= length:
            break
        take = min(len(chunk), length - produced)
        if take:
            yield chunk[:take]
            produced += take


def _serve_file(file, dek: bytes, media_type: str, filename=None, as_attachment=False, range_header=None):
    total = file.file_size or 0
    start, end = 0, max(total - 1, 0)
    code = 200
    headers = {"Accept-Ranges": "bytes"}

    if range_header:
        m = re.match(r"bytes=(\d*)-(\d*)", range_header)
        if m and (m.group(1) or m.group(2)):
            s = int(m.group(1)) if m.group(1) else 0
            e = int(m.group(2)) if m.group(2) else total - 1
            if total > 0 and s >= total:
                raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, detail="Range not satisfiable.")
            start = s
            end = min(e, total - 1)
            code = 206
            headers["Content-Range"] = f"bytes {start}-{end}/{total}"

    length = (end - start + 1) if total > 0 else 0
    headers["Content-Length"] = str(length)
    if filename:
        headers["Content-Disposition"] = _content_disposition(filename, as_attachment)

    gen = _iter_range(file.file_path, dek, file.enc_iv, start, length)
    return StreamingResponse(gen, status_code=code, media_type=media_type, headers=headers)


# ---- Routes ----------------------------------------------------------------

@router.get("/stats")
def get_stats(db: Session = Depends(get_db), current_user: Users = Depends(get_current_user)):
    files = db.query(Files).filter(
        Files.file_owner == current_user.id,
        Files.is_deleted == False,
        Files.is_folder == False
    ).all()
    total_size = sum(f.file_size or 0 for f in files)
    trash_count = db.query(Files).filter(
        Files.file_owner == current_user.id,
        Files.is_deleted == True
    ).count()
    return {
        "total_files": len(files),
        "total_size": total_size,
        "storage_limit": current_user.storage_limit,
        "trash_count": trash_count
    }


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    parent_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    dek: bytes = Depends(get_current_dek)
):
    if parent_id:
        save_dir = _get_owned_folder(db, parent_id, current_user).file_path
    else:
        save_dir = current_user.storage_path

    original_name = file.filename or "untitled"
    file_path = _unique_path(os.path.join(save_dir, original_name))
    iv = crypto.new_file_iv()

    with open(file_path, "wb") as out:
        size = crypto.encrypt_stream(file.file, out, dek, iv)

    file_type = file.content_type or mimetypes.guess_type(original_name)[0] or "application/octet-stream"

    db_file = Files(
        file_name=original_name,
        file_path=file_path,
        file_size=size,
        file_owner=current_user.id,
        file_type=file_type,
        is_folder=False,
        parent_id=parent_id,
        create_date=datetime.now(),
        enc_iv=crypto.b64e(iv)
    )
    db.add(db_file)
    db.commit()
    return {"id": db_file.id, "filename": original_name, "size": size}


@router.patch("/rename/{file_id}")
def rename_file(
    file_id: int,
    body: FileRename,
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    file = _get_owned_file(db, file_id, current_user)
    parent_dir = os.path.dirname(file.file_path)
    new_path = _unique_path(os.path.join(parent_dir, body.new_name.strip()))
    os.rename(file.file_path, new_path)
    file.file_name = body.new_name.strip()
    file.file_path = new_path
    db.commit()
    return {"message": "Renamed successfully."}


@router.post("/folder", status_code=status.HTTP_201_CREATED)
def create_folder(
    body: FolderCreate,
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    name = body.folder_name.strip()
    if body.parent_id:
        parent = _get_owned_folder(db, body.parent_id, current_user)
        folder_path = _unique_path(os.path.join(parent.file_path, name))
    else:
        folder_path = _unique_path(os.path.join(current_user.storage_path, name))

    os.makedirs(folder_path, exist_ok=True)

    db_folder = Files(
        file_name=name,
        file_path=folder_path,
        file_size=0,
        file_owner=current_user.id,
        file_type="folder",
        is_folder=True,
        parent_id=body.parent_id,
        create_date=datetime.now()
    )
    db.add(db_folder)
    db.commit()
    return {"folder_id": db_folder.id, "folder_name": name}


@router.get("/list", response_model=list[FileOut])
def get_file_list(
    parent_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    return db.query(Files).filter(
        Files.file_owner == current_user.id,
        Files.parent_id == parent_id,
        Files.is_deleted == False
    ).all()


@router.get("/search", response_model=list[FileOut])
def search_files(
    q: str,
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    return db.query(Files).filter(
        Files.file_owner == current_user.id,
        Files.is_deleted == False,
        Files.file_name.ilike(f"%{q}%")
    ).all()


@router.get("/folders", response_model=list[FileOut])
def list_folders(db: Session = Depends(get_db), current_user: Users = Depends(get_current_user)):
    """All folders owned by the user, used to build move/copy target pickers."""
    return db.query(Files).filter(
        Files.file_owner == current_user.id,
        Files.is_folder == True,
        Files.is_deleted == False
    ).all()


@router.get("/download/{file_id}")
def download_file(
    file_id: int,
    request: Request,
    token: str = Query(None),
    db: Session = Depends(get_db)
):
    user, dek = _resolve_user(request, token, db)
    file = _get_owned_file(db, file_id, user)
    if file.is_folder:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot download a folder.")
    return _serve_file(
        file, dek, file.file_type or "application/octet-stream",
        filename=file.file_name, as_attachment=True,
        range_header=request.headers.get("Range")
    )


@router.get("/preview/{file_id}")
def preview_file(
    file_id: int,
    request: Request,
    token: str = Query(None),
    db: Session = Depends(get_db)
):
    user, dek = _resolve_user(request, token, db)
    file = _get_owned_file(db, file_id, user)
    if file.is_folder:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot preview a folder.")
    if file.file_type not in PREVIEWABLE:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="This file type cannot be previewed.")
    return _serve_file(
        file, dek, file.file_type or "application/octet-stream",
        filename=file.file_name, range_header=request.headers.get("Range")
    )


@router.patch("/move")
def move_file(
    body: FileMoveBody,
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    file = _get_owned_file(db, body.file_id, current_user)
    if body.new_parent_id:
        new_dir = _get_owned_folder(db, body.new_parent_id, current_user).file_path
    else:
        new_dir = current_user.storage_path

    new_path = _unique_path(os.path.join(new_dir, file.file_name))
    shutil.move(file.file_path, new_path)
    file.file_path = new_path
    file.parent_id = body.new_parent_id
    db.commit()
    return {"message": "Moved successfully."}


def _copy_tree(db: Session, file: Files, new_parent_id, user: Users):
    """Copy a file (or folder tree) to a new parent and return the new row."""
    if new_parent_id:
        target_dir = _get_owned_folder(db, new_parent_id, user).file_path
    else:
        target_dir = user.storage_path
    new_path = _unique_path(os.path.join(target_dir, file.file_name))

    if file.is_folder:
        os.makedirs(new_path, exist_ok=True)
        new_row = Files(
            file_name=file.file_name, file_path=new_path, file_size=0,
            file_owner=user.id, file_type="folder", is_folder=True,
            parent_id=new_parent_id, create_date=datetime.now()
        )
        db.add(new_row)
        db.flush()
        children = db.query(Files).filter(
            Files.parent_id == file.id, Files.is_deleted == False
        ).all()
        for child in children:
            _copy_tree(db, child, new_row.id, user)
        return new_row

    shutil.copy2(file.file_path, new_path)
    new_row = Files(
        file_name=file.file_name, file_path=new_path, file_size=file.file_size,
        file_owner=user.id, file_type=file.file_type, is_folder=False,
        parent_id=new_parent_id, create_date=datetime.now(), enc_iv=file.enc_iv
    )
    db.add(new_row)
    db.flush()
    return new_row


@router.post("/copy", status_code=status.HTTP_201_CREATED)
def copy_file(
    body: FileCopyBody,
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    file = _get_owned_file(db, body.file_id, current_user)
    new_row = _copy_tree(db, file, body.new_parent_id, current_user)
    db.commit()
    return {"message": "Copied successfully.", "file_id": new_row.id}


def _soft_delete(db: Session, file: Files, user: Users):
    if file.is_folder:
        children = db.query(Files).filter(
            Files.parent_id == file.id, Files.is_deleted == False
        ).all()
        for child in children:
            child.is_deleted = True
            child.deleted_at = datetime.now()
        file.is_deleted = True
        file.deleted_at = datetime.now()
    else:
        user_trash = os.path.join(TRASH_DIR, str(user.id))
        os.makedirs(user_trash, exist_ok=True)
        trash_path = _unique_path(os.path.join(user_trash, file.file_name))
        if os.path.exists(file.file_path):
            shutil.move(file.file_path, trash_path)
        file.file_path = trash_path
        file.is_deleted = True
        file.deleted_at = datetime.now()


@router.delete("/delete/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    file = _get_owned_file(db, file_id, current_user)
    _soft_delete(db, file, current_user)
    db.commit()


@router.delete("/batch-delete", status_code=status.HTTP_204_NO_CONTENT)
def batch_delete(
    body: BatchDeleteBody,
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    for file_id in body.file_ids:
        file = _get_owned_file(db, file_id, current_user)
        _soft_delete(db, file, current_user)
    db.commit()


@router.post("/share")
def create_share_link(
    body: ShareCreate,
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    dek: bytes = Depends(get_current_dek)
):
    file = _get_owned_file(db, body.file_id, current_user)
    if file.is_folder:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot share a folder.")

    token = str(uuid.uuid4()).replace("-", "")
    key = crypto.key_from_token(token)
    material = crypto.wrap_with_key(dek, key)

    link = SharedLinks(
        token=token,
        file_id=file.id,
        owner_id=current_user.id,
        expire_at=datetime.now() + timedelta(hours=body.expire_hours),
        dek_wrapped=material["dek_wrapped"],
        dek_nonce=material["dek_nonce"],
        dek_tag=material["dek_tag"],
    )
    db.add(link)
    db.commit()
    return {"token": token, "expire_at": link.expire_at.isoformat(), "url": f"/api/file/shared/{token}"}


@router.get("/shared/{token}")
def download_shared_file(token: str, request: Request, db: Session = Depends(get_db)):
    link = db.query(SharedLinks).filter(SharedLinks.token == token).first()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found.")
    if datetime.now() > link.expire_at:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="This link has expired.")

    file = db.query(Files).filter(
        Files.id == link.file_id,
        Files.is_deleted == False
    ).first()
    if not file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

    dek = crypto.unwrap_with_key(
        link.dek_wrapped, link.dek_nonce, link.dek_tag, crypto.key_from_token(token)
    )
    return _serve_file(
        file, dek, file.file_type or "application/octet-stream",
        filename=file.file_name, as_attachment=True,
        range_header=request.headers.get("Range")
    )


@router.get("/shares", response_model=list[SharedLinkOut])
def list_shared_links(db: Session = Depends(get_db), current_user: Users = Depends(get_current_user)):
    return db.query(SharedLinks).filter(SharedLinks.owner_id == current_user.id).all()


@router.delete("/share/{token}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_shared_link(token: str, db: Session = Depends(get_db), current_user: Users = Depends(get_current_user)):
    link = db.query(SharedLinks).filter(
        SharedLinks.token == token,
        SharedLinks.owner_id == current_user.id
    ).first()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found.")
    db.delete(link)
    db.commit()


@router.get("/trash", response_model=list[FileOut])
def get_trash(db: Session = Depends(get_db), current_user: Users = Depends(get_current_user)):
    return db.query(Files).filter(Files.file_owner == current_user.id, Files.is_deleted == True).all()


@router.patch("/trash/restore/{file_id}")
def restore_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    file = db.query(Files).filter(
        Files.id == file_id,
        Files.file_owner == current_user.id,
        Files.is_deleted == True
    ).first()
    if not file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found in trash.")

    restore_dir = current_user.storage_path
    if file.parent_id:
        parent = db.query(Files).filter(
            Files.id == file.parent_id, Files.is_deleted == False
        ).first()
        if parent:
            restore_dir = parent.file_path
    os.makedirs(restore_dir, exist_ok=True)
    restore_path = _unique_path(os.path.join(restore_dir, file.file_name))

    if file.is_folder:
        file.file_path = restore_path
    else:
        if os.path.exists(file.file_path):
            shutil.move(file.file_path, restore_path)
        file.file_path = restore_path

    file.is_deleted = False
    file.deleted_at = None
    db.commit()
    return {"message": "Restored."}


@router.delete("/trash/permanent/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def permanent_delete(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    file = db.query(Files).filter(
        Files.id == file_id,
        Files.file_owner == current_user.id,
        Files.is_deleted == True
    ).first()
    if not file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")
    if file.file_path and os.path.exists(file.file_path):
        if file.is_folder:
            shutil.rmtree(file.file_path, ignore_errors=True)
        else:
            os.remove(file.file_path)
    db.delete(file)
    db.commit()


@router.delete("/trash/empty", status_code=status.HTTP_204_NO_CONTENT)
def empty_trash(db: Session = Depends(get_db), current_user: Users = Depends(get_current_user)):
    files = db.query(Files).filter(
        Files.file_owner == current_user.id,
        Files.is_deleted == True,
        Files.is_folder == False
    ).all()
    for f in files:
        if f.file_path and os.path.exists(f.file_path):
            os.remove(f.file_path)
        db.delete(f)
    folders = db.query(Files).filter(
        Files.file_owner == current_user.id,
        Files.is_deleted == True,
        Files.is_folder == True
    ).all()
    for f in folders:
        db.delete(f)
    db.commit()


@router.patch("/star/{file_id}")
def toggle_star(file_id: int, db: Session = Depends(get_db), current_user: Users = Depends(get_current_user)):
    file = _get_owned_file(db, file_id, current_user)
    file.is_starred = not file.is_starred
    db.commit()
    return {"is_starred": file.is_starred}


@router.get("/starred", response_model=list[FileOut])
def get_starred(db: Session = Depends(get_db), current_user: Users = Depends(get_current_user)):
    return db.query(Files).filter(
        Files.file_owner == current_user.id,
        Files.is_starred == True,
        Files.is_deleted == False
    ).all()


@router.get("/storage-breakdown", response_model=list[FileOut])
def get_storage_breakdown(db: Session = Depends(get_db), current_user: Users = Depends(get_current_user)):
    return db.query(Files).filter(
        Files.file_owner == current_user.id,
        Files.is_deleted == False,
        Files.is_folder == False
    ).order_by(Files.file_size.desc()).limit(100).all()


def _walk_folder(db: Session, folder: Files, dek: bytes, archive: zipfile.ZipFile, prefix: str):
    for child in db.query(Files).filter(
        Files.parent_id == folder.id, Files.is_deleted == False
    ).all():
        entry_name = f"{prefix}{child.file_name}"
        if child.is_folder:
            archive.writestr(entry_name + "/", b"")
            _walk_folder(db, child, dek, archive, entry_name + "/")
        else:
            data = io.BytesIO()
            for chunk in crypto.iter_decrypted(child.file_path, dek, child.enc_iv):
                data.write(chunk)
            data.seek(0)
            archive.writestr(entry_name, data.read())


@router.get("/download-folder/{file_id}")
def download_folder(
    file_id: int,
    request: Request,
    token: str = Query(None),
    db: Session = Depends(get_db)
):
    user, dek = _resolve_user(request, token, db)
    folder = _get_owned_file(db, file_id, user)
    if not folder.is_folder:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not a folder.")

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        _walk_folder(db, folder, dek, zf, f"{folder.file_name}/")
    archive.seek(0)

    headers = {"Content-Disposition": _content_disposition(f"{folder.file_name}.zip", attachment=True)}
    return StreamingResponse(archive, media_type="application/zip", headers=headers)

