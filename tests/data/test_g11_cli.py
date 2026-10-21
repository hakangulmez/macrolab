"""Synthetic CLI metadata tests; no confidence substitution or network requests."""

from __future__ import annotations

import csv
import io
from typing import Any

import pytest

from macrolab.data.sources.g11_cli import load_configuration, metadata_evidence, parse_cli


def observation(**changes: str) -> dict[str, str]:
    return {
        "DATAFLOW": "OECD.SDD.STES:DSD_STES@DF_CLI(4.1)",
        "REF_AREA": "USA",
        "FREQ": "M",
        "MEASURE": "LI",
        "UNIT_MEASURE": "IX",
        "ACTIVITY": "_Z",
        "ADJUSTMENT": "AA",
        "TRANSFORMATION": "IX",
        "TIME_HORIZ": "_Z",
        "METHODOLOGY": "H",
        "TIME_PERIOD": "2026-09",
        "OBS_VALUE": "101.25",
        "UNIT_MULT": "0",
        "OBS_STATUS": "A",
        "BASE_PER": "",
        **changes,
    }


def parse(*observations: dict[str, str]) -> dict[str, Any]:
    configuration = load_configuration()
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(observation()))
    writer.writeheader()
    writer.writerows(observations)
    structure = {
        "dimensions": configuration["dataset"]["dimensions"],
        "labels": configuration["mapping"]["verified_code_labels"],
    }
    return parse_cli(
        buffer.getvalue().encode(),
        structure,
        configuration,
        [{"iso3": "USA"}, {"iso3": "AUT"}, {"iso3": "EA", "current_euro_area_code": "EA21"}],
        raw_path="data/raw/OECD/synthetic_cli.csv",
    )


def test_only_headline_cli_is_selected_with_all_raw_dimensions_preserved() -> None:
    original = observation()
    result = parse(
        original,
        observation(ADJUSTMENT="NOR", OBS_VALUE="102"),
        observation(ADJUSTMENT="TR", TRANSFORMATION="GY", OBS_VALUE="3.0"),
    )

    assert len(result["rows"]) == 1
    row = result["rows"][0]
    assert row["concept_id"] == "cli"
    assert row["value"] == 101.25
    assert row["unit"] == "IX" and row["unit_mult"] == 0
    assert row["sa_flag"] == "NA"
    assert "amplitude_adjusted" in row["flags"]
    assert row["raw_path"] == "data/raw/OECD/synthetic_cli.csv"
    assert row["audit"]["source_period"] == "2026-09"
    assert row["audit"]["selector"]["METHODOLOGY"] == "H"
    assert row["audit"]["selector"]["ADJUSTMENT"] == "AA"
    assert result["mapping_evidence"]["all_variant_observations"] == 3


def test_national_variant_is_reported_as_alternative_not_silently_substituted() -> None:
    result = parse(observation(REF_AREA="AUT", METHODOLOGY="N"))

    assert not result["rows"]
    austria = next(issue for issue in result["issues"] if issue["country"] == "AUT")
    assert austria["code"] == "cli_headline_definition_not_observed"
    assert "Other LI variants exist" in austria["detail"]
    assert result["mapping_evidence"]["observed_methodologies"] == ["N"]


def test_unavailable_country_is_distinguished_from_present_alternative_variant() -> None:
    result = parse(observation())
    missing = {issue["country"]: issue for issue in result["issues"]}

    assert set(missing) == {"AUT", "EA"}
    assert {issue["code"] for issue in missing.values()} == {
        "cli_not_observed_in_current_oecd_flow"
    }
    assert all("not cessation" in issue["detail"] for issue in missing.values())
    assert all(issue["reason_code"] == issue["code"] for issue in missing.values())


def test_non_euro_area_group_is_not_used_as_euro_area_cli() -> None:
    result = parse(observation(REF_AREA="G4E"))

    assert not result["rows"]
    euro_area = next(issue for issue in result["issues"] if issue["country"] == "EA")
    assert euro_area["code"] == "cli_not_observed_in_current_oecd_flow"


@pytest.mark.parametrize("measure", ["BCICP", "CCICP", "RS"])
def test_confidence_or_reference_series_cannot_be_mistaken_for_cli(measure: str) -> None:
    with pytest.raises(ValueError, match="outside the requested measure"):
        parse(observation(MEASURE=measure))


def metadata(version: str = "4.1", *, include_scope: bool = True) -> bytes:
    scope = (
        "CLIs are calculated for G20 countries plus Spain and 5 zone aggregates."
        if include_scope
        else "Synthetic description without a coverage statement."
    )
    return (
        '<Root xmlns:s="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure" '
        'xmlns:c="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common">'
        f'<s:Dataflow id="DSD_STES@DF_CLI" agencyID="OECD.SDD.STES" version="{version}">'
        f'<c:Description xml:lang="en">{scope}</c:Description>'
        "</s:Dataflow></Root>"
    ).encode()


def test_coverage_statement_is_taken_from_current_metadata_without_inference() -> None:
    dataset = load_configuration()["dataset"]
    actual = metadata_evidence(metadata(), dataset)
    absent = metadata_evidence(metadata(include_scope=False), dataset)

    assert actual["official_coverage_statement"] == (
        "CLIs are calculated for G20 countries plus Spain and 5 zone aggregates."
    )
    assert absent["official_coverage_statement"] is None


def test_unverified_flow_version_requires_review_instead_of_reusing_old_mapping() -> None:
    with pytest.raises(ValueError, match="differs from the verified"):
        metadata_evidence(metadata("5.0"), load_configuration()["dataset"])
