"""Kaggle provider — metadata only (no authenticated download)."""

from __future__ import annotations

from backend.retrieval.data_providers.base import DataProvider, DatasetCandidate


class KaggleProvider(DataProvider):
    """
    Surfaces dataset search metadata for operators.

    Does not return download_url that can be fetched without Kaggle API credentials.
    Orchestrator will skip candidates without downloadable URLs.
    """

    name = "kaggle"
    priority = 40

    def supports(self, topic: str, keywords: list[str]) -> bool:
        blob = f"{topic} {' '.join(keywords)}".lower()
        return "kaggle" in blob

    def search(self, topic: str, keywords: list[str], *, limit: int = 5) -> list[DatasetCandidate]:
        # Metadata-only stub: no anonymous download URL
        q = "+".join(keywords[:5]) or topic.replace(" ", "+")
        return [
            DatasetCandidate(
                title=f"Kaggle search: {topic}",
                topic=topic,
                download_url="",  # intentionally empty — metadata only
                provider=self.name,
                source_url=f"https://www.kaggle.com/search?q={q}",
                license="Kaggle dataset terms (varies)",
                dataset_version=None,
                file_format="unknown",
                description=(
                    "Kaggle requires API credentials for dataset download. "
                    "Use Kaggle CLI or paste a direct file URL."
                ),
                tags=["kaggle", "metadata_only"],
                rank=10,
                extra={"source_type": "Kaggle", "metadata_only": True},
            )
        ][:limit]
