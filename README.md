# ⚡ AI Summary

**YouTube / Audio-Video File → Transcript + Structured Summary**

Production-ready MVP сервис для личного использования: отправляешь YouTube-ссылку или загружаешь аудио/видео файл — получаешь полный транскрипт и структурированное саммари.

---

## Возможности

- **YouTube** — автоматическое получение субтитров (ручные > автогенерированные), fallback на ASR
- **Upload** — загрузка аудио/видео файлов (до 250 МБ)
- **ASR** — транскрипция через OpenAI `gpt-4o-transcribe` с автоматическим разбиением на чанки
- **Саммари** — структурированное резюме через `gpt-4o-mini` (map-reduce для длинных текстов)
- **3 уровня**: short / medium / detailed
- **3 языка**: auto / ru / en
- **Async обработка** — RQ (Redis Queue), poll по job_id
- **Авторизация** — регистрация/логин → API-ключ
- **Dark UI** — современный фронтенд с drag&drop, историей, прогресс-баром

## Стек

| Компонент | Технология |
|-----------|-----------|
| Backend | Python + FastAPI |
| Database | **Supabase** (PostgreSQL) |
| Queue | Redis + RQ |
| Transcription | OpenAI gpt-4o-transcribe |
| Summary | OpenAI gpt-4o-mini |
| YouTube | yt-dlp + youtube-transcript-api |
| Audio | ffmpeg |
| Deploy | Railway |
| Frontend | Vanilla HTML/CSS/JS (dark theme) |

## Структура проекта

```
AI-summary/
├── app/
│   ├── main.py                 # FastAPI приложение
│   ├── config.py               # Настройки (env vars)
│   ├── api/
│   │   ├── auth.py             # POST /v1/auth/register, /login, /rotate-key
│   │   ├── youtube.py          # POST /v1/youtube
│   │   ├── upload.py           # POST /v1/upload
│   │   ├── jobs.py             # GET /v1/jobs/{id}, /result
│   │   └── deps.py             # Auth dependency
│   ├── services/
│   │   ├── youtube.py          # yt-dlp + youtube-transcript-api
│   │   ├── transcribe.py       # OpenAI transcription + chunking
│   │   └── summarize.py        # Map-reduce summarization
│   ├── workers/
│   │   └── tasks.py            # RQ background tasks
│   ├── db/
│   │   ├── database.py         # SQLAlchemy engine (→ Supabase)
│   │   └── models.py           # ORM модели (summary_users, summary_jobs)
│   └── static/
│       ├── index.html
│       ├── styles.css
│       └── app.js
├── Dockerfile
├── docker-compose.yml          # Локально (только Redis)
├── start.sh                    # Entrypoint (web)
├── worker.sh                   # Entrypoint (RQ worker)
├── railway.toml
├── Procfile
├── requirements.txt
└── README.md
```

## API

### Аутентификация

```bash
# Регистрация
curl -X POST https://YOUR-APP.up.railway.app/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "myuser", "password": "mypass123"}'
# → {"api_key": "...", "username": "myuser"}

# Логин
curl -X POST https://YOUR-APP.up.railway.app/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "myuser", "password": "mypass123"}'

# Ротация API ключа
curl -X POST https://YOUR-APP.up.railway.app/v1/auth/rotate-key \
  -H "X-API-Key: YOUR_API_KEY"
```

### YouTube → Summary

```bash
curl -X POST https://YOUR-APP.up.railway.app/v1/youtube \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "summary_style": "medium",
    "language": "auto",
    "callback_url": "https://your-app.com/webhooks/ai-summary"
  }'
# → {"job_id": "abc-123-...", "status": "queued"}
```

### Upload → Summary

```bash
curl -X POST https://YOUR-APP.up.railway.app/v1/upload \
  -H "X-API-Key: YOUR_API_KEY" \
  -F "file=@recording.mp3" \
  -F "summary_style=detailed" \
  -F "language=ru" \
  -F "callback_url=https://your-app.com/webhooks/ai-summary"
# → {"job_id": "def-456-...", "status": "queued"}
```

### Статус и результат

```bash
# Статус
curl https://YOUR-APP.up.railway.app/v1/jobs/JOB_ID \
  -H "X-API-Key: YOUR_API_KEY"
# → {"job_id": "...", "status": "running", "progress": 45, ...}

# История задач (backend)
curl "https://YOUR-APP.up.railway.app/v1/jobs?limit=20&offset=0" \
  -H "X-API-Key: YOUR_API_KEY"

# Результат (когда status=done)
curl https://YOUR-APP.up.railway.app/v1/jobs/JOB_ID/result \
  -H "X-API-Key: YOUR_API_KEY"
# → {
#     "source": {"title": "...", "channel": "...", ...},
#     "transcript": {"text": "...", "segments": [...]},
#     "summary": {
#       "tl_dr": "...",
#       "key_points": ["..."],
#       "outline": [{title, points}],
#       "action_items": ["..."],
#       "timestamps": [{"t": "00:03:12", "label": "..."}]
#     }
#   }
```

```bash
# Скачать результат в Markdown
curl https://YOUR-APP.up.railway.app/v1/jobs/JOB_ID/result.md \
  -H "X-API-Key: YOUR_API_KEY" \
  -o ai-summary-result.md

# Скачать PDF
curl https://YOUR-APP.up.railway.app/v1/jobs/JOB_ID/result.pdf?template=default \
  -H "X-API-Key: YOUR_API_KEY" \
  -o ai-summary-result.pdf

# Скачать DOCX
curl https://YOUR-APP.up.railway.app/v1/jobs/JOB_ID/result.docx?template=meeting_notes \
  -H "X-API-Key: YOUR_API_KEY" \
  -o ai-summary-result.docx

# Retry failed job
curl -X POST https://YOUR-APP.up.railway.app/v1/jobs/JOB_ID/retry \
  -H "X-API-Key: YOUR_API_KEY"

# Cancel queued/running job
curl -X POST https://YOUR-APP.up.railway.app/v1/jobs/JOB_ID/cancel \
  -H "X-API-Key: YOUR_API_KEY"
```

## Деплой на Railway

### 1. GitHub → Railway

1. Пуш в GitHub (репо уже создан)
2. [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub Repo**
3. Выбери репо `AI-summary`

### 2. Добавь Redis

В проекте Railway: **+ New** → **Database** → **Redis**

Railway автоматически создаст `REDIS_URL`.

### 3. Переменные окружения

В настройках сервиса добавь:

| Переменная | Значение | Обязательно |
|------------|----------|:-----------:|
| `OPENAI_API_KEY` | `sk-...` | ✅ |
| `DATABASE_URL` | Supabase connection string | ✅ |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` | ✅ (авто) |
| `TRANSCRIBE_MODEL` | `gpt-4o-transcribe` | default |
| `SUMMARY_MODEL` | `gpt-4o-mini` | default |
| `MAX_UPLOAD_MB` | `250` | default |
| `YTDLP_COOKIES_PATH` | `/app/secrets/youtube_cookies.txt` | optional |
| `YTDLP_COOKIES_B64` | base64(cookies.txt) | optional |
| `YTDLP_PLAYER_CLIENT` | `android` | optional |
| `YTDLP_FALLBACK_CLIENTS` | `android,web,ios` | optional |
| `CALLBACK_TIMEOUT_SECONDS` | `10` | optional |
| `CALLBACK_RETRIES` | `2` | optional |

### Supabase DATABASE_URL

Формат: `postgresql://postgres.XXXX:PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres`

Важно:
- Для `*.pooler.supabase.com` используй пользователя вида `postgres.<project_ref>`, не просто `postgres`.
- Если пароль содержит спецсимволы (`@`, `:`, `/`, `#`, `%`) — он должен быть URL-encoded.
- В коде есть автонормализация пароля, но в переменной окружения лучше хранить уже валидный URI.

Найти: Supabase Dashboard → Settings → Database → Connection string → URI (Transaction pooler, порт 6543).

### 4. Deploy (раздельно web и worker)

Используй 2 сервиса Railway из одного репо:
- `web` service: `Start Command = bash start.sh`
- `worker` service: `Start Command = bash worker.sh`

Оба сервиса должны видеть одинаковые env vars (`DATABASE_URL`, `REDIS_URL`, `OPENAI_API_KEY`, ...).

## Локальная разработка

```bash
cp .env.example .env
# Отредактируй .env: добавь OPENAI_API_KEY и DATABASE_URL от Supabase

# Через Docker (Redis local + app):
docker-compose up --build

# Без Docker:
pip install -r requirements.txt
# Терминал 1:
uvicorn app.main:app --reload --port 8000
# Терминал 2:
rq worker --url redis://localhost:6379/0 default
```

## Настройка

| Переменная | Описание | Default |
|------------|----------|---------|
| `DATABASE_URL` | Supabase PostgreSQL | — |
| `REDIS_URL` | Redis connection | `redis://localhost:6379/0` |
| `OPENAI_API_KEY` | OpenAI API key | — |
| `TRANSCRIBE_MODEL` | Модель транскрипции | `gpt-4o-transcribe` |
| `SUMMARY_MODEL` | Модель саммари | `gpt-4o-mini` |
| `MAX_UPLOAD_MB` | Макс. размер файла | `250` |
| `MAX_AUDIO_CHUNK_SECONDS` | Макс. длина чанка аудио (сек) | `1300` |
| `UPLOAD_BLOB_TTL_SECONDS` | TTL upload-блоба в Redis (сек) | `3600` |
| `YTDLP_COOKIES_PATH` | Путь к cookies.txt для yt-dlp | `""` |
| `YTDLP_COOKIES_B64` | base64-содержимое cookies.txt | `""` |
| `YTDLP_PLAYER_CLIENT` | youtube player_client для yt-dlp | `android` |
| `YTDLP_FALLBACK_CLIENTS` | fallback цепочка клиентов yt-dlp | `android,web,ios` |
| `MAX_AUDIO_CHUNK_MB` | Макс. размер чанка для OpenAI | `24` |
| `JOB_TIMEOUT` | Таймаут задачи (сек) | `1800` |
| `CALLBACK_TIMEOUT_SECONDS` | Таймаут webhook callback (сек) | `10` |
| `CALLBACK_RETRIES` | Количество повторов callback | `2` |
| `AUTH_RATE_LIMIT_PER_MINUTE` | Лимит auth-запросов/мин/IP | `20` |
| `JOB_SUBMIT_RATE_LIMIT_PER_MINUTE` | Лимит submit/retry/мин/IP | `30` |
| `JOB_MAX_RETRIES` | Авто-retry задач в RQ | `2` |
| `JOB_RETENTION_HOURS` | Хранение done/error задач (часы) | `168` |
| `RETENTION_CLEANUP_INTERVAL_SECONDS` | Интервал cleanup в worker (сек) | `1800` |
| `RETENTION_CLEANUP_BATCH_SIZE` | Размер batch удаления старых задач | `200` |

## Тесты

```bash
pytest tests/ -v
```

## Disclaimer

> Этот сервис предназначен **исключительно для личного использования**.
> Пользователь несёт ответственность за соблюдение авторских прав и условий использования контента.
> Медиа-файлы автоматически удаляются после обработки.

## Лицензия

MIT
