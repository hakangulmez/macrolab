"""Source-boundary and mapping failures use synthetic records; no network is required."""

import csv
import io
from datetime import date
from types import SimpleNamespace

import pytest

from macrolab.data.sources.v1 import hicp_rows, pcps_rows, policy_rows


def response(rows):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=sorted({k for r in rows for k in r}))
    writer.writeheader()
    writer.writerows(rows)
    return SimpleNamespace(
        body=stream.getvalue().encode(),
        record=SimpleNamespace(
            status=200,
            error=None,
            url="https://data-api.ecb.europa.eu/service/data/test",
            raw_path="data/raw/synthetic.bin",
            retrieved_utc="2026-10-21T00:00:00Z",
        ),
    )


def commodity():
    return [
        {
            "INDICATOR": c,
            "COUNTRY": "G001",
            "DATA_TRANSFORMATION": "INDEX",
            "FREQUENCY": "M",
            "SCALE": "0",
            "ACCESS_SHARING_LEVEL": "PUBLIC_OPEN",
            "ACCESS_SHARING_NOTES": "",
            "TIME_PERIOD": "1999-M01",
            "OBS_VALUE": "100",
            "LICENSE": "© International Monetary Fund Copyright. All Rights Reserved. https://www.imf.org/external/terms.htm",
        }
        for c in ("PALLFNF", "PNRG", "PNFUEL")
    ]


@pytest.mark.parametrize(
    "field,value",
    [
        ("INDICATOR", "POILBRE"),
        ("DATA_TRANSFORMATION", "INDEX_PCH"),
        ("ACCESS_SHARING_NOTES", "No redistribution"),
        ("SCALE", "3"),
        ("LICENSE", "Restricted"),
        ("OBS_VALUE", "-1"),
    ],
)
def test_pcps_rejects_unreviewed_definitions_or_rights(field, value):
    rows = commodity()
    rows[0][field] = value
    with pytest.raises(ValueError):
        pcps_rows(response(rows))


def test_pcps_only_indices_and_explicit_variants():
    rows = pcps_rows(response(commodity()))
    assert {r["variant"] for r in rows} == {"all", "energy", "nonfuel"}
    assert all(r["base_year"] == "2016" and r["value"] == 100 for r in rows)
    assert all(r["audit"]["source_period"] == "1999-M01" for r in rows)


def rate(instrument, when, value):
    return {
        "KEY": f"FM.D.U2.EUR.4F.KR.{instrument}.LEV",
        "FREQ": "D",
        "REF_AREA": "U2",
        "CURRENCY": "EUR",
        "PROVIDER_FM": "4F",
        "INSTRUMENT_FM": "KR",
        "PROVIDER_FM_ID": instrument,
        "DATA_TYPE_FM": "LEV",
        "UNIT": "PCPA",
        "TIME_PERIOD": when,
        "OBS_VALUE": str(value),
        "TITLE_COMPL": "Synthetic rate",
    }


def test_rates_select_actual_month_end_and_splice_mro_without_filling():
    raw = [rate(i, "2026-09-30", v) for i, v in (("DFR", 2), ("MRR_FR", 3))]
    raw += [
        rate("DFR", "2026-10-21", 4),
        rate("MRR_MBR", "2008-09-30", 5),
        rate("MRR_FR", "2008-10-31", 6),
        rate("DFR", "2026-08-28", 7),
    ]
    result = policy_rows(response(raw), date(2026, 10, 21))
    assert [(r["variant"], r["date"], r["value"]) for r in result] == [
        ("dfr", "2026-09", 2),
        ("mro", "2026-09", 3),
        ("mro", "2008-09", 5),
        ("mro", "2008-10", 6),
    ]
    assert result[0]["audit"]["source_period"] == "2026-09-30"


def test_overlapping_mro_tenders_fail_closed():
    raw = [rate(i, "2026-09-30", 2) for i in ("DFR", "MRR_FR", "MRR_MBR")]
    with pytest.raises(ValueError, match="overlap"):
        policy_rows(response(raw), date(2026, 10, 21))


def test_hicp_rejects_obsolete_base():
    with pytest.raises(ValueError, match="base"):
        hicp_rows(
            response(
                [
                    {
                        "KEY": "HICP.M.U2.Y.000000.4F0.INX",
                        "UNIT_INDEX_BASE": "2015 = 100",
                        "UNIT": "IX",
                    }
                ]
            )
        )
