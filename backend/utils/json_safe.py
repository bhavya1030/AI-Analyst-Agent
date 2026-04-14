import json
import math
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd


def make_json_safe(value):
    if value is None or isinstance(value, (str, int, bool)):
        return value

    if isinstance(value, float):
        return value if math.isfinite(value) else None

    if isinstance(value, (np.integer,)):
        return int(value)

    if isinstance(value, (np.floating, Decimal)):
        numeric_value = float(value)
        return numeric_value if math.isfinite(numeric_value) else None

    if isinstance(value, (np.bool_,)):
        return bool(value)

    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, pd.DataFrame):
        return make_json_safe(value.to_dict(orient="records"))

    if isinstance(value, (pd.Series, pd.Index)):
        return make_json_safe(value.tolist())

    if isinstance(value, np.ndarray):
        return make_json_safe(value.tolist())

    if isinstance(value, dict):
        return {
            str(key): make_json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [make_json_safe(item) for item in value]

    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def figure_to_json(fig):
    return json.loads(fig.to_json())
