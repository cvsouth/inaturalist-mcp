# iNaturalist MCP Server

An MCP server that gives AI assistants access to iNaturalist's biodiversity data — search observations, explore species, and discover wildlife anywhere in the world.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

## Quick Start

Add to your MCP config:

```json
{
  "mcpServers": {
    "inaturalist": {
      "command": "uvx",
      "args": ["inaturalist-mcp"]
    }
  }
}
```

> [!NOTE]
> No API key required. This server uses the public iNaturalist API.

> [!IMPORTANT]
> Rate limited to 60 requests/minute to respect iNaturalist's API guidelines.

## Available Tools

| Tool | Description |
|------|-------------|
| `search_observations` | Search observations by location, species, date, and quality grade |
| `get_species_counts` | Get species observed at a location, ranked by observation count |
| `search_taxa` | Search for species by common or scientific name |
| `get_taxon` | Get detailed info about a species (taxonomy, conservation status, photos) |
| `search_places` | Find iNaturalist places by name |
| `get_nearby_places` | Find places near GPS coordinates |
| `search_projects` | Find community science projects (bioblitzes, surveys) |
| `get_similar_species` | Find species commonly confused with a target species |
| `inaturalist_search` | Search across all iNaturalist resources at once |

<details>
<summary>Full tool reference</summary>

### search_observations

Search iNaturalist observations by location, species, date, and more.

- `lat` (float): Latitude for location-based search
- `lng` (float): Longitude for location-based search
- `radius` (int): Search radius in km (default: 10, use with lat/lng)
- `place_name` (string): Place name to search within (e.g. "Australia", "Yellowstone")
- `place_id` (int): iNaturalist place ID to search within
- `taxon_name` (string): Species common or scientific name to filter by
- `taxon_id` (int): iNaturalist taxon ID to filter by
- `d1` (string): Start date (YYYY-MM-DD)
- `d2` (string): End date (YYYY-MM-DD)
- `quality_grade` (string): `research`, `needs_id`, or `casual`
- `iconic_taxa` (string): Filter by group: Aves, Mammalia, Reptilia, Amphibia, Insecta, Plantae, Fungi, etc.
- `page` (int): Page number (default: 1)
- `per_page` (int): Results per page (default: 20, max: 200)

### get_species_counts

Get species observed at a location, ranked by observation count. Great for answering "what wildlife will I see here?"

- `lat` (float): Latitude for location-based search
- `lng` (float): Longitude for location-based search
- `radius` (int): Search radius in km (default: 10, use with lat/lng)
- `place_name` (string): Place name (e.g. "Kruger National Park")
- `place_id` (int): iNaturalist place ID
- `taxon_name` (string): Filter to a taxon group by name (e.g. "Birds")
- `taxon_id` (int): Filter to a taxon group by ID
- `d1` (string): Start date (YYYY-MM-DD)
- `d2` (string): End date (YYYY-MM-DD)
- `quality_grade` (string): `research`, `needs_id`, or `casual`
- `iconic_taxa` (string): Filter by group: Aves, Mammalia, Reptilia, Amphibia, Insecta, Plantae, Fungi, etc.
- `per_page` (int): Number of species to return (default: 20, max: 200)

### search_taxa

Search for species or taxa by common or scientific name.

- `q` (string, required): Search query (e.g. "platypus", "Ornithorhynchus")
- `is_active` (bool): Only show currently accepted taxa
- `rank` (string): Filter by taxonomic rank (species, genus, family, order, class, phylum, kingdom)
- `per_page` (int): Number of results (default: 10, max: 30)

### get_taxon

Get detailed information about a specific taxon by ID. Returns taxonomy chain, conservation status, Wikipedia summary, and photos.

- `taxon_id` (int, required): The iNaturalist taxon ID

### search_places

Search for iNaturalist places by name. Returns place IDs you can use in other tools.

- `q` (string, required): Place name to search for (e.g. "Yellowstone", "Costa Rica")
- `per_page` (int): Number of results (default: 10)

### get_nearby_places

Find iNaturalist places near a set of coordinates. Returns both standard (administrative) and community places.

- `lat` (float, required): Latitude
- `lng` (float, required): Longitude

### search_projects

Search for iNaturalist community projects (bioblitzes, surveys, regional biodiversity projects).

- `q` (string): Search query (e.g. "birds Sydney", "butterflies")
- `lat` (float): Latitude to find nearby projects
- `lng` (float): Longitude to find nearby projects
- `place_id` (int): iNaturalist place ID to filter by
- `per_page` (int): Number of results (default: 10)

### get_similar_species

Get species commonly confused with a given taxon. Useful for wildlife identification.

- `taxon_id` (int, required): The iNaturalist taxon ID to find similar species for
- `place_id` (int): Optional place ID for regionally relevant results

### inaturalist_search

Search across all of iNaturalist — taxa, places, projects, and users at once.

- `q` (string, required): Search query (e.g. "monarch butterfly migration")
- `sources` (string): Comma-separated types: "taxa", "places", "projects", "users" (default: all)
- `per_page` (int): Number of results (default: 10)

</details>

## Development

```bash
git clone https://github.com/cvsouth/inaturalist-mcp.git
cd inaturalist-mcp
uv sync --dev
pytest
```

## License

MIT
