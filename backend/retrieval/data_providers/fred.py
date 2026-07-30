"""FRED (Federal Reserve Economic Data) provider — public CSV graph endpoints.

No API key required for fredgraph.csv series downloads.
"""

from __future__ import annotations

from backend.retrieval.data_providers.base import DataProvider, DatasetCandidate

# Common FRED series IDs → labels
_FRED_SERIES: dict[str, tuple[str, str, list[str]]] = {
    # id: (title, license tags, keywords)
    "GDP": ("US Real/Nominal GDP (FRED GDP)", "FRED open data", ["gdp", "us", "macro"]),
    "GDPC1": ("US Real GDP (FRED GDPC1)", "FRED open data", ["gdp", "real", "us"]),
    "CPIAUCSL": ("US CPI All Urban (FRED)", "FRED open data", ["inflation", "cpi", "us"]),
    "UNRATE": ("US Unemployment Rate (FRED)", "FRED open data", ["unemployment", "us"]),
    "FEDFUNDS": ("Federal Funds Effective Rate (FRED)", "FRED open data", ["interest", "rate", "fed"]),
    "DGS10": ("10-Year Treasury Rate (FRED)", "FRED open data", ["interest", "treasury", "bond"]),
    "PAYEMS": ("US Nonfarm Payrolls (FRED)", "FRED open data", ["employment", "payroll"]),
    "M2SL": ("M2 Money Stock (FRED)", "FRED open data", ["money", "m2"]),
}


def _csv_url(series_id: str) -> str:
    return f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"


class FredProvider(DataProvider):
    name = "fred"
    priority = 85
    domains = ("macroeconomics", "finance", "economics")

    def supports(self, topic: str, keywords: list[str]) -> bool:
        blob = f"{topic} {' '.join(keywords)}".lower()
        if "fred" in blob or "federal reserve" in blob:
            return True
        # US macro series
        keys = (
            "gdp", "inflation", "cpi", "unemployment", "interest", "treasury",
            "fed", "payroll", "money supply", "m2",
        )
        us_hint = any(x in blob for x in ("us ", "u.s", "usa", "united states", "american"))
        return us_hint and any(k in blob for k in keys) or any(
            k in blob for k in ("interest rate", "federal funds", "treasury")
        )

    def preferred_for(self, topic: str, keywords: list[str]) -> int:
        if not self.supports(topic, keywords):
            return -1
        blob = f"{topic} {' '.join(keywords)}".lower()
        if "fred" in blob:
            return self.priority + 20
        if any(x in blob for x in ("united states", "usa", "us ", "u.s")):
            return self.priority + 10
        return self.priority

    def search(self, topic: str, keywords: list[str], *, limit: int = 5) -> list[DatasetCandidate]:
        blob = f"{topic} {' '.join(keywords)}".lower()
        hits: list[DatasetCandidate] = []
        for series_id, (title, license_, keys) in _FRED_SERIES.items():
            score = sum(1 for k in keys if k in blob)
            if score == 0 and "fred" not in blob:
                continue
            conf = min(0.95, 0.55 + 0.12 * score)
            hits.append(
                DatasetCandidate(
                    title=title,
                    topic=topic,
                    download_url=_csv_url(series_id),
                    provider=self.name,
                    source_url=f"https://fred.stlouisfed.org/series/{series_id}",
                    license=license_,
                    dataset_version=f"FRED:{series_id}",
                    file_format="csv",
                    description=f"FRED series {series_id} as CSV via fredgraph.",
                    tags=list(keys) + ["fred", "csv"],
                    rank=int(80 + 10 * score),
                    confidence=conf,
                    country=["United States"],
                    metric=keys[0].upper() if keys else series_id,
                    time_period="historical",
                    extra={"source_type": "API", "fred_series": series_id},
                )
            )
        hits.sort(key=lambda c: c.rank, reverse=True)
        return hits[:limit]
