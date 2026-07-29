# Deployment Guide — AI Analyst Agent

This guide walks you through deploying the Analytics Copilot stack with Docker for the first time.

**Stack**

| Service | Image / Dockerfile | Default host port |
|---------|------------------|-------------------|
| Backend (FastAPI + LangGraph) | Root `Dockerfile` | `8000` |
| Frontend (Next.js 14) | `analytics-copilot-ui/Dockerfile` | `3000` |
| Ollama (optional) | `ollama/ollama` via Compose profile `ollama` | `11434` |

**Artifacts used**

- `Dockerfile` (backend)
- `analytics-copilot-ui/Dockerfile` (frontend)
- `docker-compose.yml`
- `.env.example`

Ollama is **not required**. Default configuration uses rule-based intent/planning and runs without a local LLM.

---

## 1. Project prerequisites

Install on the host machine:

| Requirement | Notes |
|-------------|--------|
| Docker Engine | 24+ recommended |
| Docker Compose | v2 (`docker compose`) |
| Git | Clone the repository |
| Disk | **20 GB+ free** (backend image includes scientific stack; first embedding download adds more) |
| RAM | **8 GB minimum**; **16 GB recommended** if you enable the Ollama profile |
| Network | Outbound HTTPS for open-data downloads and (first-time) model cache |

**Not required for default deploy**

- Local Python / Node installs
- Ollama on the host
- PostgreSQL, Redis, or MongoDB
- OpenAI / Gemini API keys (not used by the application)

---

## 2. Clone repository

```bash
git clone <YOUR_REPOSITORY_URL> AI-Analyst-Agent
cd AI-Analyst-Agent
```

Confirm these files exist at the repo root:

```text
Dockerfile
docker-compose.yml
.env.example
backend/
analytics-copilot-ui/Dockerfile
requirements.txt
```

---

## 3. Configure `.env`

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

### Minimum recommended values for Docker Compose

Edit `.env` so persistence and the UI API URL match Compose:

```env
# Backend (inside containers)
DATABASE_URL=sqlite:////app/data/memory.db
DATA_DIR=/app/data
LOG_LEVEL=INFO

# Keep LLM off unless you start the ollama profile and want LLM features
USE_LLM_INTENT=false
USE_LLM_PLANNER=false
USE_LLM_TOPIC=false
USE_LLM_LEARN=false
LEARN_DATASETS=true

# Used only if LLM flags are true and ollama profile is running
OLLAMA_SERVER_URL=http://ollama:11434
OLLAMA_MODEL=qwen3:4b

# Frontend (baked into the Next.js client at BUILD time)
# Browser must reach the backend on the host — use localhost for local deploy
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Optional host port overrides (read by Compose, not by app `Settings`):

```env
BACKEND_HOST_PORT=8000
FRONTEND_HOST_PORT=3000
```

**Important**

- `NEXT_PUBLIC_API_URL` is inlined when the frontend image is **built**. Changing it later requires a frontend rebuild.
- Do not set `NEXT_PUBLIC_API_URL=http://backend:8000` for browser access; that hostname only resolves inside the Docker network.
- The application does not require API secrets for the default path.

Full variable list and descriptions: see `.env.example`.

---

## 4. Build Docker images

From the repository root:

```bash
docker compose build
```

Force a clean rebuild:

```bash
docker compose build --no-cache
```

Rebuild only one service:

```bash
docker compose build backend
docker compose build frontend
```

If you change `NEXT_PUBLIC_API_URL`, always rebuild the frontend:

```bash
# Linux / macOS
export NEXT_PUBLIC_API_URL=http://localhost:8000
docker compose build frontend

# Windows PowerShell
$env:NEXT_PUBLIC_API_URL = "http://localhost:8000"
docker compose build frontend
```

First backend build can take a long time (Prophet, sentence-transformers, PyTorch).

---

## 5. Start Docker Compose

### Default (backend + frontend, no Ollama)

```bash
docker compose up -d
```

### With optional Ollama

```bash
docker compose --profile ollama up -d
```

Pull the model configured in `.env` (example `qwen3:4b`):

```bash
docker compose --profile ollama exec ollama ollama pull qwen3:4b
```

To use Ollama for intent/planner/topic, set the corresponding flags to `true` in `.env`, then recreate the backend:

```bash
docker compose --profile ollama up -d --force-recreate backend
```

### Foreground (logs in terminal)

```bash
docker compose up
```

Stop with `Ctrl+C`, then run `docker compose down` if containers remain.

---

## 6. Verify services

```bash
docker compose ps
```

Expected: `backend` and `frontend` are **Up** and **healthy** (healthchecks may take 1–2 minutes on first start).

```bash
# Backend root
curl http://localhost:8000/

# Frontend
curl -I http://localhost:3000/
```

Windows PowerShell:

```powershell
Invoke-WebRequest -Uri http://localhost:8000/ -UseBasicParsing
Invoke-WebRequest -Uri http://localhost:3000/ -UseBasicParsing
```

---

## 7. Access frontend

Open in a browser:

```text
http://localhost:3000
```

If you set `FRONTEND_HOST_PORT` in the environment / Compose, use that port instead.

You should see the Analytics Copilot UI (chat, upload, response panels).

---

## 8. Access backend

| Resource | URL |
|----------|-----|
| API root | http://localhost:8000/ |
| OpenAPI docs (Swagger) | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |

Primary analysis endpoint:

```text
GET http://localhost:8000/v1/ask?question=...&session_id=...
```

---

## 9. Health endpoints

```bash
# Lightweight LLM/Ollama status (Ollama may be unavailable — that is OK)
curl http://localhost:8000/health/llm

# Database + LangGraph + Ollama summary
curl http://localhost:8000/health/full
```

**Healthy default deploy (no Ollama)**

- `database`: `ok`
- `langgraph`: `ok`
- `ollama.ollama_running`: `false` or similar failure fields — expected
- API still serves analysis via the rule-based path

Optional inference probe (only if Ollama is up and the model is pulled):

```bash
curl "http://localhost:8000/health/llm?test_inference=true"
```

---

## 10. Upload dataset test

### Option A — UI

1. Open http://localhost:3000  
2. Use the upload dropzone to upload a CSV (for example `data/employees.csv` from the repo if present on the host)  
3. Ask a question such as: `Summarize this dataset` or `Show a chart of the main numeric columns`  
4. Confirm a response appears and charts/suggestions populate when data loads  

### Option B — API

```bash
# Upload
curl -X POST http://localhost:8000/upload \
  -F "file=@./data/employees.csv"

# Note the returned file_path, then ask
curl "http://localhost:8000/v1/ask?session_id=deploy-test&question=Describe%20this%20dataset&file_path=<FILE_PATH_FROM_UPLOAD>"
```

### Option C — open-data question (no upload)

```bash
curl "http://localhost:8000/v1/ask?session_id=deploy-test&question=Analyze%20India%20GDP"
```

This path may take longer (network download + analysis). Outbound HTTPS from the backend container must work.

---

## 11. Common deployment issues

| Symptom | Likely cause | What to do |
|---------|--------------|------------|
| Frontend loads but every ask fails | Wrong `NEXT_PUBLIC_API_URL` baked into UI image | Set URL, `docker compose build frontend`, recreate frontend |
| UI calls `http://backend:8000` and fails in browser | Internal Docker DNS used as public API URL | Use `http://localhost:8000` (or public hostname) for `NEXT_PUBLIC_API_URL` |
| Backend unhealthy / restarting | First import slow or OOM | Check logs; free RAM; wait through `start_period`; increase Docker memory |
| `sqlite` / permission errors on volume | Volume ownership vs `appuser` (uid 1000) | Prefer named volumes from Compose; avoid root-only bind mounts |
| Empty sessions after restart | Volume removed with `-v` or different project name | Avoid `down -v` unless intentional; keep `backend_data` volume |
| Forecast fails | Prophet/CmdStan first-time setup or missing sklearn path | Check backend logs; regression fallback may apply; ensure image built from current `Dockerfile` |
| First semantic/search very slow | Downloading `all-MiniLM-L6-v2` | Wait once; cache persists under `/app/data/.cache` on volume |
| Open-data ask returns upload prompt | Source not found / network blocked | Check outbound network; try upload or a known topic (GDP, gold, etc.) |
| Port already allocated | Host 3000 or 8000 in use | Set `BACKEND_HOST_PORT` / `FRONTEND_HOST_PORT` and recreate |
| Ollama flags true but no answers from LLM | Profile not started or model not pulled | `docker compose --profile ollama up -d` and `ollama pull <model>` |
| Build fails on Prophet / wheels | Builder needs network and enough disk | Retry build; ensure Docker has 8 GB+ RAM for install |

---

## 12. Updating containers

After pulling new code:

```bash
git pull

# Rebuild changed images
docker compose build

# Recreate running services with new images
docker compose up -d
```

Frontend env URL change:

```bash
export NEXT_PUBLIC_API_URL=https://api.your-domain.com   # or set in .env for compose build args
docker compose build frontend
docker compose up -d frontend
```

Backend-only code change:

```bash
docker compose build backend
docker compose up -d backend
```

Named volumes (`backend_data`) are kept across rebuilds unless you delete them.

---

## 13. Viewing logs

```bash
# All services
docker compose logs -f

# Backend only
docker compose logs -f backend

# Frontend only
docker compose logs -f frontend

# Last 200 lines
docker compose logs --tail=200 backend

# Ollama (when profile is enabled)
docker compose --profile ollama logs -f ollama
```

---

## 14. Stopping containers

```bash
# Stop and remove containers/network; keep volumes
docker compose down

# If Ollama profile was used
docker compose --profile ollama down
```

Stop without removing containers:

```bash
docker compose stop
```

Start again later:

```bash
docker compose start
# or
docker compose up -d
```

---

## 15. Cleaning volumes

**Warning:** this deletes SQLite sessions, uploads, learned datasets, semantic index, and embedding cache.

```bash
# Stop stack and delete named volumes
docker compose down -v
```

Remove Ollama model volume as well (if used):

```bash
docker compose --profile ollama down -v
```

List volumes:

```bash
docker volume ls | grep ai_analyst
```

---

## 16. Backup SQLite database

With Compose defaults, the DB file is:

```text
/app/data/memory.db
```

on volume `ai_analyst_backend_data` (or `BACKEND_DATA_VOLUME` if overridden).

### Backup while stack is running

```bash
# Copy DB out of the backend container
docker compose exec backend python -c "import shutil; shutil.copy('/app/data/memory.db', '/app/data/memory.db.bak')"

docker cp ai-analyst-backend:/app/data/memory.db ./memory-backup-$(date +%Y%m%d).db
```

Windows PowerShell:

```powershell
docker cp ai-analyst-backend:/app/data/memory.db ".\memory-backup-$(Get-Date -Format yyyyMMdd).db"
```

### Backup full data volume (DB + uploads + library + cache)

```bash
docker run --rm `
  -v ai_analyst_backend_data:/data `
  -v ${PWD}:/backup `
  alpine tar czf /backup/ai-analyst-data-backup.tgz -C /data .
```

### Restore

1. `docker compose down`  
2. Restore file into the volume or `docker cp` into a running container at `/app/data/memory.db`  
3. `docker compose up -d`  
4. Verify: `curl http://localhost:8000/health/full` and `curl http://localhost:8000/sessions`  

Prefer stopping write traffic (or the backend) before large restores.

---

## 17. Production deployment recommendations

1. **Single host with Docker Compose** matches this codebase (SQLite + local filesystem library). Prefer a VM with a persistent disk.
2. **Do not** run multiple backend replicas against one SQLite file.
3. Keep **one worker** (image already uses `--workers 1`).
4. Put TLS in front with a reverse proxy (Caddy, Nginx, Traefik, or cloud LB) for HTTPS.
5. Set production UI API URL and rebuild frontend:
   ```text
   NEXT_PUBLIC_API_URL=https://api.your-domain.com
   ```
6. Point `DATABASE_URL` and `DATA_DIR` at durable storage (Compose named volume or attached disk).
7. Schedule backups of `/app/data` (at least `memory.db` and `datasets/`).
8. Leave `USE_LLM_*=false` unless you deliberately run and size the Ollama profile (extra RAM/CPU).
9. Ensure the host can open outbound HTTPS (open-data retrieval, embedding model download).
10. Resource sizing guide:
    - Without Ollama: ~4 vCPU, 8 GB RAM, 40 GB disk  
    - With Ollama 4B-class model: ~4+ vCPU, 16 GB RAM, 60+ GB disk  
11. Monitor `/health/full` from your uptime checks.
12. Do not use ephemeral free tiers without persistent volumes — you will lose sessions and uploads.

This project does **not** require Redis, PostgreSQL, or MongoDB for the current implementation.

---

## 18. Security recommendations

1. **TLS** — Terminate HTTPS at a reverse proxy; do not expose raw HTTP on the public internet long term.
2. **CORS** — Backend currently allows `allow_origins=["*"]`. For production, restrict to your frontend origin (code change in `backend/main.py`).
3. **Secrets** — Default path needs no API keys. Do not commit real `.env` files if you later add credentials.
4. **Network exposure** — Publish only ports 80/443 publicly; keep Ollama (`11434`) off the public internet.
5. **Non-root** — Backend and frontend images run as non-root users; keep that.
6. **Uploads** — Treat uploaded files as untrusted; limit max size at the proxy if needed (app writes under `DATA_DIR`).
7. **Updates** — Rebuild images regularly for base image and dependency security patches.
8. **Access control** — The API has no built-in auth. Place it behind VPN, SSO proxy, or network policy for private deployments.
9. **LLM flags** — Keep `USE_LLM_*=false` unless Ollama is intentionally enabled and locked to the internal network.
10. **Backups** — Encrypt backup archives if they contain sensitive business datasets.

---

## Quick reference

```bash
# First-time deploy
cp .env.example .env
# edit .env (Docker DATABASE_URL / DATA_DIR / NEXT_PUBLIC_API_URL)
docker compose build
docker compose up -d
docker compose ps
curl http://localhost:8000/health/full
# open http://localhost:3000

# Logs / stop / wipe data
docker compose logs -f backend
docker compose down
docker compose down -v
```

| URL | Purpose |
|-----|---------|
| http://localhost:3000 | Frontend |
| http://localhost:8000 | Backend API |
| http://localhost:8000/docs | Swagger UI |
| http://localhost:8000/health/full | Health check |

---

## Related files

| File | Role |
|------|------|
| `Dockerfile` | Backend multi-stage image (`uvicorn backend.main:app`) |
| `analytics-copilot-ui/Dockerfile` | Frontend standalone Next.js image |
| `docker-compose.yml` | Backend, frontend, optional `ollama` profile, volumes, healthchecks |
| `.env.example` | Application environment variables only |
| `README.md` | Project overview and local (non-Docker) development notes |
