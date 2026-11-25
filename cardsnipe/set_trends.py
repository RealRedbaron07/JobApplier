"""Validate user-imported set price observations. No market data is fetched here."""

from __future__ import annotations

import csv
import io
import math
import re
from datetime import date


FIELDS = {"date", "source", "set_name", "metric", "unit", "value"}


def parse_set_prices_csv(text: str) -> list[dict]:
    if not isinstance(text, str) or not text.strip() or len(text) > 100_000:
        raise ValueError("Paste a set price CSV up to 100 KB.")
    try:
        reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")), strict=True)
        if not reader.fieldnames or {name.strip() for name in reader.fieldnames} != FIELDS:
            raise ValueError("CSV columns must be date,source,set_name,metric,unit,value.")
        reader.fieldnames = [name.strip() for name in reader.fieldnames]
        entries = []
        for row in reader:
            if len(entries) >= 500:
                raise ValueError("Import at most 500 set observations at once.")
            if None in row or any(value is None for value in row.values()):
                raise ValueError("Each CSV row needs all six columns.")
            values = {key: value.strip() for key, value in row.items()}
            for key in ("source", "set_name", "metric"):
                values[key] = " ".join(values[key].split())
                if not 2 <= len(values[key]) <= 100 or re.search(r"[\x00-\x1f]", values[key]):
                    raise ValueError(f"Each row needs a {key} of 2 to 100 characters.")
            if not re.fullmatch(r"[A-Za-z]{2,12}", values["unit"]):
                raise ValueError("Use a unit such as CAD, USD or POINTS.")
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", values["date"]):
                raise ValueError("Use dates in YYYY-MM-DD format.")
            try:
                observed_on = date.fromisoformat(values["date"])
            except ValueError as exc:
                raise ValueError("Use real dates in YYYY-MM-DD format.") from exc
            if observed_on > date.today():
                raise ValueError("Set observations cannot be dated in the future.")
            try:
                value = float(values["value"])
            except ValueError as exc:
                raise ValueError("Every set observation needs a positive numeric value.") from exc
            if not math.isfinite(value) or not 0 < value <= 1_000_000_000:
                raise ValueError("Every set observation needs a finite positive value.")
            entries.append({"source": values["source"], "set_name": values["set_name"],
                            "metric": values["metric"], "unit": values["unit"].upper(),
                            "observed_on": observed_on, "value": value})
    except (csv.Error, TypeError) as exc:
        raise ValueError("Set price CSV could not be read.") from exc
    if not entries:
        raise ValueError("Add at least one set observation below the CSV header.")
    return entries
