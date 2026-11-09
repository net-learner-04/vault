# Vault

A self-hosted private cloud drive with a Windows 98 UI

Icon Source : https://win98icons.alexmeub.com/

---

## Features

- Upload / download / preview (images, video, PDF, text)
- **Per-user encryption** — even an admin cannot read other users' files
- Folders: create, rename, move, copy, download as ZIP
- Starred files, trash (30-day), share links, search, multi-select
- Admin console (approve/reject account requests, manage users)

---

## Prerequisites

1. A **DuckDNS** domain + token (e.g. `vault.duckdns.org`)
2. **Port forwarding** on your router: 80, 443 → server IP
3. Docker + Docker Compose installed on the server

---

## Install (Rocky Linux)

```bash
# 1) Install Docker CE (Rocky 9's dnf "docker" is Podman, so use the official repo)
sudo dnf install -y dnf-plugins-core
sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl enable --now docker

# 2) Clone
cd ~
git clone https://github.com/net-learner-04/vault.git
cd vault

# 3) Configure
cp .env.example .env
nano .env        # fill in the values from the table below

# 4) Run
docker compose up -d --build
```

Access: `https://vault.duckdns.org`

Admin login: `ADMIN_EMAIL` + `ADMIN_PASSWORD` from `.env`

---

## .env settings

Copy `.env.example` and fill in the values.

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | ✅ | Random value for JWT signing (`openssl rand -hex 32`) |
| `RECOVERY_KEY` | ⚠️ | Recovery key for password reset (falls back to `SECRET_KEY`) |
| `ADMIN_PASSWORD` | ✅ | Admin password |
| `ADMIN_EMAIL` | ✅ | Admin login email |
| `DATABASE_URL` | ✅ | Keep `sqlite:////data/vault.db` for Docker |
| `UPLOAD_DIR` | ✅ | Keep `/data/uploads` for Docker |
| `SENDGRID_API_KEY` | ❌ | For password-reset emails (optional) |
| `MAIL_FROM` | ❌ | Sender email |
| `DUCKDNS_DOMAIN` | ✅ | e.g. `vault.duckdns.org` |
| `DUCKDNS_SUBDOMAINS` | ✅ | e.g. `vault` |
| `DUCKDNS_TOKEN` | ✅ | DuckDNS token |
| `TZ` | ❌ | Timezone (e.g. `Asia/Seoul`) |

---

## Update

```bash
cd ~/vault
git pull
docker compose up -d --build
```

---

## Common commands

```bash
docker compose ps        # status
docker compose logs -f   # logs
docker compose down      # stop
docker compose up -d     # start
```

---

## Project structure (brief)

```
vault/
├── main.py           # entry point
├── users.py          # account API
├── files.py          # file API
├── admin.py          # admin API
├── crypto.py         # file encryption
├── frontend/         # HTML/CSS/JS (Windows 98 theme)
│   └── icon/         # icons
├── docker-compose.yml
├── Caddyfile         # automatic HTTPS
└── .env.example
```

Interactive API docs: `https://vault.duckdns.org/docs`
