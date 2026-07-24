"""Hugging Face Datasets API search (landing + resolve preference)."""

from __future__ import annotations

from urllib.parse import quote_plus

from backend.retrieval.sources.base import DataSource, SourceCandidate
from backend.retrieval.sources.common import http_get_json, score_text


class HuggingFaceSource(DataSource):
    name = "huggingface"
    source_type = "HuggingFace"

    def search(self, topic: str, *, limit: int = 5) -> list[SourceCandidate]:
        if not (topic or "").strip():
            return []

        url = f"https://huggingface.co/api/datasets?search={quote_plus(topic)}&limit={min(limit, 10)}"
        payload = http_get_json(url)
        if not isinstance(payload, list):
            return []

        hits: list[SourceCandidate] = []
        for record in payload[:limit]:
            if not isinstance(record, dict):
                continue
            repo_id = record.get("id")
            if not repo_id:
                continue
            desc = ""
            card = record.get("cardData") or {}
            if isinstance(card, dict):
                desc = str(card.get("description") or "")[:300]
            if not desc:
                desc = str(record.get("description") or "")[:300]

            # Prefer a resolve URL pattern when a simple CSV name is common; else dataset page.
            # Retrieval does not download; engineer may resolve further later.
            landing = f"https://huggingface.co/datasets/{repo_id}"
            hits.append(
                SourceCandidate(
                    title=str(repo_id),
                    topic=topic,
                    download_url=landing,
                    source="Hugging Face",
                    source_type=self.source_type,
                    description=desc,
                    file_format="unknown",
                    tags=["huggingface", "dataset"],
                    rank_hint=5 + score_text(topic, repo_id, desc),
                    extra={"repo_id": repo_id, "landing_url": landing},
                )
            )

        hits.sort(key=lambda c: c.rank_hint, reverse=True)
        return hits[:limit]
