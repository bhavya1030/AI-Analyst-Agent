"""Eurostat provider — SDMX-JSON data endpoints (no HTML search pages)."""

from __future__ import annotations

from backend.retrieval.data_providers.base import DataProvider, DatasetCandidate

# Stable Eurostat dataset codes with JSON-stat / SDMX-JSON friendly APIs
# Using the statistics API JSON endpoint pattern.
_EUROSTAT: dict[str, tuple[str, str, list[str]]] = {
    # code: (title, description, keywords)
    "nama_10_gdp": (
        "Eurostat GDP and main components",
        "EU GDP annual national accounts (nama_10_gdp).",
        ["gdp", "eu", "europe", "macro"],
    ),
    "une_rt_a": (
        "Eurostat Unemployment rates",
        "EU unemployment rates by sex and age (annual).",
        ["unemployment", "eu", "europe"],
    ),
    "prc_hicp_aind": (
        "Eurostat HICP inflation",
        "Harmonised index of consumer prices (annual).",
        ["inflation", "cpi", "hicp", "eu"],
    ),
    "demo_pjan": (
        "Eurostat Population on 1 January",
        "Population statistics for European countries.",
        ["population", "eu", "europe", "demographics"],
    ),
}


def _json_url(dataset_code: str) -> str:
    # Eurostat Statistics API — JSON-stat 2.0
    return (
        "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
        f"{dataset_code}?format=JSON&lang=en"
    )


class EurostatProvider(DataProvider):
    name = "eurostat"
    priority = 82
    domains = ("macroeconomics", "demographics", "economics")

    def supports(self, topic: str, keywords: list[str]) -> bool:
        blob = f"{topic} {' '.join(keywords)}".lower()
        if "eurostat" in blob or "european union" in blob or " eu " in f" {blob} ":
            return True
        eu_countries = (
            "germany", "france", "italy", "spain", "netherlands", "belgium",
            "sweden", "poland", "europe", "eurozone", "eu ",
        )
        metrics = ("gdp", "inflation", "unemployment", "population", "hicp")
        return any(c in blob for c in eu_countries) and any(m in blob for m in metrics)

    def preferred_for(self, topic: str, keywords: list[str]) -> int:
        if not self.supports(topic, keywords):
            return -1
        blob = f"{topic} {' '.join(keywords)}".lower()
        if "eurostat" in blob or "european" in blob:
            return self.priority + 15
        return self.priority

    def search(self, topic: str, keywords: list[str], *, limit: int = 5) -> list[DatasetCandidate]:
        blob = f"{topic} {' '.join(keywords)}".lower()
        hits: list[DatasetCandidate] = []
        for code, (title, desc, keys) in _EUROSTAT.items():
            score = sum(1 for k in keys if k in blob)
            if score == 0 and "eurostat" not in blob and "europe" not in blob:
                continue
            conf = min(0.92, 0.5 + 0.12 * score)
            hits.append(
                DatasetCandidate(
                    title=title,
                    topic=topic,
                    download_url=_json_url(code),
                    provider=self.name,
                    source_url=f"https://ec.europa.eu/eurostat/databrowser/view/{code}/default/table",
                    license="Eurostat reuse policy (CC-compatible for most data)",
                    dataset_version=f"EUROSTAT:{code}",
                    file_format="json",
                    description=desc,
                    tags=list(keys) + ["eurostat", "sdmx", "json"],
                    rank=int(75 + 10 * score),
                    confidence=conf,
                    country=["European Union"],
                    metric=keys[0].upper() if keys else code,
                    time_period="annual",
                    extra={"source_type": "API", "eurostat_code": code},
                )
            )
        hits.sort(key=lambda c: c.rank, reverse=True)
        return hits[:limit]
