from dotenv import load_dotenv
import os

load_dotenv()


# Root directory where uploaded files are stored.
UPLOAD_DIR: str = "/mnt/storage/vault/uploads"
# Subdirectory inside UPLOAD_DIR for profile images (auto-set).
PROFILE_DIR: str = os.path.join(UPLOAD_DIR, "_profiles")


# Username of the auto-created admin account.
ADMIN_USERNAME: str = "admin"
# Maximum number of non-admin accounts allowed.
MAX_ACCOUNT: int = 10
# Number of failed logins before account lockout.
MAX_FAILED_LOGIN: int = 5
# How long the account stays locked after too many failures.
LOCKOUT_MINUTES: int = 15
# Days of inactivity before an account is marked dormant.
DORMANT_DAYS: int = 30


# JWT signing algorithm (do not change unless you know what you are doing).
ALGORITHM: str = "HS256"
# How long a login session stays valid (1440 = 24 hours).
ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440


# Display name shown in the From field of outgoing emails.
MAIL_FROM_NAME: str = "Vault"


# Random secret used to sign JWT tokens.
SECRET_KEY: str = os.getenv("SECRET_KEY", "")
# Server secret used to recover a user's encryption key during a forgot-password
# reset. Defaults to SECRET_KEY when not set explicitly.
RECOVERY_KEY: str = os.getenv("RECOVERY_KEY", "") or SECRET_KEY
# SQLAlchemy connection string to the SQLite database file.
DATABASE_URL: str = os.getenv("DATABASE_URL", "")
# API key from SendGrid for sending emails.
SENDGRID_API_KEY: str = os.getenv("SENDGRID_API_KEY", "")
# Password for the auto-created admin account.
ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")
# Email address for the auto-created admin account.
ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "")
# Sender email address shown in outgoing emails.
MAIL_FROM: str = os.getenv("MAIL_FROM", "")
