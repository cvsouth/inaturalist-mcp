"""Tests for the iNaturalist MCP server.

Uses mocked HTTP responses to avoid hitting the real API during tests.
"""

from unittest.mock import AsyncMock, patch

import pytest

from inaturalist_mcp.server import (
    _format_observation,
    _format_place,
    _format_species_count,
    _format_taxon,
    get_nearby_places,
    get_similar_species,
    get_species_counts,
    get_taxon,
    inaturalist_search,
    search_observations,
    search_places,
    search_projects,
    search_taxa,
)

# ---- Fixtures ----

MOCK_OBSERVATION = {
    "id": 12345,
    "taxon": {
        "name": "Ornithorhynchus anatinus",
        "preferred_common_name": "Platypus",
    },
    "user": {"login": "naturelover"},
    "observed_on_details": {"date": "2025-03-15"},
    "place_guess": "Melbourne, Australia",
    "quality_grade": "research",
    "photos": [{"url": "https://example.com/photo/square.jpg"}],
}

MOCK_TAXON = {
    "id": 43236,
    "name": "Ornithorhynchus anatinus",
    "preferred_common_name": "Platypus",
    "rank": "species",
    "observations_count": 4000,
    "ancestors": [
        {"name": "Mammalia", "preferred_common_name": "Mammals"},
        {"name": "Monotremata", "preferred_common_name": "Monotremes"},
    ],
    "conservation_status": {"status_name": "Least Concern"},
    "wikipedia_summary": "The platypus is a <b>semiaquatic</b> mammal.",
    "default_photo": {"medium_url": "https://example.com/platypus.jpg"},
}

MOCK_PLACE = {
    "id": 10211,
    "name": "Yellowstone National Park",
    "display_name": "Yellowstone National Park, US, WY",
    "admin_level": 100,
    "bounding_box_geojson": {
        "coordinates": [
            [[-111.16, 44.13], [-109.82, 44.13], [-109.82, 45.11], [-111.16, 45.11], [-111.16, 44.13]]
        ]
    },
}


def mock_api(return_value):
    """Decorator to mock _api_get with a fixed return value."""
    return patch("inaturalist_mcp.server._api_get", new_callable=AsyncMock, return_value=return_value)


# ---- Unit tests for formatters ----


def test_format_observation():
    result = _format_observation(MOCK_OBSERVATION)
    assert "Platypus" in result
    assert "Ornithorhynchus anatinus" in result
    assert "naturelover" in result
    assert "2025-03-15" in result
    assert "Melbourne" in result
    assert "research" in result
    assert "https://www.inaturalist.org/observations/12345" in result
    assert "medium" in result  # photo URL upgraded from square


def test_format_observation_no_photos():
    obs = {**MOCK_OBSERVATION, "photos": []}
    result = _format_observation(obs)
    assert "Photo:" not in result


def test_format_observation_missing_taxon():
    obs = {**MOCK_OBSERVATION, "taxon": None}
    result = _format_observation(obs)
    assert "Unknown" in result


def test_format_species_count():
    item = {"taxon": MOCK_TAXON, "count": 150}
    result = _format_species_count(item)
    assert "Platypus" in result
    assert "150 observations" in result
    assert "platypus.jpg" in result


def test_format_taxon_basic():
    result = _format_taxon(MOCK_TAXON)
    assert "Platypus" in result
    assert "species" in result
    assert "43236" in result


def test_format_taxon_detailed():
    result = _format_taxon(MOCK_TAXON, detailed=True)
    assert "Mammals" in result
    assert "Monotremes" in result
    assert "Least Concern" in result
    assert "semiaquatic" in result
    assert "<b>" not in result  # HTML stripped
    assert "platypus.jpg" in result


def test_format_place():
    result = _format_place(MOCK_PLACE)
    assert "Yellowstone National Park, US, WY" in result
    assert "10211" in result
    assert "admin level 100" in result
    assert "44.13" in result


def test_format_place_minimal():
    result = _format_place({"id": 1, "name": "Test"})
    assert "Test" in result
    assert "1" in result


# ---- Integration tests with mocked _api_get ----


@pytest.mark.asyncio
async def test_search_observations_by_coords():
    with mock_api({"total_results": 1, "results": [MOCK_OBSERVATION]}):
        result = await search_observations(lat=-33.86, lng=151.21, radius=10)
    assert "Platypus" in result
    assert "1 observations" in result


@pytest.mark.asyncio
async def test_search_observations_no_results():
    with mock_api({"total_results": 0, "results": []}):
        result = await search_observations(lat=0, lng=0)
    assert "No observations found" in result


@pytest.mark.asyncio
async def test_search_observations_place_name():
    """Test that place_name resolves to place_id then searches."""
    call_count = 0

    async def side_effect(path, params=None):
        nonlocal call_count
        call_count += 1
        if "/places/autocomplete" in path:
            return {"results": [{"id": 6803}]}
        return {"total_results": 1, "results": [MOCK_OBSERVATION]}

    with patch("inaturalist_mcp.server._api_get", side_effect=side_effect):
        result = await search_observations(place_name="New Zealand")
    assert "Platypus" in result
    assert call_count == 2  # place resolve + observation search


@pytest.mark.asyncio
async def test_search_observations_place_not_found():
    with mock_api({"results": []}):
        result = await search_observations(place_name="Nonexistentplace")
    assert "Could not find a place" in result


@pytest.mark.asyncio
async def test_search_observations_rate_limited():
    with mock_api({"error": "Rate limited by iNaturalist. Please wait a moment and try again."}):
        result = await search_observations(lat=0, lng=0)
    assert "Rate limited" in result


@pytest.mark.asyncio
async def test_search_observations_taxon_name():
    """Test that taxon_name resolves to taxon_id then searches."""
    async def side_effect(path, params=None):
        if "/taxa/autocomplete" in path:
            return {"results": [{"id": 43236}]}
        return {"total_results": 1, "results": [MOCK_OBSERVATION]}

    with patch("inaturalist_mcp.server._api_get", side_effect=side_effect):
        result = await search_observations(taxon_name="Platypus")
    assert "Platypus" in result


@pytest.mark.asyncio
async def test_search_observations_with_dates():
    with mock_api({"total_results": 1, "results": [MOCK_OBSERVATION]}) as mock:
        await search_observations(lat=0, lng=0, d1="2025-01-01", d2="2025-12-31")
    call_args = mock.call_args
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("params", {})
    assert params.get("d1") == "2025-01-01"
    assert params.get("d2") == "2025-12-31"


@pytest.mark.asyncio
async def test_get_species_counts():
    with mock_api({
        "total_results": 2,
        "results": [
            {"taxon": MOCK_TAXON, "count": 500},
            {"taxon": {**MOCK_TAXON, "preferred_common_name": "Echidna", "name": "Tachyglossus"}, "count": 200},
        ],
    }):
        result = await get_species_counts(lat=-33.86, lng=151.21, iconic_taxa="Mammalia")
    assert "2 species" in result
    assert "500" in result


@pytest.mark.asyncio
async def test_get_species_counts_no_results():
    with mock_api({"total_results": 0, "results": []}):
        result = await get_species_counts(place_id=99999)
    assert "No species found" in result


@pytest.mark.asyncio
async def test_search_taxa():
    with mock_api({"results": [MOCK_TAXON]}):
        result = await search_taxa(q="platypus")
    assert "Platypus" in result
    assert "43236" in result


@pytest.mark.asyncio
async def test_search_taxa_no_results():
    with mock_api({"results": []}):
        result = await search_taxa(q="xyznonexistent")
    assert "No taxa found" in result


@pytest.mark.asyncio
async def test_get_taxon():
    with mock_api({"results": [MOCK_TAXON]}):
        result = await get_taxon(taxon_id=43236)
    assert "Platypus" in result
    assert "Least Concern" in result
    assert "semiaquatic" in result


@pytest.mark.asyncio
async def test_get_taxon_not_found():
    with mock_api({"results": []}):
        result = await get_taxon(taxon_id=999999999)
    assert "No taxon found" in result


@pytest.mark.asyncio
async def test_search_places():
    with mock_api({"results": [MOCK_PLACE]}):
        result = await search_places(q="Yellowstone")
    assert "Yellowstone" in result
    assert "10211" in result


@pytest.mark.asyncio
async def test_search_places_no_results():
    with mock_api({"results": []}):
        result = await search_places(q="xyznonexistent")
    assert "No places found" in result


@pytest.mark.asyncio
async def test_get_nearby_places():
    with mock_api({"results": {"standard": [MOCK_PLACE], "community": []}}):
        result = await get_nearby_places(lat=44.46, lng=-110.83)
    assert "Standard places" in result
    assert "Yellowstone" in result


@pytest.mark.asyncio
async def test_get_nearby_places_empty():
    with mock_api({"results": {"standard": [], "community": []}}):
        result = await get_nearby_places(lat=0, lng=0)
    assert "No places found" in result


@pytest.mark.asyncio
async def test_search_projects():
    with mock_api({
        "total_results": 1,
        "results": [{
            "id": 100,
            "title": "Sydney Birds",
            "slug": "sydney-birds",
            "description": "Tracking birds in Sydney",
            "observations_count": 1500,
            "members_count": 42,
        }],
    }):
        result = await search_projects(q="birds Sydney")
    assert "Sydney Birds" in result
    assert "inaturalist.org/projects/sydney-birds" in result
    assert "1500 observations" in result
    assert "42 members" in result


@pytest.mark.asyncio
async def test_search_projects_no_results():
    with mock_api({"total_results": 0, "results": []}):
        result = await search_projects(q="xyznonexistent")
    assert "No projects found" in result


@pytest.mark.asyncio
async def test_get_similar_species():
    with mock_api({"results": [{"taxon": MOCK_TAXON, "count": 50}]}):
        result = await get_similar_species(taxon_id=43236)
    assert "Platypus" in result
    assert "50 observations" in result


@pytest.mark.asyncio
async def test_get_similar_species_no_results():
    with mock_api({"results": []}):
        result = await get_similar_species(taxon_id=999999)
    assert "No similar species" in result


@pytest.mark.asyncio
async def test_inaturalist_search():
    with mock_api({
        "total_results": 2,
        "results": [
            {"type": "Taxon", "record": MOCK_TAXON},
            {"type": "Place", "record": MOCK_PLACE},
        ],
    }):
        result = await inaturalist_search(q="platypus")
    assert "[Taxon]" in result
    assert "[Place]" in result
    assert "Platypus" in result
    assert "Yellowstone" in result


@pytest.mark.asyncio
async def test_inaturalist_search_user_type():
    with mock_api({
        "total_results": 1,
        "results": [
            {"type": "User", "record": {"login": "testuser", "name": "Test User", "observations_count": 500}},
        ],
    }):
        result = await inaturalist_search(q="testuser")
    assert "[User]" in result
    assert "@testuser" in result
    assert "500 observations" in result


@pytest.mark.asyncio
async def test_inaturalist_search_no_results():
    with mock_api({"total_results": 0, "results": []}):
        result = await inaturalist_search(q="xyznonexistent")
    assert "No results found" in result


# ---- Error handling tests ----


@pytest.mark.asyncio
async def test_api_http_error():
    """HTTP errors should return friendly messages, not tracebacks."""
    with mock_api({"error": "iNaturalist API error: 500"}):
        result = await search_taxa(q="test")
    assert "API error" in result


@pytest.mark.asyncio
async def test_api_network_error():
    """Network errors should return friendly messages."""
    with mock_api({"error": "Network error connecting to iNaturalist: connection refused"}):
        result = await search_places(q="test")
    assert "Network error" in result


# ---- Edge case tests ----


def test_format_observation_null_observed_on_details():
    """observed_on_details can be explicitly None."""
    obs = {**MOCK_OBSERVATION, "observed_on_details": None, "observed_on": "2025-06-01"}
    result = _format_observation(obs)
    assert "2025-06-01" in result


def test_format_project_html_in_description():
    """HTML should be stripped before truncation to avoid broken tags."""
    from inaturalist_mcp.server import _format_project
    proj = {
        "id": 1,
        "title": "Test",
        "slug": "test",
        "description": "<p>" + "a" * 300 + "</p>",
    }
    result = _format_project(proj)
    assert "<p>" not in result
    assert "..." in result  # truncated after stripping
    assert len(result) < 500  # reasonable length


def test_format_species_count_null_default_photo():
    """default_photo can be explicitly None."""
    item = {"taxon": {**MOCK_TAXON, "default_photo": None}, "count": 10}
    result = _format_species_count(item)
    assert "10 observations" in result
    assert "Photo:" not in result


@pytest.mark.asyncio
async def test_search_observations_place_resolve_error():
    """API errors during place resolution should propagate, not show 'place not found'."""
    with mock_api({"error": "Rate limited by iNaturalist. Please wait a moment and try again."}):
        result = await search_observations(place_name="Australia")
    assert "Rate limited" in result
    assert "Could not find" not in result


@pytest.mark.asyncio
async def test_search_observations_taxon_resolve_error():
    """API errors during taxon resolution should propagate, not show 'taxon not found'."""
    with mock_api({"error": "Network error connecting to iNaturalist: connection refused"}):
        result = await search_observations(taxon_name="Platypus")
    assert "Network error" in result
    assert "Could not find" not in result


@pytest.mark.asyncio
async def test_get_species_counts_place_resolve_error():
    """API errors during place resolution in species counts should propagate."""
    with mock_api({"error": "Rate limited by iNaturalist. Please wait a moment and try again."}):
        result = await get_species_counts(place_name="Australia")
    assert "Rate limited" in result


def test_format_taxon_detailed_null_default_photo():
    """default_photo can be explicitly None in detailed view."""
    taxon = {**MOCK_TAXON, "default_photo": None}
    result = _format_taxon(taxon, detailed=True)
    assert "Platypus" in result
    assert "Photo:" not in result
