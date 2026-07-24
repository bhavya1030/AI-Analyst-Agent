"""EmbeddingGenerator abstraction + Sentence Transformers default."""

from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from typing import Sequence

import numpy as np

from backend.config import settings
from backend.core.logger import get_logger
from backend.semantic.exceptions import EmbeddingError

logger = get_logger(__name__)


class EmbeddingGenerator(ABC):
    """Pluggable text → vector encoder."""

    name: str = "base"
    dimension: int = 384

    @abstractmethod
    def embed(self, texts: Sequence[str]) -> np.ndarray:
        """Return float32 array shape (n, dimension), L2-normalized preferred."""
        ...

    def embed_one(self, text: str) -> np.ndarray:
        vectors = self.embed([text or ""])
        return vectors[0]


class HashingEmbeddingGenerator(EmbeddingGenerator):
    """Lightweight deterministic embedder for tests / offline fallback."""

    name = "hashing"

    def __init__(self, dimension: int = 384):
        self.dimension = int(dimension)

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        rows = []
        for text in texts:
            vec = np.zeros(self.dimension, dtype=np.float32)
            tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
            if not tokens:
                tokens = ["empty"]
            for tok in tokens:
                h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
                idx = h % self.dimension
                sign = 1.0 if (h // self.dimension) % 2 == 0 else -1.0
                vec[idx] += sign
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec /= norm
            rows.append(vec)
        return np.vstack(rows).astype(np.float32)


class SentenceTransformerEmbeddingGenerator(EmbeddingGenerator):
    """Default production embedder: sentence-transformers/all-MiniLM-L6-v2."""

    name = "sentence_transformers"

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or getattr(
            settings, "EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2"
        )
        self._model = None
        self.dimension = 384

    def _load(self):
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as exc:
            raise EmbeddingError(
                f"sentence-transformers not available: {exc}"
            ) from exc
        try:
            logger.info(
                "Loading sentence-transformer model",
                extra={"model": self.model_name},
            )
            self._model = SentenceTransformer(self.model_name)
            # Infer dimension
            try:
                self.dimension = int(self._model.get_sentence_embedding_dimension())
            except Exception:
                self.dimension = 384
            return self._model
        except Exception as exc:
            raise EmbeddingError(f"Failed to load embedding model: {exc}") from exc

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        model = self._load()
        cleaned = [t if (t or "").strip() else " " for t in texts]
        try:
            vectors = model.encode(
                cleaned,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            arr = np.asarray(vectors, dtype=np.float32)
            if arr.ndim == 1:
                arr = arr.reshape(1, -1)
            return arr
        except Exception as exc:
            raise EmbeddingError(f"Embedding failed: {exc}") from exc


def create_default_embedding_generator() -> EmbeddingGenerator:
    """Prefer SentenceTransformers; fall back to hashing if unavailable."""
    try:
        gen = SentenceTransformerEmbeddingGenerator()
        # Lazy load — don't force model download until first embed
        return gen
    except Exception:
        logger.warning("Using HashingEmbeddingGenerator fallback")
        return HashingEmbeddingGenerator()
