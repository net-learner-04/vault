# Vault

개인용 셀프호스팅 클라우드 드라이브. Windows 98 레트로 UI + 사용자별 파일 암호화.

---

## 주요 기능

- 파일 업로드 / 다운로드 / 미리보기 (이미지·영상·PDF·텍스트)
- **사용자별 암호화** — 관리자라도 다른 사용자 파일 열람 불가
- 폴더 생성·이름변경·이동·복사, 폴더 ZIP 다운로드
- 즐겨찾기, 휴지통(30일), 공유 링크, 검색, 다중 선택
- 관리자 콘솔 (계정 요청 승인/거절, 사용자 관리)

---

## 사전 준비

1. **DuckDNS** 도메인 + 토큰 확보 (예: `vault.duckdns.org`)
2. **공유기 포트포워딩**: 80, 443 → 서버 IP
3. 서버에 Docker + Docker Compose 설치

---

## 설치 (Rocky Linux 기준)

```bash
# 1) Docker CE 설치 (Rocky 9은 dnf의 docker가 Podman이라 공식 repo로 설치)
sudo dnf install -y dnf-plugins-core
sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl enable --now docker

# 2) 코드 받기
cd ~
git clone https://github.com/net-learner-04/vault.git
cd vault

# 3) 환경설정
cp .env.example .env
nano .env        # 아래 표 참고해서 값 입력

# 4) 실행
docker compose up -d --build
```

접속: `https://vault.duckdns.org`

관리자 로그인: `.env`의 `ADMIN_EMAIL` + `ADMIN_PASSWORD`

---

## .env 설정

`.env.example`을 복사해서 사용하면 됩니다.

| 변수 | 필수 | 설명 |
|------|------|------|
| `SECRET_KEY` | ✅ | JWT 서명용 랜덤값 (`openssl rand -hex 32`) |
| `RECOVERY_KEY` | ⚠️ | 비번찾기 복구용 (없으면 `SECRET_KEY`로 대체) |
| `ADMIN_PASSWORD` | ✅ | 관리자 비밀번호 |
| `ADMIN_EMAIL` | ✅ | 관리자 로그인 이메일 |
| `DATABASE_URL` | ✅ | Docker는 `sqlite:////data/vault.db` 그대로 |
| `UPLOAD_DIR` | ✅ | Docker는 `/data/uploads` 그대로 |
| `SENDGRID_API_KEY` | ❌ | 비번찾기 메일용 (안 써도 됨) |
| `MAIL_FROM` | ❌ | 발신 이메일 |
| `DUCKDNS_DOMAIN` | ✅ | 예: `vault.duckdns.org` |
| `DUCKDNS_SUBDOMAINS` | ✅ | 예: `vault` |
| `DUCKDNS_TOKEN` | ✅ | DuckDNS 토큰 |
| `TZ` | ❌ | 시간대 (예: `Asia/Seoul`) |

---

## 업데이트

```bash
cd ~/vault
git pull
docker compose up -d --build
```

---

## 자주 쓰는 명령어

```bash
docker compose ps        # 상태 확인
docker compose logs -f   # 로그
docker compose down      # 중지
docker compose up -d     # 시작
```

---

## 프로젝트 구조 (간단히)

```
vault/
├── main.py           # 진입점
├── users.py          # 계정 API
├── files.py          # 파일 API
├── admin.py          # 관리자 API
├── crypto.py         # 파일 암호화
├── frontend/         # HTML/CSS/JS (Win98 테마)
│   └── icon/         # 아이콘
├── docker-compose.yml
├── Caddyfile         # 자동 HTTPS
└── .env.example
```

자세한 API는 실행 후 `https://vault.duckdns.org/docs` 에서 확인 가능.
