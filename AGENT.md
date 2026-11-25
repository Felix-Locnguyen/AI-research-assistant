# Nexus AI — Tổng hợp dự án

## 1. Tổng quan

Nexus AI là trợ lý AI cá nhân đa kênh (Telegram / Zalo / Messenger): hội thoại có bộ nhớ dài hạn,
nghiên cứu thông tin trên Internet, lời nhắc chủ động qua chat.

**Stack:** FastAPI + uvicorn · PostgreSQL (SQLAlchemy 2.0 async + asyncpg) · Google Gemini
(`google-genai`) · httpx · pydantic-settings. Docker Compose gồm app (`python:3.12-slim`) + `postgres:16`.
Tracker công việc chính: **TASK.md** (T01–T69 theo 11 EPIC).

## 2. Kiến trúc & luồng tin nhắn

```
Telegram/Zalo/Messenger webhook (app/main.py) hoặc scripts/telegram_poll.py
  → xác thực chữ ký → normalize → core/queue.enqueue (trả 200 ngay — T58)
  → worker (1 task): handle_message (retry ≤3, 429 → dead-letter ngay — T59)
      → UserRepository / MemoryManager / ConversationRepository (lịch sử 20 tin — T31)
      → retriever.retrieve (xếp hạng ký ức theo câu hỏi) + context_builder (prompts/assistant.md)
      → llm.generate — vòng lặp tool tối đa 3 lượt (qua LLM_GATE — T60)
           SAVE_PREFERENCE · SAVE_MEMORY · MANAGE_MEMORY · RESEARCH · REMINDER
      → lưu message → trả lời; extractor.spawn chạy nền (T32)
  → base.send_text (retry ≤3, chỉ retry send — không chạy lại handle)
```

**Các gói:**

| Gói | Vai trò |
|---|---|
| `channels/` | Transport; telegram/zalo/messenger đều hoạt động (`send_text` + webhook xác thực chữ ký); dispatcher outbound ở `base.py` (EPIC 08) |
| `conversation/` | `handler` điều phối lượt; `tools.py` khai báo + thực thi tool LLM |
| `agents/research.py` | Pipeline nghiên cứu: tạo truy vấn → tìm kiếm → lọc → tóm tắt → lưu → định dạng |
| `memory/` | `manager` (validate/CRUD/markdown), `retriever` (token-ranking), `extractor` (trích xuất nền) |
| `reminders/` | `service` (CRUD + múi giờ + lặp), `notifier` (gửi theo kênh), `scheduler` (quét 60s) |
| `research/` | `search` (ddgs), `collector` (fetch HTML + RSS), `filter` (trùng lặp/liên quan), `summarizer` |
| `database/` | `models` (8 bảng) + `repository` (mỗi entity một repo, commit trong method) |
| `core/` | `config` (pydantic-settings), `llm` (retry/backoff + `LLM_GATE`), `queue` (async queue + retry/dead-letter, T58–T59), `ratelimit` (`RateGate`, T60), `alert` (`ALERT_WEBHOOK_URL`, T69) |

## 3. Trạng thái các EPIC

| EPIC | Nội dung | Trạng thái |
|---|---|---|
| 01 | Project init (FastAPI, env, Docker) | ✅ Xong |
| 02 | Database & user management | ✅ Xong (không Alembic — dùng `create_all`) |
| 03 | Telegram integration | ✅ Xong (webhook + polling) |
| 04 | AI conversation (tool-calling) | ✅ Xong |
| 05 | Memory management (T31–T37) | ✅ Xong |
| 06 | Research agent (T38–T47) | ✅ Xong |
| 07 | Reminder system (T48–T53) | ✅ Xong |
| 08 | Zalo & Messenger (T54–T57) | ✅ Xong |
| 09 | Background queue & rate limiting (T58–T60) | ✅ Xong |
| 10 | Testing & CI (T61–T64) | ✅ Xong (184 tests, CI GitHub Actions) |
| 11 | Deployment & ops (T65–T69) | ✅ Xong (compose full-stack, fail-fast DATABASE_URL, /health, README, alert tùy chọn) |

## 4. Quy ước kỹ thuật (bắt buộc khi sửa code)

- **Datetime lưu naive-UTC:** `datetime.now(UTC).replace(tzinfo=None)` — khớp `func.now()` của Postgres.
  Đổi múi giờ chỉ ở biên vào/ra qua `zoneinfo`; tz của user nằm ở `user_preferences['timezone']`,
  mặc định `Asia/Ho_Chi_Minh`.
- **Schema:** `Base.metadata.create_all` khi boot; thêm cột vào bảng cũ → `ALTER TABLE ... ADD COLUMN
  IF NOT EXISTS` idempotent trong `init_db()` (`app/database/connection.py`). Không dùng Alembic.
- **Repository:** class bọc một `AsyncSession`, commit trong method, mọi truy vấn scope theo `user_id`.
- **Tool LLM:** hằng `types.Tool` trong `conversation/tools.py` + nhánh trong `execute()` trả chuỗi
  tiếng Việt; model học id qua kết quả dạng `id=N` và tool liệt kê danh sách.
- **LLM trả JSON:** `llm.generate(..., response_schema=...)` rồi `json.loads(response.text)`.
- **Task nền** (extractor / scheduler / cleanup): `asyncio.create_task` trong lifespan, mở session riêng
  mỗi lần chạy, nuốt lỗi + log, `cancel()` ở `finally`; giữ tham chiếu task để tránh bị GC.
- **Thư viện chuyên dụng:** `ddgs` (search, có retry), `feedparser` (RSS), `beautifulsoup4` (trích HTML).
- **Test (EPIC 10):** sync tests + `asyncio.run` (không pytest-asyncio); `tests/conftest.py` ép
  `DATABASE_URL` → DB riêng `nexus_ai_test` TRƯỚC khi import app (engine bind lúc import) và swap
  engine sang **NullPool** (pool mặc định dính "attached to a different loop" với asyncio.run từng test);
  test DB gắn marker `db` + fixture `db_run(scenario)` — TOÀN BỘ scenario chạy trong MỘT loop
  (truncate trước/sau, skip tự động khi Postgres khôngreachable); không bao giờ `with TestClient(app)`
  (vô tình chạy lifespan); monkeypatch theo bound name trong module under test.
- Ghi chú/hàm và nội dung người dùng: **tiếng Việt**. Namespace packages (không `__init__.py`).

## 5. Chạy & kiểm chứng

```bash
# .env cần: TELEGRAM_BOT_TOKEN, GEMINI_API_KEY (+ DATABASE_URL nếu host-run — xem .env.example)
docker compose up -d --build   # app + Postgres; compose tự override DATABASE_URL → host `db`
uvicorn app.main:app --reload   # host-run (cần Postgres local)
python scripts/telegram_poll.py # chế độ long-poll local
curl localhost:8000/health      # 200 {status,db,queue,errors} / 503 degraded

# Tests (CI: .github/workflows/ci.yml — 2 job: test + docker-build)
pytest -q                      # đủ bộ (cần Postgres — DB test riêng nexus_ai_test)
pytest -q -m "not db"          # không cần Postgres
```

Lưu ý: Gemini free-tier giới hạn ~20 request/ngày — test nhiều sẽ gặp `429 RESOURCE_EXHAUSTED`.
Các pipeline đã có fallback: research suy giảm còn title+link, extractor nuốt lỗi, query-gen dùng
câu hỏi gốc. Queue (EPIC 09) + test (EPIC 10) kiểm chứng bằng unit test + curl — không cần live LLM.

## 6. Việc còn lại & điểm đã biết

- **Cả 11 EPIC đã xong.** Việc lẻ: e2e chat qua LLM còn chờ quota Gemini reset; webhook secret
  production chưa điền vào `.env` (đang dev mode); chưa có reverse proxy/TLS khi expose public.
- **EPIC 11:** compose full-stack (healthcheck/restart/log rotation, PG chỉ `127.0.0.1`),
  `DATABASE_URL` fail-fast khi trống (password không còn trong code), `/health` 200/503 +
  queue stats + error counter, README tiếng Việt, alert tùy chọn `ALERT_WEBHOOK_URL` (500 + dead-letter).
  **Đổi shape `/health`:** không còn `{"status":"ok"}` đơn giản — test `test_health_ok` đã cập nhật.
- **Test (EPIC 10):** 184 tests — CI `.github/workflows/ci.yml` (Python 3.12 + postgres:16 service,
  `pip install -r requirements.txt pytest` + job docker-build). Lưu ý: `LLM_GATE` trong `llm.py` từng bị
  mất trong commit `a709840` (lạc khỏi thay đổi EPIC 09) → đã khôi phục ở đầu EPIC 10.
- **Queue (EPIC 09):** in-memory — mất job đang chờ khi restart (webhook đã trả 200 nên platform
  không redeliver; queue đầy → 503 để redeliver); 1 worker FIFO (giữ thứ tự hội thoại per-user —
  tăng worker cần per-user lock); notifier/scheduler KHÔNG qua queue (gửi trực tiếp, retry theo tick).
- **Bảo mật:** webhook đã xác thực chữ ký cả 3 kênh (Telegram secret token / Zalo `X-ZEvent-Signature` /
  Messenger `X-Hub-Signature-256`, secret trống = dev mode); `database_url` mặc định `""` + fail-fast —
  mọi secret chỉ nằm trong `.env` (không commit).
- **Zalo:** `ZALO_OA_ACCESS_TOKEN` hết hạn ~1h, cập nhật thủ công trong `.env` (không có refresh flow);
  gửi chủ động ngoài cửa sổ 48h CS sẽ bị từ chối → scheduler thử lại tick sau.
- **Messenger:** gửi chủ động (lời nhắc) dùng `MESSAGE_TAG` (`MESSENGER_TAG`, mặc định `ACCOUNT_UPDATE`).
- **Kiểm chứng đã chạy:** EPIC 05–09 xác minh trực tiếp (curl webhook e2e); EPIC 10: 184 tests green
  (31 db trên Postgres local, skip khi không có PG); EPIC 11: compose e2e (app+db healthy, health
  200 → 503 khi stop db → 200 khi start lại, tz probe ok, log middleware đúng). Chờ: quota Gemini.
