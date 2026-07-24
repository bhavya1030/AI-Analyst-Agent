"""Local filesystem implementation of DatasetStorage."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import BinaryIO, Optional

from backend.core.logger import get_logger
from backend.dataset_library.exceptions import (
    DatasetFileNotFoundError,
    DatasetLibraryValidationError,
)
from backend.dataset_library.models import LibraryFileMetadata
from backend.dataset_library.storage.base import DatasetStorage, SourceData

logger = get_logger(__name__)

INDEX_FILENAME = "_index.json"
METADATA_FILENAME = "metadata.json"


class LocalFilesystemStorage(DatasetStorage):
    """
    Layout under root:

        {root}/
          {source_slug}/
            {topic_slug}/
              {dataset_id}/
                dataset.csv
                metadata.json
          _index.json   # dataset_id -> relative_dir
    """

    def __init__(self, root_dir: str | Path):
        self.root = Path(root_dir).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._index_path = self.root / INDEX_FILENAME

    # ------------------------------------------------------------------
    # DatasetStorage API
    # ------------------------------------------------------------------

    def save(
        self,
        *,
        dataset_id: str,
        data: SourceData,
        relative_dir: str,
        data_filename: str,
        metadata: LibraryFileMetadata,
    ) -> str:
        if self.exists(dataset_id):
            raise DatasetLibraryValidationError(
                f"Dataset already exists: {dataset_id}. Use replace_dataset()."
            )
        return self._write(dataset_id, data, relative_dir, data_filename, metadata)

    def exists(self, dataset_id: str) -> bool:
        path = self.get_path(dataset_id)
        return bool(path and Path(path).is_file())

    def get_path(self, dataset_id: str) -> Optional[str]:
        meta = self.get_metadata(dataset_id)
        if meta is None:
            return None
        rel = meta.relative_dir or self._index().get(dataset_id)
        if not rel:
            return None
        data_path = self.root / rel / (meta.data_filename or "dataset.csv")
        return str(data_path) if data_path.is_file() else None

    def get_metadata(self, dataset_id: str) -> Optional[LibraryFileMetadata]:
        rel = self._index().get(dataset_id)
        if not rel:
            # Fallback scan (repairs missing index)
            rel = self._scan_for_dataset(dataset_id)
            if not rel:
                return None
            self._index_set(dataset_id, rel)

        meta_path = self.root / rel / METADATA_FILENAME
        if not meta_path.is_file():
            return None
        try:
            payload = json.loads(meta_path.read_text(encoding="utf-8"))
            meta = LibraryFileMetadata.from_dict(payload)
            if not meta.relative_dir:
                meta.relative_dir = rel
            return meta
        except Exception as exc:
            logger.warning(
                "Failed to read library metadata",
                extra={"dataset_id": dataset_id, "error": str(exc)},
            )
            return None

    def delete(self, dataset_id: str) -> bool:
        rel = self._index().get(dataset_id) or self._scan_for_dataset(dataset_id)
        if not rel:
            return False
        target = self.root / rel
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        self._index_pop(dataset_id)
        # Prune empty parents (topic / source) but never the root
        self._prune_empty_parents(target.parent)
        return True

    def replace(
        self,
        *,
        dataset_id: str,
        data: SourceData,
        relative_dir: str,
        data_filename: str,
        metadata: LibraryFileMetadata,
    ) -> str:
        # Remove previous directory if path changed
        old_rel = self._index().get(dataset_id)
        if old_rel and old_rel != relative_dir:
            old_dir = self.root / old_rel
            if old_dir.is_dir():
                shutil.rmtree(old_dir, ignore_errors=True)
        return self._write(dataset_id, data, relative_dir, data_filename, metadata)

    def read_bytes(self, dataset_id: str) -> bytes:
        path = self.get_path(dataset_id)
        if not path:
            raise DatasetFileNotFoundError(dataset_id)
        return Path(path).read_bytes()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _write(
        self,
        dataset_id: str,
        data: SourceData,
        relative_dir: str,
        data_filename: str,
        metadata: LibraryFileMetadata,
    ) -> str:
        relative_dir = relative_dir.replace("\\", "/").strip("/")
        if not relative_dir or ".." in relative_dir.split("/"):
            raise DatasetLibraryValidationError("Invalid relative_dir")

        dest_dir = self.root / relative_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        data_path = dest_dir / data_filename

        raw = _coerce_bytes(data)
        data_path.write_bytes(raw)

        metadata.relative_dir = relative_dir
        metadata.data_filename = data_filename
        meta_path = dest_dir / METADATA_FILENAME
        meta_path.write_text(
            json.dumps(metadata.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        self._index_set(dataset_id, relative_dir)
        logger.info(
            "Dataset library wrote files",
            extra={"dataset_id": dataset_id, "path": str(data_path)},
        )
        return str(data_path.resolve())

    def _index(self) -> dict[str, str]:
        if not self._index_path.is_file():
            return {}
        try:
            data = json.loads(self._index_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _index_set(self, dataset_id: str, relative_dir: str) -> None:
        index = self._index()
        index[dataset_id] = relative_dir.replace("\\", "/")
        self._index_path.write_text(
            json.dumps(index, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _index_pop(self, dataset_id: str) -> None:
        index = self._index()
        if dataset_id in index:
            index.pop(dataset_id, None)
            self._index_path.write_text(
                json.dumps(index, indent=2, sort_keys=True),
                encoding="utf-8",
            )

    def _scan_for_dataset(self, dataset_id: str) -> Optional[str]:
        for meta_path in self.root.rglob(METADATA_FILENAME):
            try:
                payload = json.loads(meta_path.read_text(encoding="utf-8"))
                if payload.get("dataset_id") == dataset_id:
                    rel = meta_path.parent.relative_to(self.root).as_posix()
                    return rel
            except Exception:
                continue
        return None

    def _prune_empty_parents(self, start: Path) -> None:
        current = start
        try:
            while current != self.root and self.root in current.parents:
                if current.is_dir() and not any(current.iterdir()):
                    current.rmdir()
                    current = current.parent
                else:
                    break
        except Exception:
            pass


def _coerce_bytes(data: SourceData) -> bytes:
    if isinstance(data, (bytes, bytearray, memoryview)):
        return bytes(data)
    if isinstance(data, str):
        path = Path(data)
        if not path.is_file():
            raise DatasetLibraryValidationError(f"Source path is not a file: {data}")
        return path.read_bytes()
    # file-like
    if hasattr(data, "read"):
        chunk = data.read()
        if isinstance(chunk, str):
            return chunk.encode("utf-8")
        return bytes(chunk)
    raise DatasetLibraryValidationError("Unsupported data source type for save")
