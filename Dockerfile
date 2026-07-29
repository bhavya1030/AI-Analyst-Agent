# =============================================================================
# AI Analyst Agent — Backend API image (FastAPI + LangGraph)
# Build context: repository root (where requirements.txt and backend/ live)
# Does NOT include Ollama, Next.js UI, or docker-compose.
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: build wheels / install Python deps (compilers discarded later)
# -----------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Native toolchain required to compile Prophet / some scientific wheels when
# prebuilt wheels are unavailable. Not present in the final image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        g++ \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .

# Project requirements + scikit-learn (used by forecasting_agent fallback but
# not listed in requirements.txt). torch arrives via sentence-transformers.
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && pip install "scikit-learn>=1.3,<2"

# -----------------------------------------------------------------------------
# Stage 2: runtime — no compilers, smaller attack surface
# -----------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Package root must be WORKDIR so "import backend" and BASE_DIR resolve
    PYTHONPATH=/app \
    PATH="/opt/venv/bin:$PATH" \
    # Absolute SQLite URL (four slashes after scheme for absolute path)
    DATABASE_URL=sqlite:////app/memory.db \
    DATA_DIR=/app/data \
    # LLM stays off inside this container; Ollama is external if ever used
    USE_LLM_INTENT=false \
    USE_LLM_PLANNER=false \
    USE_LLM_TOPIC=false \
    USE_LLM_LEARN=false \
    # Hugging Face / ST model cache on the persistent volume path
    HF_HOME=/app/data/.cache/huggingface \
    TRANSFORMERS_CACHE=/app/data/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/app/data/.cache/sentence-transformers \
    # Prophet / cmdstan write under home when first forecast runs
    HOME=/home/appuser

WORKDIR /app

# Runtime shared libs for numpy/torch OpenMP; curl only if you healthcheck via it
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgomp1 \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid appuser --create-home --shell /bin/bash appuser

COPY --from=builder /opt/venv /opt/venv

# Application package only (not tests, venv, UI, or sample bulk data)
COPY backend/ ./backend/

# Directories required by config.py + dataset_library + semantic store + uploads
# data/           -> settings.DATA_DIR (uploads, library root)
# data/datasets/  -> LocalFilesystemStorage library
# data/semantic/  -> vector index persistence
# data/.cache/    -> sentence-transformers / HF downloads at runtime
RUN mkdir -p \
        /app/data/datasets \
        /app/data/semantic \
        /app/data/.cache/huggingface \
        /app/data/.cache/sentence-transformers \
        /home/appuser \
    && touch /app/memory.db \
    && chown -R appuser:appuser /app /home/appuser

USER appuser

EXPOSE 8000

# Single worker: SQLite + in-process caches + graph state are process-local.
# Correct module path for this monorepo: backend.main:app (NOT main:app).
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
