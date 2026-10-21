"""Offline fixtures for OECD membership, definitions and raw-observation provenance."""

import csv
import io
from typing import Any

import pytest

from macrolab.data.sources.oecd import parse_countries, parse_structure, standardise_csv

STRUCTURE_NS = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"
COMMON_NS = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common"


def country_fixture(*, membership: str | None = "USA+DEU") -> bytes:
    def code(identifier: str, name: str, rule: str | None = None) -> str:
        annotation = ""
        if rule is not None:
            annotation = (
                "<c:Annotations><c:Annotation><c:AnnotationType>COMP_RULE</c:AnnotationType>"
                f"<c:AnnotationTitle>{rule}</c:AnnotationTitle></c:Annotation></c:Annotations>"
            )
        return (
            f'<s:Code id="{identifier}">{annotation}<c:Name xml:lang="en">{name}</c:Name></s:Code>'
        )

    codes = "".join(
        [
            code("USA", "United States"),
            code("DEU", "Germany"),
            code("IND", "India"),
            code("OECD00", "OECD (evolving composition)", membership),
            code("EA21", "Euro area", "DEU"),
            code("EU27_2020", "European Union", "DEU"),
            code("OECDA", "OECD America", "USA"),
            code("OECDE", "OECD Europe", "DEU"),
        ]
    )
    return (
        f'<Root xmlns:s="{STRUCTURE_NS}" xmlns:c="{COMMON_NS}">'
        f'<s:Codelist id="CL_AREA" agencyID="OECD" version="fixture">{codes}</s:Codelist></Root>'
    ).encode()


def test_membership_uses_current_composition_and_excludes_other_geographic_codes() -> None:
    countries = parse_countries(country_fixture(), raw_path="data/raw/OECD/fixture.bin")
    assert {country["iso3"] for country in countries} == {"USA", "DEU", "EA"}
    germany = next(country for country in countries if country["iso3"] == "DEU")
    assert germany["monetary_union"] == "EA"
    assert germany["oecd_region"] == "OECD Europe"
    assert germany["membership_raw_path"] == "data/raw/OECD/fixture.bin"
    changed = parse_countries(country_fixture(membership="USA+DEU+IND"))
    assert {country["iso3"] for country in changed} == {"USA", "DEU", "IND", "EA"}


def test_missing_composition_is_an_error_not_a_hardcoded_fallback() -> None:
    with pytest.raises(ValueError, match="no explicit composition"):
        parse_countries(country_fixture(membership=None))


def test_structure_resolves_dimension_order_and_exact_codelist_version() -> None:
    xml = f'''<Root xmlns:s="{STRUCTURE_NS}" xmlns:c="{COMMON_NS}">
      <s:DataStructure><s:DataStructureComponents><s:DimensionList>
        <s:Dimension id="UNIT_MEASURE" position="2"><s:LocalRepresentation><s:Enumeration>
          <Ref agencyID="OECD" id="CL_UNIT" version="2"/>
        </s:Enumeration></s:LocalRepresentation></s:Dimension>
        <s:Dimension id="REF_AREA" position="1"><s:LocalRepresentation><s:Enumeration>
          <Ref agencyID="OECD" id="CL_AREA" version="1"/>
        </s:Enumeration></s:LocalRepresentation></s:Dimension>
      </s:DimensionList></s:DataStructureComponents></s:DataStructure>
      <s:Codelist id="CL_UNIT" agencyID="OECD" version="1">
        <s:Code id="IX"><c:Name xml:lang="en">Wrong version</c:Name></s:Code>
      </s:Codelist>
      <s:Codelist id="CL_UNIT" agencyID="OECD" version="2">
        <s:Code id="IX"><c:Name xml:lang="en">Index</c:Name></s:Code>
      </s:Codelist>
      <s:Codelist id="CL_AREA" agencyID="OECD" version="1">
        <s:Code id="USA"><c:Name xml:lang="en">United States</c:Name></s:Code>
      </s:Codelist>
    </Root>'''
    structure = parse_structure(xml.encode())
    assert structure["dimensions"] == ["REF_AREA", "UNIT_MEASURE"]
    assert structure["labels"]["UNIT_MEASURE"]["IX"] == "Index"


DIMENSIONS = [
    "REF_AREA",
    "FREQ",
    "METHODOLOGY",
    "MEASURE",
    "UNIT_MEASURE",
    "EXPENDITURE",
    "ADJUSTMENT",
]


def csv_row(**changes: str) -> dict[str, str]:
    return {
        "DATAFLOW": "FIXTURE",
        "REF_AREA": "USA",
        "FREQ": "M",
        "METHODOLOGY": "N",
        "MEASURE": "CPI",
        "UNIT_MEASURE": "IX",
        "EXPENDITURE": "_T",
        "ADJUSTMENT": "S",
        "TIME_PERIOD": "2001-01",
        "OBS_VALUE": "12.345",
        "UNIT_MULT": "3",
        "BASE_PER": "2015",
        "OBS_STATUS": "P",
        **changes,
    }


def convert(
    *observations: dict[str, str], ea_eu_member: bool | None = True
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(csv_row()))
    writer.writeheader()
    writer.writerows(observations)
    dataset = {"id": "fixture", "flow": "FIXTURE", "title": "Synthetic fixture"}
    mapping = {
        "concept_id": "cpi",
        "selector": {"MEASURE": "CPI", "UNIT_MEASURE": "IX"},
        "methodology_by_eu": True,
        "price_basis": "price_index",
        "definition": "Fixture only",
    }
    countries = [
        {"iso3": "USA", "eu_member": False},
        {"iso3": "DEU", "eu_member": True},
        {"iso3": "EA", "eu_member": ea_eu_member, "current_euro_area_code": "EA21"},
    ]
    return standardise_csv(
        buffer.getvalue().encode(),
        dataset,
        [mapping],
        {"dimensions": DIMENSIONS, "labels": {"UNIT_MEASURE": {"IX": "Index"}}},
        countries,
        source_url="https://sdmx.oecd.org/fixture",
        raw_path="data/raw/OECD/fixture.bin",
    )


def test_source_value_multiplier_and_all_identifying_dimensions_are_preserved() -> None:
    original = csv_row()
    rows, issues = convert(original)
    assert not issues
    row = rows[0]
    assert row["value"] == 12.345
    assert row["unit_mult"] == 3
    assert row["base_year"] == "2015"
    assert row["sa_flag"] == "SA"
    assert row["audit"]["selector"] == {
        "DATAFLOW": "FIXTURE",
        **{key: original[key] for key in DIMENSIONS},
    }
    assert row["audit"]["source_period"] == original["TIME_PERIOD"]
    assert row["raw_path"] == "data/raw/OECD/fixture.bin"


def test_eu_hicp_requirement_rejects_national_cpi_without_silent_fallback() -> None:
    rows, _ = convert(
        csv_row(REF_AREA="DEU", METHODOLOGY="N"),
        csv_row(REF_AREA="DEU", METHODOLOGY="HICP", ADJUSTMENT="N"),
        csv_row(REF_AREA="USA", METHODOLOGY="HICP"),
    )
    assert len(rows) == 1
    assert rows[0]["country"] == "DEU"
    assert rows[0]["audit"]["selector"]["METHODOLOGY"] == "HICP"
    assert rows[0]["sa_flag"] == "NSA"
    assert "not_seasonally_adjusted" in rows[0]["flags"]


@pytest.mark.parametrize(
    "changes", [{"OBS_VALUE": "NaN"}, {"OBS_VALUE": ".."}, {"TIME_PERIOD": "bad"}]
)
def test_invalid_observations_are_counted_and_not_published(changes: dict[str, str]) -> None:
    rows, issues = convert(csv_row(**changes))
    assert rows == []
    assert issues[0]["count"] == 1
    assert issues[0]["code"] == "invalid_source_observation"


def test_aggregate_compositions_remain_distinct_candidates() -> None:
    rows, _ = convert(
        csv_row(REF_AREA="EA20", METHODOLOGY="HICP"),
        csv_row(REF_AREA="EA21", METHODOLOGY="HICP"),
    )
    assert len({row["source_series_id"] for row in rows}) == 2
    older = next(row for row in rows if row["source_geo"] == "EA20")
    current = next(row for row in rows if row["source_geo"] == "EA21")
    assert "aggregate_composition_differs_from_current_euro_area" in older["flags"]
    assert older["candidate_priority"] > current["candidate_priority"]


def test_special_adjustment_and_missing_multiplier_are_explicit() -> None:
    rows, _ = convert(csv_row(ADJUSTMENT="AA", UNIT_MULT=""))
    assert rows[0]["source_adjustment"] == "AA"
    assert rows[0]["sa_flag"] == "NA"
    assert "amplitude_adjusted" in rows[0]["flags"]
    assert rows[0]["source_unit_mult"] == ""
    assert rows[0]["unit_mult"] == 0
    assert "unit_multiplier_not_reported" in rows[0]["flags"]


@pytest.mark.parametrize("eu_member", [False, None])
def test_euro_area_always_requires_hicp_even_if_enrichment_loses_eu_flag(
    eu_member: bool | None,
) -> None:
    rows, _ = convert(
        csv_row(REF_AREA="EA20", METHODOLOGY="N"),
        csv_row(REF_AREA="EA20", METHODOLOGY="HICP"),
        ea_eu_member=eu_member,
    )
    assert len(rows) == 1
    assert rows[0]["country"] == "EA"
    assert rows[0]["methodology"] == "HICP"
    assert "HICP" in rows[0]["flags"]
