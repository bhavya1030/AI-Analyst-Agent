"""GitHub raw open datasets (curated raw URLs + topic map)."""

from __future__ import annotations

from backend.retrieval.sources.base import DataSource, SourceCandidate
from backend.retrieval.sources.common import guess_format, score_text, topic_tokens

# Trusted raw.githubusercontent.com resources
GITHUB_RAW = {
    "gdp": "https://raw.githubusercontent.com/datasets/gdp/master/data/gdp.csv",
    "population": "https://raw.githubusercontent.com/datasets/population/master/data/population.csv",
    "inflation": "https://raw.githubusercontent.com/datasets/inflation/master/data/cpi.csv",
    "unemployment": "https://raw.githubusercontent.com/datasets/unemployment/master/data/unemployment.csv",
    "gold": "https://raw.githubusercontent.com/datasets/gold-prices/master/data/annual.csv",
    "gold price": "https://raw.githubusercontent.com/datasets/gold-prices/master/data/annual.csv",
    "gold rate": "https://raw.githubusercontent.com/datasets/gold-prices/master/data/annual.csv",
    "co2": "https://raw.githubusercontent.com/datasets/co2-fossil-by-nation/master/global.csv",
    "climate": "https://raw.githubusercontent.com/datasets/global-temp/master/data/annual.csv",
    "temperature": "https://raw.githubusercontent.com/datasets/global-temp/master/data/annual.csv",
    "covid": "https://raw.githubusercontent.com/datasets/covid-19/master/data/countries-aggregated.csv",
    "stock": "https://raw.githubusercontent.com/datasets/s-and-p-500/master/data/data.csv",
}


class GitHubSource(DataSource):
    name = "github"
    source_type = "GitHub"

    def search(self, topic: str, *, limit: int = 5) -> list[SourceCandidate]:
        topic_l = (topic or "").lower()
        tokens = topic_tokens(topic)
        hits: list[SourceCandidate] = []

        for key, url in GITHUB_RAW.items():
            if key in topic_l or any(tok == key or tok in key.split() for tok in tokens):
                # Avoid weak single-token traps for generic keys when residual topic is rich
                key_parts = set(key.split())
                residual = [t for t in tokens if t not in key_parts]
                if residual and key in {"stock"} and len(residual) >= 2:
                    continue
                hits.append(
                    SourceCandidate(
                        title=f"GitHub CSV for {key}",
                        topic=topic,
                        download_url=url,
                        source="GitHub",
                        source_type=self.source_type,
                        description=f"Raw open CSV dataset for {key} from GitHub datasets.",
                        file_format=guess_format(url),
                        tags=[key, "github", "csv"],
                        rank_hint=13 + score_text(topic, key),
                    )
                )

        hits.sort(key=lambda c: c.rank_hint, reverse=True)
        return hits[:limit]
