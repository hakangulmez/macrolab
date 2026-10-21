"""Keyless monthly EIA Brent workbook with an independent published-table audit."""

from __future__ import annotations

import io
import math
import re
from datetime import datetime
from html.parser import HTMLParser
from typing import Any

import pandas as pd

WORKBOOK_URL = "https://www.eia.gov/dnav/pet/hist_xls/RBRTEm.xls"
TABLE_URL = "https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=PET&s=RBRTE&f=M"
TITLE = "Europe Brent Spot Price FOB (Dollars per Barrel)"
SERIES_ID = "PET.RBRTE.M"


def parse_workbook(body: bytes) -> list[dict[str, Any]]:
    frame = pd.read_excel(io.BytesIO(body), sheet_name="Data 1", header=None, engine="xlrd")
    return parse_frame(frame)


def parse_frame(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Require the named monthly source and preserve original workbook cell provenance."""
    if (
        frame.shape[1] != 2
        or frame.shape[0] < 4
        or frame.iloc[1, 0] != "Sourcekey"
        or frame.iloc[1, 1] != "RBRTE"
        or frame.iloc[2, 0] != "Date"
        or frame.iloc[2, 1] != TITLE
    ):
        raise ValueError("EIA Brent workbook headers or source key differ from the verified series")
    result = []
    seen = set()
    for index, (period, value) in enumerate(frame.iloc[3:].itertuples(index=False, name=None), 4):
        if not isinstance(period, (datetime, pd.Timestamp)) or pd.isna(period):
            raise ValueError(f"Invalid EIA monthly date at worksheet row {index}")
        date = period.strftime("%Y-%m")
        if date in seen:
            raise ValueError(f"Duplicate EIA monthly observation: {date}")
        if isinstance(value, bool) or not isinstance(value, (float, int)):
            raise ValueError(f"EIA observation is not a numeric price at {date}")
        number = float(value)
        if not math.isfinite(number) or number <= 0:
            raise ValueError(f"EIA Brent price must be finite and positive at {date}")
        seen.add(date)
        result.append(
            {
                "date": date,
                "value": number,
                "audit": {
                    "parser": "xls",
                    "worksheet": "Data 1",
                    "date_cell": f"A{index}",
                    "value_cell": f"B{index}",
                    "source_period": period.isoformat(),
                    "source_key": "RBRTE",
                },
            }
        )
    if [item["date"] for item in result] != sorted(seen):
        raise ValueError("EIA workbook monthly observations are not chronological")
    return result


class _Table(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self.row: list[str] = []
        self.cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self.row = []
        elif tag in {"td", "th"}:
            self.cell = []

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self.cell is not None:
            self.row.append("".join(self.cell).strip())
            self.cell = None
        elif tag == "tr" and self.row:
            self.rows.append(self.row)
            self.row = []


def parse_table(body: bytes) -> tuple[dict[str, float], str]:
    text = body.decode("utf-8")
    if TITLE not in " ".join(text.split()):
        raise ValueError("The independent EIA table has the wrong series title")
    parser = _Table()
    parser.feed(text)
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    if not any(row[-12:] == months for row in parser.rows):
        raise ValueError("EIA table month headers are missing or reordered")
    values = {}
    for row in parser.rows:
        if len(row) != 13 or not re.fullmatch(r"\d{4}", row[0]):
            continue
        for month, text_value in enumerate(row[1:], 1):
            if not text_value or text_value in {"-", "--", "NA", "W"}:
                continue
            value = float(text_value)
            period = f"{row[0]}-{month:02d}"
            if period in values or not math.isfinite(value) or value <= 0:
                raise ValueError(f"Invalid or duplicate independent EIA table price: {period}")
            values[period] = value
    release = re.search(r"(?<!Next )Release Date:\s*(\d{1,2}/\d{1,2}/\d{4})", text)
    if not values or release is None:
        raise ValueError("Independent EIA table has no finite observations or release date")
    return values, datetime.strptime(release[1], "%m/%d/%Y").date().isoformat()


def audit(rows: list[dict[str, Any]], table: dict[str, float]) -> dict[str, Any]:
    workbook = {row["date"]: row for row in rows}
    if not workbook or set(workbook) != set(table):
        raise ValueError("EIA workbook and independent table have different observation periods")
    differences = {period: abs(row["value"] - table[period]) for period, row in workbook.items()}
    if any(differences.values()):
        raise ValueError("EIA workbook differs from its independently parsed published table")
    dates = ["1999-01", "2020-04", max(workbook)]
    if any(period not in workbook for period in dates):
        raise ValueError("The required three EIA audit dates are absent")
    return {
        "passed": True,
        "observations_compared": len(rows),
        "maximum_absolute_difference": max(differences.values()),
        "independent_format": "EIA published HTML year/month table versus legacy XLS cells",
        "table_url": TABLE_URL,
        "workbook_url": WORKBOOK_URL,
        "audited_dates": [
            {
                "date": period,
                "workbook_value": workbook[period]["value"],
                "official_table_value": table[period],
                "workbook_cell": workbook[period]["audit"]["value_cell"],
            }
            for period in dates
        ],
    }
