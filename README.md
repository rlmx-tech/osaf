# OSAF — Open Shark Attack File

An open-source, community-driven shark attack database — a transparent alternative to the restricted [International Shark Attack File (ISAF)](https://www.floridamuseum.ufl.edu/shark-attacks/).

## Why OSAF?

The ISAF is the world's only scientifically documented comprehensive shark attack database, but its detailed records are restricted to qualified researchers. OSAF makes incident data fully transparent and publicly accessible while using the same proven classification methodology.

- **Open data** — verified, data-minimized incident records are public
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

## Features

- Interactive world map with classification-colored markers and clustering
- Searchable/filterable incident database
- Trend dashboards and statistics (by year, country, species, activity)
- Public incident submission with admin review queue
- Durable collector jobs with leases, retries, and dead-letter visibility
- Immutable source evidence and versioned AI extraction provenance
- Reviewable incident candidates linked to canonical published records
- ISAF-compatible classification system

## Evidence architecture

```text
Pollers and submitted URLs
          ↓
Immutable source documents
          ↓
Durable leased collection jobs
          ↓
Versioned extracted observations
          ↓
Incident candidates and review
          ↓
Canonical published incidents
```

One source may produce multiple observations over time, and multiple sources
may support one incident candidate. AI output is retained as evidence with its
model, prompt version, confidence, and verification result; the canonical
incident remains a separate publication record.

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
# Clone your copy and start the full stack
git clone <repository-url> osaf
cd osaf
docker compose up -d
```

Production deployments should set `OSAF_BIND_ADDRESS` to the private address
used by their trusted reverse proxy. The backend is intentionally available
only through the bundled Nginx gateway.

## Privacy and corrections

Public API responses include verified incidents only. They omit victim names,
exact ages, narrative injury details, internal source notes, and submission
metadata. Published coordinates are rounded to reduce location precision.

To request a correction or removal, email [contact@osaf.net](mailto:contact@osaf.net)
with the case number and supporting information. Requests involving minors or
personal safety are prioritized. Full submission records are retained only for
verification, audit, and correction work and are not exposed by public API
endpoints.

## License

[MIT](LICENSE)

## Disclaimer

This project is **not affiliated** with the International Shark Attack File or the Florida Museum of Natural History. It is an independent open-source effort. Classifications are based on the same proven methodology used by ISAF but are applied independently.
