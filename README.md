# Vault

A self-hosted private cloud storage server built with FastAPI and vanilla HTML/CSS/JS, styled after the classic Windows 98 desktop.

---

## Tech Stack

- **Backend** — FastAPI, SQLAlchemy, SQLite
- **Encryption** — AES-256 (per-user keys, `cryptography`)
- **Auth** — JWT (python-jose), bcrypt
- **Email** — SendGrid
- **Frontend** — Vanilla HTML / CSS / JavaScript (Windows 98 theme)
- **Reverse proxy** — Nginx
- **Process manager** — systemd
- **Security** — fail2ban, SELinux

---

## Features

- File upload, download, preview (images, video, PDF, text) with HTTP range support
- **Per-user encryption**: files are stored encrypted; even an administrator with full DB/disk access cannot read another user's files
- Folder creation, renaming, moving and copying (including whole folder trees)
- Folder download as ZIP
- Starred files and trash bin (30-day auto-delete)
- Shareable links with expiry, listing and revocation
- Full-text filename search, grid/list view toggle, drag-and-drop upload
- Email-based login with account lockout and dormant detection
- Profile picture upload and account settings (integrated into the main dashboard)
- Admin console (users, account requests, storage limits) integrated into the same dashboard

---

## Encryption model

Each user has a random 256-bit Data Encryption Key (DEK). The DEK is stored in the
database **wrapped with a key derived from the user's password** (PBKDF2 + AES-GCM),
so it cannot be used without the password. Files are stream-encrypted on disk with
AES-256-CTR (each file has its own random IV).

Consequences of this zero-knowledge design:

- An administrator cannot decrypt another user's files via the UI, the database, or the disk.
- Changing your password (while logged in) re-wraps the same DEK, so your files stay readable.
- A **forgot-password reset recovers the DEK via the server's admin recovery key** (`RECOVERY_KEY`),
  then re-wraps it under the new password, so the user's files remain readable.

---

## Project Structure

```
vault/
├── main.py               Entry point + router registration
├── config.py             App configuration
├── auth.py               JWT auth + current user/DEK dependencies
├── crypto.py             AES key wrapping + streaming file encryption
├── db.py                 Database session + lightweight migrations
├── models.py             SQLAlchemy models
├── schemas.py            Pydantic schemas
├── users.py              User router + CRUD + key management
├── files.py              File router + service (upload/download/share/trash)
├── admin.py              Admin router
├── mailer.py             SendGrid email sender
├── .env                  Secrets (not committed)
└── frontend/
    ├── index.html        Landing page
    ├── login.html
    ├── register.html
    ├── reset_password.html
    ├── dashboard.html    Unified drive + admin + settings app
    ├── css/style.css     Windows 98 theme
    └── js/api.js         Shared API/auth helpers
```

---

## Configuration

Create a `.env` file in the project root before running.

```env
SECRET_KEY=your_random_secret_key
RECOVERY_KEY=your_admin_recovery_key
DATABASE_URL=sqlite:////absolute/path/to/data/account_info.db
SENDGRID_API_KEY=SG.your_sendgrid_key
ADMIN_PASSWORD=your_admin_password
ADMIN_EMAIL=admin@example.com
MAIL_FROM=noreply@example.com
```

Non-secret settings such as `MAX_ACCOUNT`, `UPLOAD_DIR`, `LOCKOUT_MINUTES`, and `DORMANT_DAYS` are managed in `config.py`.

---

## Installation

```bash
# 1. Clone and enter the project directory
cd /home/haruki/vault

# 2. Set correct ownership on the database directory
sudo chown haruki:haruki data/

# 3. Run the setup script (installs packages and runs migrations)
sudo bash setup1.sh
```

The admin account is created automatically on first startup using the credentials in `.env`.

---

## Docker Deployment (recommended)

### 1. Prerequisites
- A DuckDNS domain (e.g. `vault.duckdns.org`) with its token.
- Ports **80** and **443** forwarded on your router to this server.
- Docker + Docker Compose installed on the server.

### 2. Prepare environment
```bash
cp .env.example .env
# edit .env: fill SECRET_KEY, ADMIN_PASSWORD, DUCKDNS_TOKEN, etc.
```

### 3. Start
```bash
docker compose up -d --build
```

Three containers run together:
- `vault` — the FastAPI app (SQLite + uploads kept in the `vault_data` volume)
- `caddy` — reverse proxy with automatic HTTPS (Let's Encrypt)
- `duckdns` — keeps the dynamic DNS record up to date

### DuckDNS without Docker (host cron)
```bash
chmod +x duckdns.sh
crontab -e
# add this line (updates every 5 minutes):
*/5 * * * * /home/<user>/vault/duckdns.sh >/dev/null 2>&1
```

---

## Running with systemd

Create `/etc/systemd/system/vault.service`:

```ini
[Unit]
Description=Vault FastAPI
After=network.target

[Service]
User=haruki
WorkingDirectory=/home/haruki/vault
ExecStart=/usr/local/bin/uvicorn main:app --host 127.0.0.1 --port 2926
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable vault
sudo systemctl start vault
```

---

## Nginx Configuration

```nginx
server {
    listen 80;
    server_name vault.duckdns.org;

    client_max_body_size 2G;

    location / {
        proxy_pass http://127.0.0.1:2926;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300;
        proxy_connect_timeout 300;
    }
}
```

Enable Nginx to connect to local ports on Rocky Linux (SELinux):

```bash
sudo setsebool -P httpd_can_network_connect 1
sudo systemctl restart nginx
```

---

## HTTPS

```bash
sudo dnf install certbot python3-certbot-nginx -y
sudo certbot --nginx -d vault.duckdns.org
```

---

## Security

fail2ban is configured to automatically ban IPs that repeatedly scan for vulnerabilities.

```bash
# Check ban status
sudo fail2ban-client status nginx-botscan

# Manually unban an IP
sudo fail2ban-client set nginx-botscan unbanip 1.2.3.4
```

---

## API Overview

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/user/login | Sign in with email and password |
| GET | /api/user/me | Get current user info |
| POST | /api/user/password/reset-request | Send a password reset code |
| POST | /api/user/password/reset | Reset password with code |
| POST | /api/file/upload | Upload a file (encrypted at rest) |
| GET | /api/file/list | List files in a folder |
| GET | /api/file/search?q= | Search files by name |
| GET | /api/file/folders | List all folders (for move/copy picker) |
| GET | /api/file/stats | Storage usage and file count |
| GET | /api/file/download/{id} | Download a file |
| GET | /api/file/preview/{id} | Preview a file (range-capable) |
| GET | /api/file/download-folder/{id} | Download a folder as ZIP |
| PATCH | /api/file/rename/{id} | Rename a file or folder |
| PATCH | /api/file/move | Move a file/folder |
| POST | /api/file/copy | Copy a file/folder |
| GET | /api/file/starred | List starred files |
| GET | /api/file/trash | List trashed files |
| PATCH | /api/file/star/{id} | Toggle star on a file |
| DELETE | /api/file/delete/{id} | Move file to trash |
| DELETE | /api/file/batch-delete | Move multiple files to trash |
| PATCH | /api/file/trash/restore/{id} | Restore file from trash |
| DELETE | /api/file/trash/permanent/{id} | Permanently delete a file |
| DELETE | /api/file/trash/empty | Empty all trash |
| POST | /api/file/share | Create a share link |
| GET | /api/file/shares | List share links |
| DELETE | /api/file/share/{token} | Revoke a share link |
| GET | /api/admin/users | List all users (admin only) |
| PATCH | /api/admin/users/{id}/storage-limit | Set per-user storage limit |
| PATCH | /api/admin/users/{id}/lock | Lock a user account |
| PATCH | /api/admin/users/{id}/unlock | Unlock a user account |
| PATCH | /api/admin/users/{id}/dormant-unlock | Reactivate a dormant account |
| DELETE | /api/admin/users/{id} | Delete a user |
| GET | /api/admin/requests | List pending account requests |
| POST | /api/admin/requests/{id}/approve | Approve a request |
| DELETE | /api/admin/requests/{id}/reject | Reject a request |

Full interactive API docs are available at `/docs` when the server is running.
