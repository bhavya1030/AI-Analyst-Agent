"""Seed local analytical CSVs for E2E workflow testing."""

from __future__ import annotations

import csv
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "local_library"
OUT.mkdir(parents=True, exist_ok=True)


def _write(name: str, headers: list[str], rows: list[list]) -> Path:
    path = OUT / name
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)
    return path


def seed() -> dict[str, Path]:
    paths: dict[str, Path] = {}

    # Seattle weather monthly
    months = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]
    rain = [5.8, 3.8, 3.8, 2.7, 1.9, 1.5, 0.8, 1.0, 1.6, 3.5, 6.1, 5.6]
    temp = [46, 48, 52, 56, 62, 67, 72, 72, 67, 58, 50, 45]
    wind = [9.2, 8.8, 8.5, 7.9, 7.2, 6.8, 6.5, 6.6, 7.0, 7.8, 8.6, 9.0]
    rows = []
    for y in range(2015, 2025):
        for i, m in enumerate(months):
            rows.append([y, m, rain[i] + (y - 2015) * 0.02, temp[i] + (y % 3) * 0.2, wind[i]])
    paths["seattle_weather"] = _write(
        "seattle_weather.csv",
        ["Year", "Month", "Rainfall_in", "Temp_F", "Wind_mph"],
        rows,
    )

    # Population by country
    countries = [
        ("India", 1.43e9, 0.009),
        ("China", 1.41e9, 0.001),
        ("United States", 3.35e8, 0.005),
        ("Indonesia", 2.78e8, 0.008),
        ("Pakistan", 2.4e8, 0.019),
        ("Nigeria", 2.23e8, 0.024),
        ("Brazil", 2.16e8, 0.006),
        ("Bangladesh", 1.73e8, 0.01),
        ("Russia", 1.44e8, -0.002),
        ("Mexico", 1.29e8, 0.008),
        ("Japan", 1.23e8, -0.004),
        ("Ethiopia", 1.26e8, 0.025),
    ]
    pop_rows = []
    for c, base, g in countries:
        for y in range(2000, 2025):
            pop = base * ((1 + g) ** (y - 2023))
            pop_rows.append([c, y, int(pop)])
    paths["world_population"] = _write(
        "world_population.csv",
        ["Country", "Year", "Population"],
        pop_rows,
    )

    # GDP
    gdp_rows = []
    for y in range(2000, 2025):
        india = 4.6e11 + (y - 2000) * 1.1e11
        us = 1.0e13 + (y - 2000) * 4.5e11
        china = 1.2e12 + (y - 2000) * 5.5e11
        gdp_rows.append(["India", y, india])
        gdp_rows.append(["United States", y, us])
        gdp_rows.append(["China", y, china])
    paths["world_gdp"] = _write(
        "world_gdp.csv",
        ["Country", "Year", "GDP"],
        gdp_rows,
    )
    paths["india_gdp"] = _write(
        "india_gdp.csv",
        ["Country", "Year", "GDP"],
        [r for r in gdp_rows if r[0] == "India"],
    )

    # Oil prices
    paths["oil_prices"] = _write(
        "oil_prices.csv",
        ["Year", "Price_USD"],
        [[y, 30 + ((y % 8) * 8) + math.sin(y) * 3] for y in range(2000, 2025)],
    )

    # Gold prices
    paths["gold_prices"] = _write(
        "gold_prices.csv",
        ["Date", "Year", "Price"],
        [[f"{y}-12-31", y, 400 + (y - 2000) * 45] for y in range(2000, 2025)],
    )

    # India rainfall
    paths["india_rainfall"] = _write(
        "india_rainfall.csv",
        ["Year", "Rainfall_mm"],
        [[y, 900 + ((y % 4) * 30) + (y % 3) * 5] for y in range(2000, 2025)],
    )

    # Unemployment
    paths["india_unemployment"] = _write(
        "india_unemployment.csv",
        ["Country", "Year", "Unemployment"],
        [["India", y, 5.0 + ((y % 7) * 0.2)] for y in range(2000, 2025)],
    )

    # Inflation
    paths["india_inflation"] = _write(
        "india_inflation.csv",
        ["Country", "Year", "Inflation"],
        [["India", y, 3.5 + ((y % 5) * 0.4)] for y in range(2000, 2025)],
    )

    # Employees (copy-like small HR set)
    paths["employees"] = _write(
        "employees.csv",
        ["Name", "Department", "Salary", "Years"],
        [
            ["Alice", "Engineering", 120000, 5],
            ["Bob", "Sales", 85000, 3],
            ["Carol", "Engineering", 135000, 8],
            ["Dan", "HR", 72000, 2],
            ["Eve", "Sales", 95000, 6],
            ["Frank", "Engineering", 110000, 4],
            ["Grace", "Marketing", 88000, 5],
            ["Hank", "Marketing", 78000, 1],
        ],
    )

    # CO2 local copy for dual local/remote
    paths["co2_local"] = _write(
        "co2_emissions_local.csv",
        ["Country", "Year", "CO2"],
        [["India", y, 1000 + (y - 2000) * 50] for y in range(2000, 2025)]
        + [["USA", y, 5000 + (y - 2000) * 10] for y in range(2000, 2025)],
    )

    print(f"Seeded {len(paths)} datasets under {OUT}")
    for k, p in paths.items():
        print(f"  {k}: {p} ({p.stat().st_size} bytes)")
    return paths


if __name__ == "__main__":
    seed()
