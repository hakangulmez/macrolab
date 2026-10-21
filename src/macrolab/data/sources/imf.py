"""IMF WEO actual fiscal ratios and monthly-average national-currency/USD fallback."""

from __future__ import annotations

from typing import Any

from macrolab.data.sources.bis import fetch_issue, finite, make_row, read_sdmx
from macrolab.data.sources.http import SourceClient

FISCAL_INDICATORS = {"GGXWDG_NGDP": "gov_debt", "GGXCNL_NGDP": "gov_balance"}


def normalise_imf(
    body: bytes, fetched: Any, countries: set[str], kind: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw_rows, parser = read_sdmx(body)
    rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    missing_cutoff: set[tuple[str, str]] = set()
    for raw in raw_rows:
        country = raw.get("COUNTRY", "")
        if (
            country not in countries
            or not raw.get("TIME_PERIOD")
            or not finite(raw.get("OBS_VALUE"))
        ):
            continue
        if kind == "fiscal":
            indicator = raw.get("INDICATOR", "")
            if indicator not in FISCAL_INDICATORS or raw.get("FREQUENCY") != "A":
                continue
            if raw.get("UNIT") != "PT" or "Percent of GDP" not in raw.get("SERIES_NAME", ""):
                continue
            cutoff = raw.get("LATEST_ACTUAL_ANNUAL_DATA", "")
            if not cutoff.isdigit():
                missing_cutoff.add((country, indicator))
                continue
            if int(raw["TIME_PERIOD"]) > int(cutoff):
                continue
            concept = FISCAL_INDICATORS[indicator]
            selector = {key: raw[key] for key in ("COUNTRY", "INDICATOR", "FREQUENCY")}
            row = make_row(
                country=country,
                concept=concept,
                source="IMF",
                series_id="IMF.RES:WEO(9.0.0)." + ".".join(selector.values()),
                raw=raw,
                fetched=fetched,
                parser=parser,
                selector=selector,
                unit="percent_gdp",
                frequency="A",
                sa_flag="UNKNOWN",
                price_basis="nominal",
                flags=[
                    "seasonal_adjustment_unknown",
                    "weo_actual_boundary_enforced",
                    "national_fiscal_definitions_may_differ",
                ],
            )
            row["audit"]["actual_year_cutoff"] = int(cutoff)
        else:
            if (
                raw.get("INDICATOR") != "XDC_USD"
                or raw.get("TYPE_OF_TRANSFORMATION") != "PA_RT"
                or raw.get("FREQUENCY") != "M"
            ):
                continue
            selector = {
                key: raw[key]
                for key in ("COUNTRY", "INDICATOR", "TYPE_OF_TRANSFORMATION", "FREQUENCY")
            }
            row = make_row(
                country=country,
                concept="fx_usd",
                source="IMF",
                series_id="IMF.STA:ER(4.0.1)." + ".".join(selector.values()),
                raw=raw,
                fetched=fetched,
                parser=parser,
                selector=selector,
                unit="national_currency_per_USD",
                frequency="M",
                sa_flag="UNKNOWN",
                price_basis="nominal",
                flags=[
                    "seasonal_adjustment_unknown",
                    "monthly_average",
                    "source_currency_history_as_published",
                ],
            )
        rows.append(row)
    for country, indicator in sorted(missing_cutoff):
        issues.append(
            {
                "source": "IMF",
                "code": "actual_boundary_unavailable",
                "country": country,
                "indicator": indicator,
                "reason": "Forecasts cannot be separated reliably; series omitted",
            }
        )
    return rows, issues


def fetch_imf(client: SourceClient, countries: list[dict[str, Any]]) -> dict[str, Any]:
    codes = sorted(str(country["iso3"]) for country in countries if country["iso3"] != "EA")
    rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for offset in range(0, len(codes), 8):
        chunk = codes[offset : offset + 8]
        country_key = "+".join(chunk)
        for kind, flow, key in [
            ("fiscal", "IMF.RES,WEO,9.0.0", f"{country_key}.GGXWDG_NGDP+GGXCNL_NGDP.A"),
            ("fx", "IMF.STA,ER,4.0.1", f"{country_key}.XDC_USD.PA_RT.M"),
        ]:
            request_id = f"imf_{kind}_{offset}"
            url = f"https://api.imf.org/external/sdmx/2.1/data/{flow}/{key}?startPeriod=1950"
            fetched = client.fetch("IMF", request_id, url, "text/csv")
            if fetched.record.status != 200 or fetched.body is None:
                issues.append(fetch_issue("IMF", request_id, fetched))
                continue
            parsed, problems = normalise_imf(fetched.body, fetched, set(chunk), kind)
            rows.extend(parsed)
            issues.extend(problems)
    for country in countries:
        for concept in ["gov_debt", "gov_balance", "fx_usd"]:
            if not any(
                row["country"] == country["iso3"] and row["concept_id"] == concept for row in rows
            ):
                issues.append(
                    {
                        "source": "IMF",
                        "code": "series_not_returned",
                        "country": country["iso3"],
                        "concept_id": concept,
                        "reason": (
                            "No verified actual series in selected flow; "
                            "use source-priority fallback"
                        ),
                    }
                )
    return {"rows": rows, "issues": issues}
