import asyncio
import re
import time

import httpx
from mcp.server.fastmcp import FastMCP

BASE_URL = "https://api.inaturalist.org/v1"
USER_AGENT = "inaturalist-mcp/0.1.0"
MAX_REQUESTS_PER_MINUTE = 60

mcp = FastMCP("inaturalist")

# Simple rate limiter
_request_times: list[float] = []


async def _api_get(path: str, params: dict | None = None) -> dict:
    """Make a rate-limited GET request to the iNaturalist API."""
    global _request_times
    now = time.monotonic()
    _request_times = [t for t in _request_times if now - t < 60]
    if len(_request_times) >= MAX_REQUESTS_PER_MINUTE:
        wait = 60 - (now - _request_times[0])
        if wait > 0:
            await asyncio.sleep(wait)

    try:
        async with httpx.AsyncClient(
            base_url=BASE_URL,
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        ) as client:
            resp = await client.get(path, params=params)
            _request_times.append(time.monotonic())
            if resp.status_code == 429:
                return {"error": "Rate limited by iNaturalist. Please wait a moment and try again."}
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        return {"error": f"iNaturalist API error: {e.response.status_code}"}
    except httpx.RequestError as e:
        return {"error": f"Network error connecting to iNaturalist: {e}"}


async def _resolve_place_name(name: str) -> int | str | None:
    """Resolve a place name to an iNaturalist place ID. Returns error string on API failure."""
    data = await _api_get("/places/autocomplete", {"q": name, "per_page": 1})
    if "error" in data:
        return data["error"]
    results = data.get("results", [])
    if results:
        return results[0]["id"]
    return None


async def _resolve_taxon_name(name: str) -> int | str | None:
    """Resolve a taxon name to an iNaturalist taxon ID. Returns error string on API failure."""
    data = await _api_get("/taxa/autocomplete", {"q": name, "per_page": 1})
    if "error" in data:
        return data["error"]
    results = data.get("results", [])
    if results:
        return results[0]["id"]
    return None


def _format_observation(obs: dict) -> str:
    taxon = obs.get("taxon") or {}
    common = taxon.get("preferred_common_name", "Unknown")
    scientific = taxon.get("name", "Unknown")
    user = obs.get("user", {})
    observer = user.get("login", "unknown")
    date = (obs.get("observed_on_details") or {}).get("date", obs.get("observed_on", "unknown"))
    place = obs.get("place_guess", "Unknown location")
    quality = obs.get("quality_grade", "unknown")
    url = f"https://www.inaturalist.org/observations/{obs['id']}"
    photos = obs.get("photos", [])
    photo_url = photos[0]["url"].replace("square", "medium") if photos else None
    lines = [
        f"**{common}** (*{scientific}*)",
        f"  Observer: {observer} | Date: {date}",
        f"  Location: {place} | Quality: {quality}",
        f"  Link: {url}",
    ]
    if photo_url:
        lines.append(f"  Photo: {photo_url}")
    return "\n".join(lines)


def _format_species_count(item: dict) -> str:
    taxon = item.get("taxon", {})
    common = taxon.get("preferred_common_name", "Unknown")
    scientific = taxon.get("name", "Unknown")
    count = item.get("count", 0)
    photo = taxon.get("default_photo") or {}
    photo_url = photo.get("medium_url") or photo.get("url", "")
    line = f"**{common}** (*{scientific}*) — {count} observations"
    if photo_url:
        line += f"\n  Photo: {photo_url}"
    return line


def _format_taxon(taxon: dict, detailed: bool = False) -> str:
    common = taxon.get("preferred_common_name", "")
    scientific = taxon.get("name", "Unknown")
    rank = taxon.get("rank", "unknown")
    tid = taxon.get("id", "")
    obs_count = taxon.get("observations_count", 0)

    title = f"**{common}** (*{scientific}*)" if common else f"*{scientific}*"
    lines = [f"{title} — {rank} (ID: {tid}, {obs_count} observations)"]

    if detailed:
        # Ancestry
        ancestors = taxon.get("ancestors", [])
        if ancestors:
            chain = " > ".join(
                a.get("preferred_common_name") or a.get("name", "?") for a in ancestors
            )
            lines.append(f"  Taxonomy: {chain}")

        # Conservation status
        cs = taxon.get("conservation_status")
        if cs:
            lines.append(f"  Conservation: {cs.get('status_name', cs.get('status', 'unknown'))}")
        cslist = taxon.get("conservation_statuses", [])
        if cslist and not cs:
            statuses = ", ".join(f"{s.get('status', '?')} ({s.get('authority', '?')})" for s in cslist[:3])
            lines.append(f"  Conservation: {statuses}")

        # Wikipedia
        wp = taxon.get("wikipedia_summary")
        if wp:
            clean = re.sub(r"<[^>]+>", "", wp)
            if len(clean) > 300:
                clean = clean[:300] + "..."
            lines.append(f"  Summary: {clean}")

        # Photo
        photo = taxon.get("default_photo") or {}
        if photo:
            url = photo.get("medium_url") or photo.get("url", "")
            if url:
                lines.append(f"  Photo: {url}")

    return "\n".join(lines)


def _format_place(place: dict) -> str:
    name = place.get("display_name") or place.get("name", "Unknown")
    pid = place.get("id", "")
    admin = place.get("admin_level")
    admin_str = f" (admin level {admin})" if admin is not None else ""
    bbox = place.get("bounding_box_geojson")
    bbox_str = ""
    if bbox and bbox.get("coordinates"):
        coords = bbox["coordinates"][0]
        if len(coords) >= 3:
            lats = [c[1] for c in coords]
            lngs = [c[0] for c in coords]
            bbox_str = f"\n  Bounds: {min(lats):.2f},{min(lngs):.2f} to {max(lats):.2f},{max(lngs):.2f}"
    return f"**{name}** (ID: {pid}){admin_str}{bbox_str}"


def _format_project(proj: dict) -> str:
    title = proj.get("title", "Unknown")
    pid = proj.get("id", "")
    desc = proj.get("description", "")
    url = f"https://www.inaturalist.org/projects/{proj.get('slug', pid)}"
    lines = [f"**{title}** (ID: {pid})", f"  Link: {url}"]
    stats = []
    obs_count = proj.get("observations_count")
    if obs_count is not None:
        stats.append(f"{obs_count} observations")
    members = proj.get("members_count")
    if members is not None:
        stats.append(f"{members} members")
    if stats:
        lines.append(f"  {', '.join(stats)}")
    if desc:
        clean = re.sub(r"<[^>]+>", "", desc).strip()
        if len(clean) > 200:
            clean = clean[:200] + "..."
        if clean:
            lines.append(f"  {clean}")
    return "\n".join(lines)


# ============================================================
# Slice 1.2: Observation Search
# ============================================================

@mcp.tool()
async def search_observations(
    lat: float | None = None,
    lng: float | None = None,
    radius: int | None = None,
    place_name: str | None = None,
    place_id: int | None = None,
    taxon_name: str | None = None,
    taxon_id: int | None = None,
    d1: str | None = None,
    d2: str | None = None,
    quality_grade: str | None = None,
    iconic_taxa: str | None = None,
    page: int = 1,
    per_page: int = 20,
) -> str:
    """Search iNaturalist observations by location, species, date, and more.

    Args:
        lat: Latitude for location-based search
        lng: Longitude for location-based search
        radius: Search radius in km (use with lat/lng, default 10)
        place_name: Place name to search within (e.g. "Australia", "Yellowstone")
        place_id: iNaturalist place ID to search within
        taxon_name: Species or taxon common/scientific name to filter by
        taxon_id: iNaturalist taxon ID to filter by
        d1: Start date (YYYY-MM-DD)
        d2: End date (YYYY-MM-DD)
        quality_grade: Filter by quality: "research", "needs_id", or "casual"
        iconic_taxa: Filter by group: Aves, Mammalia, Reptilia, Amphibia, Actinopterygii, Mollusca, Arachnida, Insecta, Plantae, Fungi, etc.
        page: Page number (default 1)
        per_page: Results per page (default 20, max 200)
    """
    params: dict = {"page": page, "per_page": min(per_page, 200)}

    if lat is not None and lng is not None:
        params["lat"] = lat
        params["lng"] = lng
        params["radius"] = radius or 10

    if place_name and not place_id:
        resolved = await _resolve_place_name(place_name)
        if isinstance(resolved, str):
            return resolved
        if resolved is None:
            return f"Could not find a place matching '{place_name}'. Try a different name or use lat/lng."
        place_id = resolved
    if place_id:
        params["place_id"] = place_id

    if taxon_name and not taxon_id:
        resolved = await _resolve_taxon_name(taxon_name)
        if isinstance(resolved, str):
            return resolved
        if resolved is None:
            return f"Could not find a taxon matching '{taxon_name}'. Try a different name or use taxon_id."
        taxon_id = resolved
    if taxon_id:
        params["taxon_id"] = taxon_id

    if d1:
        params["d1"] = d1
    if d2:
        params["d2"] = d2
    if quality_grade:
        params["quality_grade"] = quality_grade
    if iconic_taxa:
        params["iconic_taxa"] = iconic_taxa

    data = await _api_get("/observations", params)
    if "error" in data:
        return data["error"]

    total = data.get("total_results", 0)
    results = data.get("results", [])
    if not results:
        return "No observations found matching your criteria."

    lines = [f"Found {total} observations (showing page {page}, {len(results)} results):\n"]
    for obs in results:
        lines.append(_format_observation(obs))
        lines.append("")

    return "\n".join(lines)


# ============================================================
# Slice 1.3: Species Counts
# ============================================================

@mcp.tool()
async def get_species_counts(
    lat: float | None = None,
    lng: float | None = None,
    radius: int | None = None,
    place_name: str | None = None,
    place_id: int | None = None,
    taxon_name: str | None = None,
    taxon_id: int | None = None,
    d1: str | None = None,
    d2: str | None = None,
    quality_grade: str | None = None,
    iconic_taxa: str | None = None,
    per_page: int = 20,
) -> str:
    """Get species observed at a location, ranked by observation count. Great for answering "what wildlife will I see here?"

    Args:
        lat: Latitude for location-based search
        lng: Longitude for location-based search
        radius: Search radius in km (use with lat/lng, default 10)
        place_name: Place name (e.g. "Kruger National Park")
        place_id: iNaturalist place ID
        taxon_name: Filter to a taxon group by name (e.g. "Birds")
        taxon_id: Filter to a taxon group by ID
        d1: Start date (YYYY-MM-DD)
        d2: End date (YYYY-MM-DD)
        quality_grade: "research", "needs_id", or "casual"
        iconic_taxa: Filter by group: Aves, Mammalia, Reptilia, Amphibia, Insecta, Plantae, Fungi, etc.
        per_page: Number of species to return (default 20, max 200)
    """
    params: dict = {"per_page": min(per_page, 200)}

    if lat is not None and lng is not None:
        params["lat"] = lat
        params["lng"] = lng
        params["radius"] = radius or 10

    if place_name and not place_id:
        resolved = await _resolve_place_name(place_name)
        if isinstance(resolved, str):
            return resolved
        if resolved is None:
            return f"Could not find a place matching '{place_name}'."
        place_id = resolved
    if place_id:
        params["place_id"] = place_id

    if taxon_name and not taxon_id:
        resolved = await _resolve_taxon_name(taxon_name)
        if isinstance(resolved, str):
            return resolved
        if resolved is None:
            return f"Could not find a taxon matching '{taxon_name}'."
        taxon_id = resolved
    if taxon_id:
        params["taxon_id"] = taxon_id

    if d1:
        params["d1"] = d1
    if d2:
        params["d2"] = d2
    if quality_grade:
        params["quality_grade"] = quality_grade
    if iconic_taxa:
        params["iconic_taxa"] = iconic_taxa

    data = await _api_get("/observations/species_counts", params)
    if "error" in data:
        return data["error"]

    total = data.get("total_results", 0)
    results = data.get("results", [])
    if not results:
        return "No species found matching your criteria."

    lines = [f"Found {total} species (showing top {len(results)}):\n"]
    for i, item in enumerate(results, 1):
        lines.append(f"{i}. {_format_species_count(item)}")
    return "\n".join(lines)


# ============================================================
# Slice 2.1: Taxa Search and Details
# ============================================================

@mcp.tool()
async def search_taxa(
    q: str,
    is_active: bool | None = None,
    rank: str | None = None,
    per_page: int = 10,
) -> str:
    """Search for species or taxa by common or scientific name.

    Args:
        q: Search query (common or scientific name, e.g. "platypus", "Ornithorhynchus")
        is_active: Only show currently accepted taxa (default: all)
        rank: Filter by taxonomic rank (species, genus, family, order, class, phylum, kingdom)
        per_page: Number of results (default 10, max 30)
    """
    params: dict = {"q": q, "per_page": min(per_page, 30)}
    if is_active is not None:
        params["is_active"] = str(is_active).lower()
    if rank:
        params["rank"] = rank

    data = await _api_get("/taxa/autocomplete", params)
    if "error" in data:
        return data["error"]

    results = data.get("results", [])
    if not results:
        return f"No taxa found matching '{q}'."

    lines = [f"Found {len(results)} taxa matching '{q}':\n"]
    for taxon in results:
        lines.append(_format_taxon(taxon))
    return "\n".join(lines)


@mcp.tool()
async def get_taxon(taxon_id: int) -> str:
    """Get detailed information about a specific taxon (species, genus, etc.) by ID.

    Args:
        taxon_id: The iNaturalist taxon ID
    """
    data = await _api_get(f"/taxa/{taxon_id}")
    if "error" in data:
        return data["error"]

    results = data.get("results", [])
    if not results:
        return f"No taxon found with ID {taxon_id}."

    return _format_taxon(results[0], detailed=True)


# ============================================================
# Slice 2.2: Places Search and Nearby
# ============================================================

@mcp.tool()
async def search_places(q: str, per_page: int = 10) -> str:
    """Search for iNaturalist places by name. Returns place IDs you can use in other tools.

    Args:
        q: Place name to search for (e.g. "Yellowstone", "Costa Rica")
        per_page: Number of results (default 10)
    """
    data = await _api_get("/places/autocomplete", {"q": q, "per_page": per_page})
    if "error" in data:
        return data["error"]

    results = data.get("results", [])
    if not results:
        return f"No places found matching '{q}'."

    lines = [f"Found {len(results)} places matching '{q}':\n"]
    for place in results:
        lines.append(_format_place(place))
    return "\n".join(lines)


@mcp.tool()
async def get_nearby_places(lat: float, lng: float) -> str:
    """Find iNaturalist places near a set of coordinates.

    Args:
        lat: Latitude
        lng: Longitude
    """
    data = await _api_get("/places/nearby", {"nelat": lat + 0.5, "nelng": lng + 0.5, "swlat": lat - 0.5, "swlng": lng - 0.5})
    if "error" in data:
        return data["error"]

    # The nearby endpoint returns {standard: [...], community: [...]}
    standard = data.get("results", {}).get("standard", [])
    community = data.get("results", {}).get("community", [])

    if not standard and not community:
        return f"No places found near ({lat}, {lng})."

    lines = []
    if standard:
        lines.append(f"**Standard places** ({len(standard)}):\n")
        for place in standard[:10]:
            lines.append(_format_place(place))
        lines.append("")
    if community:
        lines.append(f"**Community places** ({len(community)}):\n")
        for place in community[:10]:
            lines.append(_format_place(place))

    return "\n".join(lines)


# ============================================================
# Slice 3.1: Projects Search
# ============================================================

@mcp.tool()
async def search_projects(
    q: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    place_id: int | None = None,
    per_page: int = 10,
) -> str:
    """Search for iNaturalist community projects (bioblitzes, surveys, regional biodiversity projects).

    Args:
        q: Search query (e.g. "birds Sydney", "butterflies")
        lat: Latitude to find nearby projects
        lng: Longitude to find nearby projects
        place_id: iNaturalist place ID to filter by
        per_page: Number of results (default 10)
    """
    params: dict = {"per_page": per_page}
    if q:
        params["q"] = q
    if lat is not None and lng is not None:
        params["lat"] = lat
        params["lng"] = lng
    if place_id:
        params["place_id"] = place_id

    data = await _api_get("/projects", params)
    if "error" in data:
        return data["error"]

    total = data.get("total_results", 0)
    results = data.get("results", [])
    if not results:
        return "No projects found matching your criteria."

    lines = [f"Found {total} projects (showing {len(results)}):\n"]
    for proj in results:
        lines.append(_format_project(proj))
        lines.append("")
    return "\n".join(lines)


# ============================================================
# Slice 3.2: Similar Species
# ============================================================

@mcp.tool()
async def get_similar_species(
    taxon_id: int,
    place_id: int | None = None,
) -> str:
    """Get species commonly confused with a given taxon. Useful for wildlife identification.

    Args:
        taxon_id: The iNaturalist taxon ID to find similar species for
        place_id: Optional place ID to get regionally relevant results
    """
    params: dict = {"taxon_id": taxon_id}
    if place_id:
        params["place_id"] = place_id

    data = await _api_get("/identifications/similar_species", params)
    if "error" in data:
        return data["error"]

    results = data.get("results", [])
    if not results:
        return f"No similar species data found for taxon {taxon_id}."

    lines = [f"Species commonly confused with taxon {taxon_id} ({len(results)} results):\n"]
    for i, item in enumerate(results, 1):
        lines.append(f"{i}. {_format_species_count(item)}")
    return "\n".join(lines)


# ============================================================
# Slice 3.3: Universal Search
# ============================================================

@mcp.tool()
async def inaturalist_search(
    q: str,
    sources: str | None = None,
    per_page: int = 10,
) -> str:
    """Search across all of iNaturalist — taxa, places, projects, and users at once.

    Args:
        q: Search query (e.g. "monarch butterfly migration")
        sources: Comma-separated types to include: "taxa", "places", "projects", "users" (default: all)
        per_page: Number of results (default 10)
    """
    params: dict = {"q": q, "per_page": per_page}
    if sources:
        params["sources"] = sources

    data = await _api_get("/search", params)
    if "error" in data:
        return data["error"]

    results = data.get("results", [])
    if not results:
        return f"No results found for '{q}'."

    lines = [f"Found {data.get('total_results', 0)} results for '{q}':\n"]
    for item in results:
        rtype = item.get("type", "unknown")
        record = item.get("record", {})

        if rtype == "Taxon":
            lines.append(f"[Taxon] {_format_taxon(record)}")
        elif rtype == "Place":
            lines.append(f"[Place] {_format_place(record)}")
        elif rtype == "Project":
            lines.append(f"[Project] {_format_project(record)}")
        elif rtype == "User":
            login = record.get("login", "unknown")
            name = record.get("name", "")
            obs = record.get("observations_count", 0)
            label = f"{name} (@{login})" if name else f"@{login}"
            lines.append(f"[User] **{label}** — {obs} observations")
        else:
            lines.append(f"[{rtype}] {record.get('name', record.get('title', 'Unknown'))}")
        lines.append("")

    return "\n".join(lines)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
