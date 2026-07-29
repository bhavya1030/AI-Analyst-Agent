"""Hugging Face datasets provider — only direct file URLs (no landing pages)."""

from __future__ import annotations

from backend.retrieval.data_providers.base import DataProvider, DatasetCandidate

# Curated HF resolve URLs that return files
_HF_FILES = [
    {
        "keys": {"imdb", "sentiment"},
        "title": "IMDB reviews sample (HF resolve)",
        "url": (
            "https://huggingface.co/datasets/imdb/resolve/main/plain_text/train-00000-of-00001.parquet"
        ),
        "format": "parquet",
        "rank": 40,
    },
]


class HuggingFaceProvider(DataProvider):
    name = "huggingface"
    priority = 60

    def supports(self, topic: str, keywords: list[str]) -> bool:
        blob = f"{topic} {' '.join(keywords)}".lower()
        return "hugging" in blob or "hf" in keywords or any(
            any(k in blob for k in item["keys"]) for item in _HF_FILES
        )

    def search(self, topic: str, keywords: list[str], *, limit: int = 5) -> list[DatasetCandidate]:
        blob = f"{topic} {' '.join(keywords)}".lower()
        out: list[DatasetCandidate] = []
        for item in _HF_FILES:
            if not any(k in blob for k in item["keys"]):
                continue
            out.append(
                DatasetCandidate(
                    title=item["title"],
                    topic=topic,
                    download_url=item["url"],
                    provider=self.name,
                    source_url=item["url"],
                    license="upstream dataset license",
                    dataset_version="hf-resolve",
                    file_format=item["format"],
                    description="Direct Hugging Face resolve URL (file, not landing page).",
                    tags=["huggingface", item["format"]],
                    rank=item["rank"],
                    extra={"source_type": "HuggingFace"},
                )
            )
        return out[:limit]
