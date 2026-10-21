"""ECB euro-area broad money; source composition and stock timing remain visible."""

from __future__ import annotations

from typing import Any

from macrolab.data.sources.bis import fetch_issue, finite, make_row, read_sdmx
from macrolab.data.sources.http import SourceClient


def fetch_ecb(client: SourceClient, countries: list[dict[str, Any]]) -> dict[str, Any]:
    if not any(country["iso3"] == "EA" for country in countries):
        return {"rows": [], "issues": []}
    key = "M.U2.Y.V.M30.X.1.U2.2300.Z01.E"
    url = f"https://data-api.ecb.europa.eu/service/data/BSI/{key}?format=csvdata"
    fetched = client.fetch("ECB", "ecb_ea_money_m3", url, "text/csv")
    if fetched.record.status != 200 or fetched.body is None:
        return {"rows": [], "issues": [fetch_issue("ECB", "ecb_ea_money_m3", fetched)]}
    raw_rows, parser = read_sdmx(fetched.body)
    rows = []
    for raw in raw_rows:
        if not raw.get("TIME_PERIOD") or not finite(raw.get("OBS_VALUE")):
            continue
        if raw.get("UNIT") != "EUR" or raw.get("ADJUSTMENT") != "Y" or raw.get("BS_ITEM") != "M30":
            continue
        rows.append(
            make_row(
                country="EA",
                concept="money_broad",
                source="ECB",
                series_id=raw["KEY"],
                raw=raw,
                fetched=fetched,
                parser=parser,
                selector={"KEY": raw["KEY"]},
                unit="EUR",
                frequency="M",
                sa_flag="SA",
                price_basis="nominal",
                flags=[
                    "working_day_adjusted",
                    "monthly_end_of_period",
                    "euro_area_changing_composition",
                ],
            )
        )
    return {
        "rows": rows,
        "issues": [] if rows else [fetch_issue("ECB", "ecb_ea_money_m3", fetched)],
    }
