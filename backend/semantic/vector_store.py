"""VectorStore abstraction + FAISS default (numpy fallback)."""

from __future__ import annotations

import json
import pickle
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

import numpy as np

from backend.config import settings
from backend.core.logger import get_logger
from backend.semantic.exceptions import VectorStoreError
from backend.semantic.models import SemanticDocument, SemanticSearchResult

logger = get_logger(__name__)


class VectorStore(ABC):
    """Pluggable vector index (FAISS today; Chroma/Qdrant/Pinecone later)."""

    name: str = "base"

    @abstractmethod
    def upsert(self, registry_id: str, vector: np.ndarray, document: SemanticDocument) -> None:
        ...

    @abstractmethod
    def search(
        self,
        query_vector: np.ndarray,
        *,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[SemanticSearchResult]:
        ...

    @abstractmethod
    def delete(self, registry_id: str) -> bool:
        ...

    @abstractmethod
    def contains(self, registry_id: str) -> bool:
        ...

    @abstractmethod
    def save(self) -> None:
        ...

    @abstractmethod
    def load(self) -> None:
        ...


def _l2_normalize(vec: np.ndarray) -> np.ndarray:
    v = np.asarray(vec, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(v))
    if norm > 0:
        v = v / norm
    return v


class NumpyVectorStore(VectorStore):
    """Cosine search with pickle persistence (tests + FAISS-less environments)."""

    name = "numpy"

    def __init__(self, path: str | Path, dimension: int = 384):
        self.path = Path(path)
        self.dimension = dimension
        self._ids: list[str] = []
        self._vectors: Optional[np.ndarray] = None
        self._docs: dict[str, dict[str, Any]] = {}
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def upsert(self, registry_id: str, vector: np.ndarray, document: SemanticDocument) -> None:
        vec = _l2_normalize(vector)
        if self._ids and vec.shape[0] != self.dimension:
            raise VectorStoreError(f"Vector dim {vec.shape[0]} != store dim {self.dimension}")
        if not self._ids:
            self.dimension = int(vec.shape[0])

        if registry_id in self._docs and registry_id in self._ids:
            idx = self._ids.index(registry_id)
            assert self._vectors is not None
            self._vectors[idx] = vec
        else:
            self._ids.append(registry_id)
            if self._vectors is None:
                self._vectors = vec.reshape(1, -1)
            else:
                self._vectors = np.vstack([self._vectors, vec.reshape(1, -1)])
        self._docs[registry_id] = document.to_dict()

    def search(
        self,
        query_vector: np.ndarray,
        *,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[SemanticSearchResult]:
        if not self._ids or self._vectors is None:
            return []
        q = _l2_normalize(query_vector)
        scores = self._vectors @ q
        order = np.argsort(-scores)
        results: list[SemanticSearchResult] = []
        for i in order[: max(1, top_k)]:
            score = float(scores[i])
            if score < min_score:
                continue
            rid = self._ids[int(i)]
            doc = self._docs.get(rid) or {}
            results.append(
                SemanticSearchResult(
                    registry_id=rid,
                    similarity_score=score,
                    metadata=doc.get("metadata") or {
                        k: v for k, v in doc.items() if k != "text"
                    },
                )
            )
        return results

    def delete(self, registry_id: str) -> bool:
        if registry_id not in self._docs:
            return False
        if registry_id in self._ids and self._vectors is not None:
            idx = self._ids.index(registry_id)
            self._ids.pop(idx)
            self._vectors = np.delete(self._vectors, idx, axis=0)
            if self._vectors.size == 0:
                self._vectors = None
        self._docs.pop(registry_id, None)
        return True

    def contains(self, registry_id: str) -> bool:
        return registry_id in self._docs

    def save(self) -> None:
        payload = {
            "dimension": self.dimension,
            "ids": self._ids,
            "docs": self._docs,
            "vectors": None if self._vectors is None else self._vectors.astype(np.float32),
        }
        with self.path.open("wb") as f:
            pickle.dump(payload, f)

    def load(self) -> None:
        if not self.path.is_file():
            return
        try:
            with self.path.open("rb") as f:
                payload = pickle.load(f)
            self.dimension = int(payload.get("dimension") or self.dimension)
            self._ids = list(payload.get("ids") or [])
            self._docs = dict(payload.get("docs") or {})
            vectors = payload.get("vectors")
            self._vectors = (
                np.asarray(vectors, dtype=np.float32) if vectors is not None else None
            )
        except Exception as exc:
            raise VectorStoreError(f"Failed to load numpy store: {exc}") from exc


class FAISSVectorStore(VectorStore):
    """FAISS IndexFlatIP + sidecar metadata; keeps matrix for update/delete."""

    name = "faiss"

    def __init__(self, path: str | Path, dimension: int = 384):
        self.path = Path(path)
        self.dimension = dimension
        self._ids: list[str] = []
        self._docs: dict[str, dict[str, Any]] = {}
        self._matrix: Optional[np.ndarray] = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._meta_path = Path(str(self.path) + ".meta.json")
        try:
            import faiss  # type: ignore

            self._faiss = faiss
            self._index = faiss.IndexFlatIP(self.dimension)
        except Exception as exc:
            raise VectorStoreError(f"FAISS unavailable: {exc}") from exc

    def _rebuild_index(self) -> None:
        self._index = self._faiss.IndexFlatIP(self.dimension)
        if self._matrix is not None and len(self._ids) > 0:
            self._index.add(self._matrix.astype(np.float32))

    def upsert(self, registry_id: str, vector: np.ndarray, document: SemanticDocument) -> None:
        vec = _l2_normalize(vector).astype(np.float32)
        if self._ids and vec.shape[0] != self.dimension:
            raise VectorStoreError(f"Vector dim {vec.shape[0]} != store dim {self.dimension}")
        if not self._ids:
            self.dimension = int(vec.shape[0])
            self._index = self._faiss.IndexFlatIP(self.dimension)

        doc_dict = document.to_dict()
        if registry_id in self._docs and registry_id in self._ids:
            idx = self._ids.index(registry_id)
            assert self._matrix is not None
            self._matrix[idx] = vec
            self._docs[registry_id] = doc_dict
            self._rebuild_index()
            return

        self._ids.append(registry_id)
        self._docs[registry_id] = doc_dict
        if self._matrix is None:
            self._matrix = vec.reshape(1, -1)
        else:
            self._matrix = np.vstack([self._matrix, vec.reshape(1, -1)])
        self._rebuild_index()

    def search(
        self,
        query_vector: np.ndarray,
        *,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[SemanticSearchResult]:
        if not self._ids or self._matrix is None or self._index.ntotal == 0:
            return []
        q = _l2_normalize(query_vector).astype(np.float32).reshape(1, -1)
        k = min(max(1, top_k), len(self._ids))
        scores, indices = self._index.search(q, k)
        results: list[SemanticSearchResult] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self._ids):
                continue
            s = float(score)
            if s < min_score:
                continue
            rid = self._ids[int(idx)]
            doc = self._docs.get(rid) or {}
            results.append(
                SemanticSearchResult(
                    registry_id=rid,
                    similarity_score=s,
                    metadata=doc.get("metadata")
                    or {k: v for k, v in doc.items() if k not in {"text"}},
                )
            )
        return results

    def delete(self, registry_id: str) -> bool:
        if registry_id not in self._docs:
            return False
        if registry_id not in self._ids or self._matrix is None:
            self._docs.pop(registry_id, None)
            return True
        idx = self._ids.index(registry_id)
        self._ids.pop(idx)
        self._matrix = np.delete(self._matrix, idx, axis=0)
        if self._matrix.size == 0:
            self._matrix = None
        self._docs.pop(registry_id, None)
        self._rebuild_index()
        return True

    def contains(self, registry_id: str) -> bool:
        return registry_id in self._docs

    def save(self) -> None:
        try:
            self._faiss.write_index(self._index, str(self.path))
            meta = {
                "dimension": self.dimension,
                "ids": self._ids,
                "docs": self._docs,
                "matrix": None if self._matrix is None else self._matrix.tolist(),
            }
            self._meta_path.write_text(json.dumps(meta), encoding="utf-8")
        except Exception as exc:
            raise VectorStoreError(f"Failed to save FAISS store: {exc}") from exc

    def load(self) -> None:
        if self._meta_path.is_file():
            try:
                meta = json.loads(self._meta_path.read_text(encoding="utf-8"))
                self.dimension = int(meta.get("dimension") or self.dimension)
                self._ids = list(meta.get("ids") or [])
                self._docs = dict(meta.get("docs") or {})
                matrix = meta.get("matrix")
                self._matrix = (
                    np.asarray(matrix, dtype=np.float32) if matrix is not None else None
                )
                self._rebuild_index()
                return
            except Exception as exc:
                logger.warning("FAISS meta load failed", extra={"error": str(exc)})
        if self.path.is_file():
            try:
                self._index = self._faiss.read_index(str(self.path))
            except Exception as exc:
                raise VectorStoreError(f"Failed to load FAISS index: {exc}") from exc


def default_vector_store_path() -> Path:
    return Path(settings.DATA_DIR) / "semantic" / "dataset_index"


def create_default_vector_store(dimension: int = 384) -> VectorStore:
    """Prefer FAISS; fall back to numpy cosine store."""
    path = default_vector_store_path()
    try:
        store = FAISSVectorStore(path.with_suffix(".faiss"), dimension=dimension)
        try:
            store.load()
        except Exception:
            pass
        logger.info("Using FAISS vector store", extra={"path": str(path)})
        return store
    except Exception as exc:
        logger.warning(
            "FAISS not available; using NumpyVectorStore",
            extra={"error": str(exc)},
        )
        store = NumpyVectorStore(path.with_suffix(".npy.pkl"), dimension=dimension)
        try:
            store.load()
        except Exception:
            pass
        return store
