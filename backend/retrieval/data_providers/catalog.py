"""Curated, verified-style downloadable dataset catalog.

Only direct file / structured API endpoints — never HTML search pages.
URLs are preferred in order; orchestrator validates before use.
"""

from __future__ import annotations

from typing import Any

# Each entry: list of alternative download specs (first valid wins at runtime).
# Formats: csv | json
CURATED: dict[str, list[dict[str, Any]]] = {
    "gdp": [
        {
            "title": "World Bank GDP (open CSV)",
            "download_url": "https://raw.githubusercontent.com/datasets/gdp/master/data/gdp.csv",
            "provider": "world_bank",
            "license": "CC-BY / World Bank open data",
            "dataset_version": "datasets/gdp@master",
            "file_format": "csv",
            "tags": ["gdp", "macro", "country", "year"],
            "description": "Country-level annual GDP series.",
        }
    ],
    "population": [
        {
            "title": "World Population by Country",
            "download_url": "https://raw.githubusercontent.com/datasets/population/master/data/population.csv",
            "provider": "world_bank",
            "license": "CC-BY / World Bank open data",
            "dataset_version": "datasets/population@master",
            "file_format": "csv",
            "tags": ["population", "demographics"],
            "description": "Country population totals.",
        }
    ],
    "co2_emissions": [
        {
            "title": "Our World in Data — CO₂ dataset",
            "download_url": "https://raw.githubusercontent.com/owid/co2-data/master/owid-co2-data.csv",
            "provider": "owid",
            "license": "CC BY 4.0 (OWID)",
            "dataset_version": "owid/co2-data@master",
            "file_format": "csv",
            "tags": ["co2", "emissions", "climate"],
            "description": "Comprehensive national CO₂ and GHG series from OWID.",
        },
        {
            "title": "CO₂ emissions by nation (fossil)",
            "download_url": "https://raw.githubusercontent.com/datasets/co2-fossil-by-nation/master/data/fossil-fuel-co2-emissions-by-nation.csv",
            "provider": "github_raw",
            "license": "ODC-PDDL",
            "dataset_version": "datasets/co2-fossil-by-nation",
            "file_format": "csv",
            "tags": ["co2", "fossil"],
            "description": "Historical fossil-fuel CO₂ by nation.",
        },
    ],
    "renewable_energy": [
        {
            "title": "Our World in Data — Energy",
            "download_url": "https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv",
            "provider": "owid",
            "license": "CC BY 4.0 (OWID)",
            "dataset_version": "owid/energy-data@master",
            "file_format": "csv",
            "tags": ["energy", "renewable", "electricity"],
            "description": "Energy production and mix including renewables.",
        }
    ],
    "electric_vehicles": [
        {
            # Energy dataset includes transport/EV-related series in broad form
            "title": "Our World in Data — Energy (EV / transport context)",
            "download_url": "https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv",
            "provider": "owid",
            "license": "CC BY 4.0 (OWID)",
            "dataset_version": "owid/energy-data@master",
            "file_format": "csv",
            "tags": ["ev", "transport", "energy"],
            "description": "Energy dataset used as proxy open series for EV/transport analysis.",
        }
    ],
    "happiness": [
        {
            "title": "World Bank Life expectancy (wellbeing / happiness proxy)",
            "download_url": (
                "https://api.worldbank.org/v2/country/all/indicator/SP.DYN.LE00.IN"
                "?format=json&per_page=20000"
            ),
            "provider": "world_bank",
            "license": "CC BY 4.0 (World Bank)",
            "dataset_version": "SP.DYN.LE00.IN",
            "file_format": "json",
            "tags": ["happiness", "wellbeing", "life_expectancy"],
            "description": (
                "Life expectancy at birth as open wellbeing proxy when "
                "dedicated happiness microdata is unavailable."
            ),
        }
    ],
    "air_quality": [
        {
            "title": "World Bank PM2.5 air pollution (JSON API)",
            "download_url": (
                "https://api.worldbank.org/v2/country/all/indicator/EN.ATM.PM25.MC.M3"
                "?format=json&per_page=20000"
            ),
            "provider": "world_bank",
            "license": "CC BY 4.0 (World Bank)",
            "dataset_version": "EN.ATM.PM25.MC.M3",
            "file_format": "json",
            "tags": ["air", "pollution", "pm25", "aqi"],
            "description": "PM2.5 air pollution mean annual exposure by country.",
        }
    ],
    "inflation": [
        {
            "title": "World Bank CPI inflation (JSON API)",
            "download_url": (
                "https://api.worldbank.org/v2/country/all/indicator/FP.CPI.TOTL.ZG"
                "?format=json&per_page=20000"
            ),
            "provider": "world_bank",
            "license": "CC BY 4.0 (World Bank)",
            "dataset_version": "FP.CPI.TOTL.ZG",
            "file_format": "json",
            "tags": ["inflation", "cpi"],
            "description": "Annual inflation (CPI) by country from World Bank indicators.",
        }
    ],
    "cryptocurrency": [
        {
            "title": "Bitcoin market chart (CoinGecko JSON)",
            "download_url": (
                "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
                "?vs_currency=usd&days=365"
            ),
            "provider": "json_api",
            "license": "CoinGecko API terms",
            "dataset_version": "coingecko-bitcoin-365d",
            "file_format": "json",
            "tags": ["bitcoin", "crypto", "price"],
            "description": "Bitcoin USD price history (1y) via CoinGecko.",
        }
    ],
    "olympics": [
        {
            "title": "Olympics athlete events (TidyTuesday CSV)",
            "download_url": (
                "https://raw.githubusercontent.com/rfordatascience/tidytuesday/"
                "master/data/2021/2021-07-27/olympics.csv"
            ),
            "provider": "github_raw",
            "license": "CC0 / upstream sports data",
            "dataset_version": "tidytuesday/2021-07-27/olympics",
            "file_format": "csv",
            "tags": ["olympics", "medals", "athletes"],
            "description": "Historical olympic athlete events including medals.",
        }
    ],
    "internet_usage": [
        {
            "title": "World Bank Internet users (JSON API)",
            "download_url": (
                "https://api.worldbank.org/v2/country/all/indicator/IT.NET.USER.ZS"
                "?format=json&per_page=20000"
            ),
            "provider": "world_bank",
            "license": "CC BY 4.0 (World Bank)",
            "dataset_version": "IT.NET.USER.ZS",
            "file_format": "json",
            "tags": ["internet", "connectivity"],
            "description": "Individuals using the Internet (% of population).",
        }
    ],
    "tourism": [
        {
            "title": "World Bank International tourism arrivals (JSON API)",
            "download_url": (
                "https://api.worldbank.org/v2/country/all/indicator/ST.INT.ARVL"
                "?format=json&per_page=20000"
            ),
            "provider": "world_bank",
            "license": "CC BY 4.0 (World Bank)",
            "dataset_version": "ST.INT.ARVL",
            "file_format": "json",
            "tags": ["tourism", "arrivals"],
            "description": "International tourism, number of arrivals.",
        }
    ],
    "unemployment": [
        {
            "title": "World Bank Unemployment (JSON API)",
            "download_url": (
                "https://api.worldbank.org/v2/country/all/indicator/SL.UEM.TOTL.ZS"
                "?format=json&per_page=20000"
            ),
            "provider": "world_bank",
            "license": "CC BY 4.0 (World Bank)",
            "dataset_version": "SL.UEM.TOTL.ZS",
            "file_format": "json",
            "tags": ["unemployment", "labour"],
            "description": "Unemployment, total (% of total labor force).",
        }
    ],
    "gold": [
        {
            "title": "Gold prices (annual CSV)",
            "download_url": "https://raw.githubusercontent.com/datasets/gold-prices/master/data/annual.csv",
            "provider": "github_raw",
            "license": "ODC-PDDL",
            "dataset_version": "datasets/gold-prices",
            "file_format": "csv",
            "tags": ["gold", "commodity"],
            "description": "Annual gold price series.",
        }
    ],
    "climate": [
        {
            "title": "Global temperature (annual)",
            "download_url": "https://raw.githubusercontent.com/datasets/global-temp/master/data/annual.csv",
            "provider": "github_raw",
            "license": "ODC-PDDL",
            "dataset_version": "datasets/global-temp",
            "file_format": "csv",
            "tags": ["climate", "temperature"],
            "description": "Global temperature anomaly annual series.",
        }
    ],
    "covid": [
        {
            "title": "COVID-19 countries aggregated",
            "download_url": "https://raw.githubusercontent.com/datasets/covid-19/master/data/countries-aggregated.csv",
            "provider": "github_raw",
            "license": "ODC-PDDL",
            "dataset_version": "datasets/covid-19",
            "file_format": "csv",
            "tags": ["covid", "health"],
            "description": "Country-level COVID-19 aggregated cases.",
        }
    ],
}


def catalog_entries_for(aliases: list[str], keywords: list[str]) -> list[dict[str, Any]]:
    """Return enabled curated entries matching aliases or keywords."""
    keys = set(aliases or [])
    # map loose keywords to catalog keys
    kw = set(keywords or [])
    if {"gdp"} & kw:
        keys.add("gdp")
    if {"population"} & kw:
        keys.add("population")
    if {"co2", "emission", "emissions", "carbon"} & kw:
        keys.add("co2_emissions")
    if {"renewable", "energy", "solar", "wind"} & kw:
        keys.add("renewable_energy")
    if {"ev", "electric", "vehicle"} & kw:
        keys.add("electric_vehicles")
    if {"happiness"} & kw:
        keys.add("happiness")
    if {"aqi", "air", "pollution", "pm25"} & kw:
        keys.add("air_quality")
    if {"inflation", "cpi"} & kw:
        keys.add("inflation")
    if {"bitcoin", "crypto", "cryptocurrency"} & kw:
        keys.add("cryptocurrency")
    if {"olympic", "olympics", "medal", "medals"} & kw:
        keys.add("olympics")
    if {"internet", "broadband"} & kw:
        keys.add("internet_usage")
    if {"tourism", "tourist"} & kw:
        keys.add("tourism")
    if {"unemployment"} & kw:
        keys.add("unemployment")
    if {"gold"} & kw:
        keys.add("gold")
    if {"climate", "temperature"} & kw:
        keys.add("climate")
    if {"covid", "coronavirus"} & kw:
        keys.add("covid")

    out: list[dict[str, Any]] = []
    for key in keys:
        for entry in CURATED.get(key, []):
            if entry.get("disabled"):
                continue
            item = dict(entry)
            item["catalog_key"] = key
            out.append(item)
    return out
