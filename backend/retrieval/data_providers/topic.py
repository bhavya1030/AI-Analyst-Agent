"""Topic extraction and keyword mapping for provider routing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


_STOP = {
    "the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "with", "by",
    "data", "dataset", "datasets", "open", "csv", "json", "analyze", "analyse",
    "study", "explore", "show", "visualize", "visualise", "trends", "trend",
    "global", "world", "worldwide", "using", "about", "from", "over", "time",
}


@dataclass
class TopicContext:
    raw: str
    normalized: str
    keywords: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)


# Map surface phrases → canonical topic keys used by catalogs
_ALIAS_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(electric\s*vehicle|ev\s*sales|ev\b|electric car)", re.I), "electric_vehicles"),
    (re.compile(r"\b(co2|co₂|carbon\s*dioxide|carbon\s*emission|greenhouse)", re.I), "co2_emissions"),
    (re.compile(r"\b(renewable|solar\s*energy|wind\s*energy|clean\s*energy)", re.I), "renewable_energy"),
    (re.compile(r"\b(happiness|world\s*happiness)", re.I), "happiness"),
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
]


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
    # also keep tokens as soft aliases
    return TopicContext(
        raw=raw,
        normalized=normalized,
        keywords=tokens,
        aliases=aliases,
    )
