"""Topic extraction and keyword mapping for provider routing (Retrieval v2)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


_STOP = {
    "the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "with", "by",
    "data", "dataset", "datasets", "open", "csv", "json", "analyze", "analyse",
    "study", "explore", "show", "visualize", "visualise", "trends", "trend",
    "global", "world", "worldwide", "using", "about", "from", "over", "time",
    "rates", "rate", "statistics", "index", "scores", "major", "cities",
}


@dataclass
class TopicContext:
    raw: str
    normalized: str
    keywords: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    # Retrieval v2 dimensions
    country: list[str] = field(default_factory=list)
    metric: Optional[str] = None
    time_period: Optional[str] = None
    domain: str = "general"


# Map surface phrases → canonical topic keys used by catalogs
_ALIAS_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(electric\s*vehicle|ev\s*sales|ev\b|electric car)", re.I), "electric_vehicles"),
    (re.compile(r"\b(co2|co₂|carbon\s*dioxide|carbon\s*emission|greenhouse)", re.I), "co2_emissions"),
    (re.compile(r"\b(renewable|solar\s*energy|wind\s*energy|clean\s*energy)", re.I), "renewable_energy"),
    (re.compile(r"\b(happiness|world\s*happiness|life\s*expectancy)", re.I), "happiness"),
    (re.compile(r"\b(air\s*quality|aqi|pm2\.?5|pollution\s*index)", re.I), "air_quality"),
    (re.compile(r"\b(inflation|cpi|consumer\s*price)", re.I), "inflation"),
    (re.compile(r"\b(bitcoin|crypto|cryptocurrency|ethereum)", re.I), "cryptocurrency"),
    (re.compile(r"\b(olympic|olympics|medal\s*count)", re.I), "olympics"),
    (re.compile(r"\b(internet\s*usage|internet\s*users|broadband)", re.I), "internet_usage"),
    (re.compile(r"\b(tourism|tourist|tourist\s*arrivals)", re.I), "tourism"),
    (re.compile(r"\b(gdp|gross\s*domestic)", re.I), "gdp"),
    (re.compile(r"\b(population|demograph)", re.I), "population"),
    (re.compile(r"\b(unemployment|jobless)", re.I), "unemployment"),
    (re.compile(r"\b(gold(\s*price)?)", re.I), "gold"),
    (re.compile(r"\b(oil(\s*price)?|crude)", re.I), "oil"),
    (re.compile(r"\b(covid|coronavirus)", re.I), "covid"),
    (re.compile(r"\b(climate|global\s*temp|temperature\s*anomaly)", re.I), "climate"),
    (re.compile(r"\b(interest\s*rate|federal\s*funds|fred)\b", re.I), "interest_rate"),
    (re.compile(r"\b(eurostat|eu\s*gdp|european\s*union)\b", re.I), "eu_macro"),
]

_COUNTRY_MAP = {
    "india": "India",
    "china": "China",
    "usa": "United States",
    "us": "United States",
    "united states": "United States",
    "uk": "United Kingdom",
    "united kingdom": "United Kingdom",
    "germany": "Germany",
    "france": "France",
    "japan": "Japan",
    "brazil": "Brazil",
    "canada": "Canada",
    "australia": "Australia",
    "mexico": "Mexico",
    "italy": "Italy",
    "spain": "Spain",
    "russia": "Russia",
}

_METRIC_LABELS = {
    "gdp": "GDP",
    "population": "Population",
    "inflation": "Inflation",
    "cpi": "CPI",
    "unemployment": "Unemployment",
    "co2_emissions": "CO2 Emissions",
    "renewable_energy": "Renewable Energy",
    "electric_vehicles": "Electric Vehicles",
    "happiness": "Happiness / Life Expectancy",
    "air_quality": "Air Quality",
    "cryptocurrency": "Cryptocurrency",
    "olympics": "Olympics",
    "internet_usage": "Internet Usage",
    "tourism": "Tourism",
    "gold": "Gold Price",
    "oil": "Oil Price",
    "covid": "COVID-19",
    "climate": "Climate / Temperature",
    "interest_rate": "Interest Rate",
    "eu_macro": "EU Macro",
}

_ALIAS_DOMAIN = {
    "gdp": "macroeconomics",
    "population": "demographics",
    "inflation": "macroeconomics",
    "unemployment": "macroeconomics",
    "interest_rate": "finance",
    "eu_macro": "macroeconomics",
    "co2_emissions": "climate",
    "renewable_energy": "energy",
    "electric_vehicles": "transport",
    "climate": "climate",
    "air_quality": "climate",
    "olympics": "sports",
    "cryptocurrency": "finance",
    "gold": "finance",
    "oil": "finance",
    "covid": "health",
    "happiness": "health",
    "tourism": "economics",
    "internet_usage": "technology",
}


def extract_topic_context(topic: str) -> TopicContext:
    raw = (topic or "").strip()
    normalized = re.sub(r"\s+", " ", raw.lower()).strip()
    tokens = [
        t
        for t in re.findall(r"[a-z0-9]+", normalized)
        if len(t) > 2 and t not in _STOP
    ]
    aliases: list[str] = []
    for pattern, key in _ALIAS_RULES:
        if pattern.search(raw) or pattern.search(normalized):
            if key not in aliases:
                aliases.append(key)

    countries: list[str] = []
    for key, label in sorted(_COUNTRY_MAP.items(), key=lambda x: -len(x[0])):
        if re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", normalized):
            if label not in countries:
                countries.append(label)

    metric = None
    for a in aliases:
        if a in _METRIC_LABELS:
            metric = _METRIC_LABELS[a]
            break
    if not metric:
        for tok in ("gdp", "population", "inflation", "unemployment", "gold", "oil"):
            if tok in tokens:
                metric = tok.upper() if tok == "gdp" else tok.title()
                break

    time_period = _extract_time_period(normalized)
    domain = "general"
    for a in aliases:
        if a in _ALIAS_DOMAIN:
            domain = _ALIAS_DOMAIN[a]
            break

    return TopicContext(
        raw=raw,
        normalized=normalized,
        keywords=tokens,
        aliases=aliases,
        country=countries,
        metric=metric,
        time_period=time_period,
        domain=domain,
    )


def _extract_time_period(text: str) -> Optional[str]:
    m = re.search(r"\b(19|20)\d{2}\s*[-–to]+\s*(19|20)\d{2}\b", text)
    if m:
        return m.group(0).replace("to", "-").replace("–", "-")
    m = re.search(r"\b(last|past|previous)\s+(\d+)\s+(years?|months?|days?)\b", text)
    if m:
        return f"{m.group(1)} {m.group(2)} {m.group(3)}"
    m = re.search(r"\b(19|20)\d{2}\b", text)
    if m:
        return m.group(0)
    if "annual" in text or "yearly" in text:
        return "annual"
    if "monthly" in text:
        return "monthly"
    if "daily" in text:
        return "daily"
    return None
