"""Bootstrap lightweight synthetic datasets for evaluation (no redesign of library)."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

# Default under project tests/evaluation/data
EVAL_DATA_DIR = Path(__file__).resolve().parent / "data"


def bootstrap_eval_datasets(root: Path | None = None) -> dict[str, Path]:
    """
    Create small CSV fixtures used by evaluation when live sources are unavailable.

    Returns mapping of logical name → path.
    """
    base = Path(root) if root else EVAL_DATA_DIR
    base.mkdir(parents=True, exist_ok=True)

    paths: dict[str, Path] = {}

    paths["india_gdp"] = _write_csv(
        base / "india_gdp.csv",
        ["Country", "Year", "GDP"],
        [["India", y, 1e12 + (y - 2000) * 8e10] for y in range(2000, 2025)],
    )
    paths["china_gdp"] = _write_csv(
        base / "china_gdp.csv",
        ["Country", "Year", "GDP"],
        [["China", y, 5e12 + (y - 2000) * 2e11] for y in range(2000, 2025)],
    )
    paths["india_population"] = _write_csv(
        base / "india_population.csv",
        ["Country", "Year", "Population"],
        [["India", y, 1e9 + (y - 2000) * 1.2e7] for y in range(2000, 2025)],
    )
    paths["india_inflation"] = _write_csv(
        base / "india_inflation.csv",
        ["Country", "Year", "Inflation"],
        [["India", y, 3.5 + ((y % 5) * 0.4)] for y in range(2000, 2025)],
    )
    paths["india_unemployment"] = _write_csv(
        base / "india_unemployment.csv",
        ["Country", "Year", "Unemployment"],
        [["India", y, 5.0 + ((y % 7) * 0.2)] for y in range(2000, 2025)],
    )
    paths["india_rainfall"] = _write_csv(
        base / "india_rainfall.csv",
        ["Country", "Year", "Rainfall"],
        [["India", y, 900 + ((y % 4) * 30)] for y in range(2000, 2025)],
    )
    paths["crop_yield"] = _write_csv(
        base / "crop_yield.csv",
        ["Country", "Year", "CropYield"],
        [["India", y, 2.0 + ((y - 2000) * 0.03)] for y in range(2000, 2025)],
    )
    paths["gold_prices"] = _write_csv(
        base / "gold_prices.csv",
        ["Date", "Year", "Price"],
        [[f"{y}-12-31", y, 400 + (y - 2000) * 45] for y in range(2000, 2025)],
    )
    paths["oil_prices"] = _write_csv(
        base / "oil_prices.csv",
        ["Year", "Price"],
        [[y, 30 + ((y % 8) * 8)] for y in range(2000, 2025)],
    )
    paths["co2"] = _write_csv(
        base / "co2_emissions.csv",
        ["Country", "Year", "CO2"],
        [["India", y, 1000 + (y - 2000) * 50] for y in range(2000, 2025)],
    )
    paths["empty"] = _write_csv(base / "empty.csv", ["A", "B"], [])
    paths["one_point"] = _write_csv(
        base / "one_point.csv",
        ["Year", "Value"],
        [[2020, 100]],
    )
    paths["corrupted"] = base / "corrupted.csv"
    paths["corrupted"].write_text(
        "Country,Year,Value\nIndia,not_a_year,??\n\"unclosed,2020,1\n",
        encoding="utf-8",
    )
    # Wide 100-column sample (few rows)
    wide_cols = ["id"] + [f"f{i}" for i in range(1, 100)]
    wide_row = [1] + [float(i) for i in range(1, 100)]
    paths["wide_100"] = _write_csv(base / "wide_100.csv", wide_cols, [wide_row, [2] + wide_row[1:]])

    # Incompatible join pair
    paths["incompatible_a"] = _write_csv(
        base / "incompatible_a.csv",
        ["WidgetId", "Color"],
        [["w1", "red"], ["w2", "blue"]],
    )
    paths["incompatible_b"] = _write_csv(
        base / "incompatible_b.csv",
        ["Sensor", "Reading"],
        [["s1", 0.1], ["s2", 0.2]],
    )

    return paths


def get_fixture_path(name: str, root: Path | None = None) -> Optional[Path]:
    paths = bootstrap_eval_datasets(root)
    return paths.get(name)


def _write_csv(path: Path, headers: list[str], rows: list[list]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(row)
    return path
