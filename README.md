# OSAF — Open Shark Attack File

An open-source, community-driven shark attack database — a transparent alternative to the restricted [International Shark Attack File (ISAF)](https://www.floridamuseum.ufl.edu/shark-attacks/).

## Why OSAF?

The ISAF is the world's only scientifically documented comprehensive shark attack database, but its detailed records are restricted to qualified researchers. OSAF makes incident data fully transparent and publicly accessible while using the same proven classification methodology.

- **Open data** — all incident data is public, no gatekeeping
- **Community-driven** — public submissions with verification workflow
- **Faster coverage** — rapid documentation from verified sources
- **Open source** — codebase and methodology are fully transparent

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Database | PostgreSQL 16 + PostGIS |
| API | FastAPI (Python 3.12+) |
| Frontend | React 18 (Vite) |
| Map | Leaflet + OpenStreetMap |
| Charts | Recharts |
| Auth | JWT (role-based) |
| Containers | Docker Compose |

## Features (Planned)

- Interactive world map with classification-colored markers and clustering
- Searchable/filterable incident database
- Trend dashboards and statistics (by year, country, species, activity)
- Public incident submission with admin review queue
- ISAF-compatible classification system

## Classification System

Based on the [ISAF methodology](https://www.floridamuseum.ufl.edu/shark-attacks/about/isaf-case-classifications/):

| Classification | Description |
|---|---|
| Unprovoked | Bite on a live human with no human provocation |
| Provoked | Human initiates interaction; shark responds defensively |
| Boat Bite | Bite on a vessel (provoked or unprovoked) |
| Scavenge | Feeding on a body post-mortem |
| Aquaria | Bite in a public aquarium |
| Doubtful | Determined not to be a shark |
| No Assignment | Shark confirmed, insufficient info to classify |
| Not Confirmed | Shark involvement unclear |

## Getting Started

```bash
# Clone and start the full stack
git clone https://git.home.rlmx.tech/russ/osaf.git
cd osaf
docker compose up -d
```

## License

[MIT](LICENSE)

## Disclaimer

This project is **not affiliated** with the International Shark Attack File or the Florida Museum of Natural History. It is an independent open-source effort. Classifications are based on the same proven methodology used by ISAF but are applied independently.
