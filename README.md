# Nexus AI — Trợ lý AI cá nhân đa kênh

Trợ lý AI cá nhân chạy qua webhook **Telegram / Zalo / Messenger**: hội thoại có bộ nhớ dài hạn,
nghiên cứu thông tin trên Internet, lời nhắc chủ động qua chat, xử lý nền qua hàng đợi in-process.

**Quickstart (Docker Compose — khuyến nghị):**

```bash
cp .env.example .env          # điền TELEGRAM_BOT_TOKEN, GEMINI_API_KEY (xem bảng bên dưới)
docker compose up -d --build
curl localhost:8000/health    # {"status":"ok","db":"ok",...}
```

## Stack

- **Backend:** FastAPI + uvicorn · PostgreSQL 16 (SQLAlchemy 2.0 async + asyncpg) · Google Gemini (`google-genai`) · httpx · pydantic-settings
- **Docker:** app (`python:3.12-slim`) + `postgres:16-alpine`
- **Python 3.12** — không thêm dependency ngoài `requirements.txt`

## Cấu trúc thư mục

```text
AI-assistant/
│
├── app/
│   ├── main.py                 # entry point, lifespan, /health, middleware log
│   │
│   ├── api/                    # placeholder rỗng (cho tương lai)
│   │   ├── routes.py
│   │   └── schemas.py
│   │
│   ├── channels/               # transport 3 kênh + dispatcher outbound
│   │   ├── base.py             # IncomingMessage, send_text(), xác thực chữ ký
│   │   ├── telegram.py
│   │   ├── zalo.py
│   │   └── messenger.py
│   │
│   ├── conversation/
│   │   ├── handler.py          # điều phối 1 lượt hội thoại
│   │   ├── tools.py            # khai báo + thực thi tool LLM
│   │   └── context_builder.py
│   │
│   ├── agents/
│   │   └── research.py         # pipeline nghiên cứu
│   │
│   ├── memory/                 # manager / retriever / extractor
│   ├── research/               # search / collector / filter / summarizer
│   ├── reminders/              # service / notifier / scheduler
│   ├── database/               # connection / models / repository
│   │
│   └── core/
│       ├── config.py           # pydantic-settings (đọc .env)
│       ├── llm.py              # Gemini + retry + LLM_GATE
│       ├── queue.py            # hàng đợi tin nhắn + retry/dead-letter (T58–T59)
│       ├── ratelimit.py        # RateGate cho LLM/search (T60)
│       └── alert.py            # ALERT_WEBHOOK_URL (T69)
│
├── prompts/                    # assistant / research / summarizer / memory-extractor (.md)
├── tests/                      # 184 tests (pytest)
├── scripts/telegram_poll.py    # chế độ long-poll thay webhook (chạy host)
├── .github/workflows/ci.yml    # CI: test + docker-build
├── pytest.ini
├── .env.example
├── Dockerfile
├── docker-compose.yml
└── README.md
```

Ghi chú: namespace packages — dự án **không** dùng `__init__.py`.

## Cài đặt local (không Docker cho app)

**Yêu cầu:** Python 3.12, PostgreSQL 16 đang chạy.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# điền DATABASE_URL (trỏ localhost + password PG local), TELEGRAM_BOT_TOKEN, GEMINI_API_KEY

uvicorn app.main:app --reload          # API + webhook + scheduler + queue worker
# hoặc long-poll thay webhook:
python -m scripts.telegram_poll
curl localhost:8000/health
```

## Cài đặt Docker Compose (khuyến nghị)

```bash
cp .env.example .env
# TỐI THIỂU: TELEGRAM_BOT_TOKEN, GEMINI_API_KEY (DATABASE_URL compose TỰ override)
docker compose up -d --build
docker compose ps                # app healthy / db healthy
curl localhost:8000/health
docker compose logs -f app
```

Những gì compose lo:

- **`DATABASE_URL` được override** sang host `db` trong network (env var thắng `.env`) —
  dòng `localhost` trong `.env` chỉ dùng cho host-run.
- **Healthchecks:** db `pg_isready` → app chỉ khởi động khi db healthy; app `/health` mỗi 30s
  (503 → container *unhealthy*; `restart: unless-stopped` chỉ restart khi process chết, không restart loop).
- **Log xoay vòng:** json-file 10MB × 3.
- **Postgres chỉ mở `127.0.0.1:5432`** trên host (đổi port nếu xung đột với PG đang chạy).
- **Queue in-process** (asyncio trong app) — không có service redis/celery.

## Cấu hình `.env`

| Biến | Bắt buộc | Mô tả |
|---|---|---|
| `ENV` | không | `development` / `production` |
| `DATABASE_URL` | **có** | App **fail-fast** nếu trống. Host-run: `postgresql+asyncpg://user:pass@localhost:5432/nexus_ai`. Compose tự override. |
| `POSTGRES_PASSWORD` | không | Chỉ cho compose (`${POSTGRES_PASSWORD:-postgres}`) — phải khớp `DATABASE_URL` nếu host-run |
| `TELEGRAM_BOT_TOKEN` | khi dùng Telegram | Từ @BotFather |
| `GEMINI_API_KEY` | **có** | Google AI Studio |
| `GEMINI_MODEL` | không | Mặc định `gemini-3.5-flash` |
| `TELEGRAM_WEBHOOK_SECRET` | production | Header `X-Telegram-Bot-Api-Secret-Token` |
| `ZALO_OA_ACCESS_TOKEN` | khi dùng Zalo | **Hết hạn ~1 giờ** — lấy lại từ Zalo OA Admin, cập nhật tay |
| `ZALO_WEBHOOK_SECRET` | production | Xác thực `X-ZEvent-Signature` (HMAC) |
| `MESSENGER_PAGE_ACCESS_TOKEN` | khi dùng Messenger | Page access token (Meta App Dashboard) |
| `MESSENGER_APP_SECRET` | production | Xác thực `X-Hub-Signature-256` |
| `MESSENGER_VERIFY_TOKEN` | khi dùng Messenger | Bước xác minh webhook GET |
| `MESSENGER_TAG` | không | MESSAGE_TAG gửi chủ động, mặc định `ACCOUNT_UPDATE` |
| `ALERT_WEBHOOK_URL` | không | Nhận POST `{"text": "..."}` khi lỗi 500 / dead-letter. **Để trống = tắt** |

> **Bí quyết secrets:** webhook secrets trống = *dev mode* (bỏ qua chữ ký) — **không dùng production**.
> `.env` không bao giờ được commit (`.gitignore`); image Docker không COPY `.env`.

## Webhook 3 kênh

| Kênh | Endpoint | Xác thực |
|---|---|---|
| Telegram | `POST /webhooks/telegram` | Header `X-Telegram-Bot-Api-Secret-Token` (BotFather → secret token) |
| Zalo | `POST /webhooks/zalo` | Header `X-ZEvent-Signature` = `sha256=` + HMAC-SHA256 (Zalo OA Admin → Callback) |
| Messenger | `GET` + `POST /webhooks/messenger` | GET: `hub.verify_token`; POST: `X-Hub-Signature-256` (Meta App Dashboard) |

Live webhook **bắt buộc** điền secret tương ứng vào `.env`, nếu không server chạy dev-mode unsigned.

## Tests & CI

```bash
pytest -q                 # đủ bộ — cần Postgres (DB test riêng nexus_ai_test, tự tạo)
pytest -q -m "not db"     # không cần Postgres
```

- `tests/conftest.py` ép `DATABASE_URL` → `nexus_ai_test` **trước** khi import app, swap engine
  sang NullPool; test DB gắn marker `db` + fixture `db_run(scenario)` (một event loop/test),
  tự skip khi Postgres khôngreachable.
- CI (`.github/workflows/ci.yml`): job `test` (Python 3.12 + postgres:16 service) +
  job `docker-build` (bắt regressions COPY).
- Không bao giờ `with TestClient(app)` trong test (vô tình chạy lifespan).

## Vận hành

- **`GET /health`** → `200 {"status":"ok","db":"ok","queue":{"pending":0,"dead_letters":0},"errors":0}`
  hoặc `503 {"status":"degraded",...}` khi DB không phản hồi.
- **Logs:** `docker compose logs -f app` (stdout, json-file đã xoay vòng). Request log dạng
  `POST /path -> status (ms)` — riêng `/health` bị loại để không spam.
- **Alert:** set `ALERT_WEBHOOK_URL` → nhận POST `{"text": "..."}` khi lỗi 500 / dead-letter;
  lỗi gửi alert chỉ ghi warning, không ảnh hưởng request.
- **Dead-letter:** log `DEAD-LETTER phase=...`; giữ tối đa 50 bản ghi gần nhất (in-memory).
- **Queue in-memory mất job đang chờ khi restart** — webhook đã trả 200 nên platform không
  redeliver; queue đầy (1000) → trả 503 để redeliver.

## Bảo mật

- `.env` **không bao giờ commit** — kiểm tra: `git ls-files .env` phải rỗng.
- Đổi password Postgres mặc định; điền webhook secrets khi expose public.
- `database_url` trong code mặc định `""` (fail-fast) — mọi secret chỉ nằm trong `.env`.

## Giới hạn đã biết

- Gemini free-tier ~20 request/ngày → 429 vào dead-letter ngay (không retry quota).
- Zalo: token ~1h; gửi chủ động ngoài cửa sổ 48h bị từ chối (tick scheduler thử lại).
- Queue in-process + **1 worker FIFO** (thứ tự hội thoại per-user) + single uvicorn worker —
  không chạy multi-process/`--workers`.
- Chưa có reverse proxy/TLS — tự thêm nginx/caddy nếu expose public.

---

![alt text](image.png)
