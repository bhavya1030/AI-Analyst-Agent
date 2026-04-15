from typing import Iterable, Optional

try:
    from rapidfuzz import process
except ImportError:  # pragma: no cover
    process = None

COLUMN_SYNONYMS = {
    "gdp": "Value",
    "value": "Value",
    "country": "Country Name",
    "country name": "Country Name",
    "country code": "Country Code",
    "year": "Year",
    "date": "Year",
    "population": "Population",
    "population growth": "Population",
    "inflation": "Value",
    "co2": "CO2",
    "emissions": "CO2",
    "temperature": "Temperature",
    "sales": "Sales",
    "revenue": "Revenue",
    "profit": "Profit",
    "income": "Income",
}


def _normalize_reference(reference: str) -> str:
    return reference.strip().lower()


def map_column_reference(
    reference: str,
    columns: Iterable[str],
    last_columns: list[str] | None = None,
    threshold: int = 55,
) -> Optional[str]:
    if not reference or not columns:
        return None

    normalized = _normalize_reference(reference)
    lowered_columns = [col.lower() for col in columns]

    for keyword, target in COLUMN_SYNONYMS.items():
        if keyword in normalized:
            for col in columns:
                if col.lower() == target.lower():
                    return col

    if normalized in lowered_columns:
        return columns[lowered_columns.index(normalized)]

    for col in columns:
        if col.lower() in normalized:
            return col

    if last_columns:
        for col in last_columns:
            if col.lower() in normalized:
                return col

    if process is not None:
        match = process.extractOne(normalized, columns)
        if match and match[1] >= threshold:
            return match[0]

    matches = [col for col in columns if normalized in col.lower()]
    if matches:
        return matches[0]

    if last_columns:
        return last_columns[-1]

    return None
