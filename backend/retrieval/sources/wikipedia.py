"""Wikipedia / Wikidata discovery for tabular-related topics (metadata + CSV export when possible)."""

from __future__ import annotations

from urllib.parse import quote

from backend.retrieval.sources.base import DataSource, SourceCandidate
from backend.retrieval.sources.common import http_get_json, score_text, topic_tokens


class WikipediaSource(DataSource):
    name = "wikipedia"
    source_type = "Web"

    def search(self, topic: str, *, limit: int = 5) -> list[SourceCandidate]:
        topic = (topic or "").strip()
        if not topic:
            return []

        # MediaWiki opensearch API
        payload = http_get_json(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "opensearch",
                "search": topic,
                "limit": min(limit, 5),
                "namespace": 0,
                "format": "json",
            },
        )
        hits: list[SourceCandidate] = []

        # opensearch returns [query, [titles], [descriptions], [urls]]
        if isinstance(payload, list) and len(payload) >= 4:
            titles = payload[1] or []
            descs = payload[2] or []
            urls = payload[3] or []
            for i, title in enumerate(titles[:limit]):
                page_url = urls[i] if i < len(urls) else f"https://en.wikipedia.org/wiki/{quote(str(title))}"
                desc = descs[i] if i < len(descs) else ""
                # Wikimedia offers special export endpoints; keep page URL as discovery lead.
                hits.append(
                    SourceCandidate(
                        title=str(title),
                        topic=topic,
                        download_url=page_url,
                        source="Wikipedia",
                        source_type=self.source_type,
                        description=str(desc)[:300],
                        file_format="unknown",
                        tags=["wikipedia"] + topic_tokens(topic)[:4],
                        rank_hint=4 + score_text(topic, title, desc),
                        extra={"page_url": page_url},
                    )
                )

        if not hits:
            # Fallback: direct wiki search URL
            hits.append(
                SourceCandidate(
                    title=f"Wikipedia: {topic}",
                    topic=topic,
                    download_url=f"https://en.wikipedia.org/w/index.php?search={quote(topic)}",
                    source="Wikipedia",
                    source_type=self.source_type,
                    description="Wikipedia search results page.",
                    file_format="unknown",
                    tags=["wikipedia", "search"],
                    rank_hint=1,
                )
            )

        hits.sort(key=lambda c: c.rank_hint, reverse=True)
        return hits[:limit]
