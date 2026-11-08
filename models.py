from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, BigInteger
from db import Base
from datetime import datetime


class Users(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, nullable=False)
    name = Column(String, nullable=False, unique=True)
    passwd = Column(String, nullable=False)
    email = Column(String, unique=True)
    storage_path = Column(String, nullable=True)
    is_admin = Column(Boolean, default=False, nullable=False)
    failed_login = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime, nullable=True)
    last_login = Column(DateTime, nullable=True)
    profile_image = Column(String, nullable=True)
    is_dormant = Column(Boolean, default=False, nullable=False)
    storage_limit = Column(BigInteger, nullable=True)
    # Encryption material for this user's files. The DEK is stored wrapped
    # with a key derived from the user password, so it cannot be used without
    # the password (admins included).
    dek_wrapped = Column(String, nullable=True)
    dek_nonce = Column(String, nullable=True)
    dek_tag = Column(String, nullable=True)
    kek_salt = Column(String, nullable=True)
    # Recovery copy of the DEK, wrapped with the server's admin recovery key.
    # Used to restore access when a user forgets their password.
    dek_wrapped_recovery = Column(String, nullable=True)
    dek_nonce_recovery = Column(String, nullable=True)
    dek_tag_recovery = Column(String, nullable=True)


class Files(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, nullable=False)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    file_owner = Column(Integer, ForeignKey("users.id"), nullable=False)
    file_type = Column(String(50))
    is_deleted = Column(Boolean, default=False)
    is_folder = Column(Boolean, default=False, nullable=False)
    parent_id = Column(Integer, ForeignKey("files.id"), nullable=True)
    create_date = Column(DateTime, nullable=False, default=datetime.now)
    is_starred = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime, nullable=True)
    # Per-file AES-CTR IV (base64). Folders have no IV.
    enc_iv = Column(String, nullable=True)


class SharedLinks(Base):
    __tablename__ = "shared_links"

    id = Column(Integer, primary_key=True, nullable=False)
    token = Column(String, nullable=False, unique=True)
    file_id = Column(Integer, ForeignKey("files.id"), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    expire_at = Column(DateTime, nullable=False)
    create_date = Column(DateTime, nullable=False, default=datetime.now)
    # The owner's DEK wrapped with a key derived from the share token, so the
    # shared file can be served without the owner being logged in.
    dek_wrapped = Column(String, nullable=True)
    dek_nonce = Column(String, nullable=True)
    dek_tag = Column(String, nullable=True)


class AccountRequests(Base):
    __tablename__ = "account_requests"

    id = Column(Integer, primary_key=True, nullable=False)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    passwd = Column(String, nullable=False)
    message = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    status = Column(String, default="pending", nullable=False)
