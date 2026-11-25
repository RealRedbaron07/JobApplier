"""Set trends require user-supplied, comparable dated observations."""

import pytest
from datetime import date, timedelta

from cardsnipe.set_trends import parse_set_prices_csv
from test_snipe_dashboard import snipe_client


HEADER = "date,source,set_name,metric,unit,value\n"


def test_local_set_history_tracks_change_without_mixing_sources_or_metrics(snipe_client, monkeypatch):
    from config import Config

    monkeypatch.setattr(Config, "EXTERNAL_ACCESS_ENABLED", False)
    client, store, _ = snipe_client
    csv = HEADER + (
        "2026-10-01,Market App,Evolving Skies,Set index,POINTS,100\n"
        "2026-10-31,Market App,Evolving Skies,Set index,POINTS,112\n"
        "2026-10-31,Other App,Evolving Skies,Set index,POINTS,150\n"
        "2026-10-31,Market App,Evolving Skies,Booster box,USD,500\n"
    )
    saved = client.post("/api/snipe/set-trends/import", json={"csv": csv}).get_json()
    assert saved["local_only"] and len(saved["series"]) == 3
    trend = next(row for row in saved["series"] if row["source"] == "Market App" and row["metric"] == "Set index")
    assert trend["change_pct"] == 12.0 and trend["observations"] == 2
    assert trend["first_date"] == "2026-10-01" and trend["latest_date"] == "2026-10-31"
    assert all(row["change_pct"] is None for row in saved["series"] if row is not trend)
    assert client.get("/api/snipe/set-trends").get_json()["series"] == saved["series"]
    corrected = client.post("/api/snipe/set-trends/import", json={"csv": HEADER +
                            "2026-10-31,market app,Evolving Skies,Set index,POINTS,115\n"}).get_json()
    updated = next(row for row in corrected["series"] if row["metric"] == "Set index" and row["source"] == "Market App")
    assert updated["change_pct"] == 15.0 and updated["observations"] == 2
    assert len(store.set_trends()) == 3


@pytest.mark.parametrize("row", [
    "future",
    "2026-10-01,App,Evolving Skies,Index,POINTS,NaN",
    "2026-10-01,App,Evolving Skies,Index,POINTS,-1",
    "2026-10-01,App,Evolving Skies,Index,POINTS",
    "2026-10-01,App,Evolving Skies,Index,POINTS,100,extra",
])
def test_invalid_set_history_cannot_replace_saved_values(snipe_client, row):
    client, store, _ = snipe_client
    if row == "future":
        row = f"{(date.today() + timedelta(days=1)).isoformat()},App,Evolving Skies,Index,POINTS,100"
    good = HEADER + "2026-10-01,App,Evolving Skies,Index,POINTS,100\n"
    assert client.post("/api/snipe/set-trends/import", json={"csv": good}).status_code == 200
    before = store.set_trends()
    assert client.post("/api/snipe/set-trends/import", json={"csv": good + row + "\n"}).status_code == 400
    assert store.set_trends() == before


def test_set_history_rejects_wrong_columns_and_empty_data():
    with pytest.raises(ValueError, match="columns"):
        parse_set_prices_csv("date,source,set_name,value\n2026-10-01,App,Base Set,100\n")
    with pytest.raises(ValueError, match="at least one"):
        parse_set_prices_csv(HEADER)
