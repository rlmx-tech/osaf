# CLAUDE.md — Open Shark Attack File (OSAF)

## Project Overview

An open-source, community-driven alternative to the International Shark Attack File (ISAF). The ISAF (https://www.floridamuseum.ufl.edu/shark-attacks/) is the world's only scientifically documented comprehensive shark attack database, but its detailed records are restricted to qualified researchers. OSAF makes incident data fully transparent and publicly accessible while using the same proven classification methodology.

### Core Differentiators
- **Open data**: All incident data is public — no gatekeeping behind academic access requests
- **Community-driven**: Public submissions with verification workflow + trusted contributor auto-publish
- **Faster coverage**: Rapid documentation of recent incidents from verified internet sources
- **Open source**: Codebase and methodology are fully transparent

### Inspiration & Sources
- ISAF classification system (Florida Museum of Natural History): https://www.floridamuseum.ufl.edu/shark-attacks/about/isaf-case-classifications/
- YouTube channels @SharkBytes (Kristian Parton, marine biologist) and @SharksHappen (Hal Miller) for case research and educational context
- Cases sourced from verified news outlets, government reports, and scientific publications

---

## Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| **Database** | PostgreSQL 16 + PostGIS | Geospatial queries for map features |
| **API** | FastAPI (Python 3.12+) | Auto OpenAPI docs, PostGIS integration, async |
| **Frontend** | React 18 (Vite) | SPA with client-side routing |
| **Map** | Leaflet + OpenStreetMap | Free, self-hostable tile server |
| **Charts** | Recharts | Trend dashboards and statistics |
| **Auth** | JWT (role-based) | Admin, Verified Contributor, Public |
| **Containerization** | Docker Compose | Full stack in containers |
| **Target Host** | Hera (AMD Ryzen 7 5700U, 64GB RAM, Debian 13) | Self-hosted homelab machine |

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   Nginx (reverse proxy)          │
│                   Port 80/443                    │
├────────────────────┬────────────────────────────┤
│   React SPA        │   FastAPI                  │
│   /                │   /api/v1/                 │
│   Port 3000 (dev)  │   Port 8000               │
├────────────────────┴────────────────────────────┤
│              PostgreSQL 16 + PostGIS             │
│              Port 5432                           │
└─────────────────────────────────────────────────┘
```

---

## Data Model

### Classification System (mirrors ISAF)

These classifications are based on shark behavior in response to varying stimuli. They do not diminish the experiences of victims.

| Classification | Description |
|---|---|
| **Unprovoked** | Bite on a live human in the shark's natural habitat with no human provocation. Includes: mistaken identity hit-and-run, investigation, and (rarely) predation. |
| **Provoked** | Human initiates interaction — harassing, touching, unhooking from net, spearfishing, feeding. Shark responds defensively. |
| **Boat Bite** | Bite on vessel of any size (kayak to yacht). Sub-classified as provoked or unprovoked. Provoked generally involves baited fishing. |
| **Scavenge** | Feeding on a body after the person died from unrelated causes (e.g., drowning). |
| **Aquaria** | Bite in a public aquarium — not a natural habitat. Sub-classified provoked/unprovoked. |
| **Doubtful** | Determined NOT to be a shark (often eels, stingrays, barracuda, bluefish misreported). |
| **No Assignment** | Shark involvement confirmed, but insufficient information for precise classification. |
| **Not Confirmed** | Shark involvement unclear — partial bite, no witnesses, unverified media reports. |

### Unprovoked Attack Sub-types

| Sub-type | Description |
|---|---|
| **Hit and Run** | Most common. Occurs in surf zone / murky water. Single bite, shark leaves. Usually non-fatal. Believed to be mistaken identity. |
| **Bump and Bite** | Shark circles and bumps victim before biting. Deeper water. More severe injuries. |
| **Sneak** | No warning. Can involve repeated bites. Deeper water. Often most severe. |

### Database Schema

```sql
-- Enable PostGIS
CREATE EXTENSION IF NOT EXISTS postgis;

-- Core incident table
CREATE TABLE incidents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_number VARCHAR(20) UNIQUE NOT NULL,  -- e.g., OSAF-2025-0042
    
    -- When
    incident_date DATE,
    incident_time TIME,
    date_precision VARCHAR(10) DEFAULT 'exact',  -- exact, month, year, approximate
    
    -- Where
    location_description TEXT NOT NULL,
    country VARCHAR(100) NOT NULL,
    state_province VARCHAR(100),
    county_region VARCHAR(100),
    body_of_water VARCHAR(200),
    coordinates GEOMETRY(POINT, 4326),  -- PostGIS point (lon, lat in WGS84)
    location_precision VARCHAR(20) DEFAULT 'exact',  -- exact, approximate, region
    
    -- Classification
    classification VARCHAR(20) NOT NULL,  -- unprovoked, provoked, boat_bite, scavenge, aquaria, doubtful, no_assignment, not_confirmed
    classification_subtype VARCHAR(20),  -- hit_and_run, bump_and_bite, sneak (for unprovoked)
    provocation_subtype VARCHAR(20),  -- provoked/unprovoked (for boat_bite and aquaria)
    
    -- Shark
    shark_species_confirmed VARCHAR(100),
    shark_species_suspected VARCHAR(100),
    shark_size_estimate VARCHAR(100),  -- free text, e.g., "3-4 meters"
    species_identification_method VARCHAR(50),  -- tooth_fragment, witness, expert, dna, photo, unknown
    
    -- Victim
    victim_activity VARCHAR(100),  -- swimming, surfing, diving, snorkeling, fishing, spearfishing, wading, etc.
    victim_injury_severity VARCHAR(20),  -- fatal, severe, moderate, minor, no_injury
    victim_injury_description TEXT,
    victim_age INTEGER,
    victim_sex VARCHAR(10),  -- male, female, unknown
    victim_name VARCHAR(200),  -- optional, public record only
    
    -- Outcome
    fatal BOOLEAN DEFAULT FALSE,
    
    -- Narrative
    description TEXT,  -- full incident narrative
    
    -- Metadata
    verification_status VARCHAR(20) DEFAULT 'pending',  -- pending, verified, rejected, needs_review
    verified_by UUID REFERENCES users(id),
    verified_at TIMESTAMPTZ,
    submitted_by UUID REFERENCES users(id),
    submitted_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT valid_classification CHECK (classification IN (
        'unprovoked', 'provoked', 'boat_bite', 'scavenge',
        'aquaria', 'doubtful', 'no_assignment', 'not_confirmed'
    )),
    CONSTRAINT valid_severity CHECK (victim_injury_severity IN (
        'fatal', 'severe', 'moderate', 'minor', 'no_injury'
    )),
    CONSTRAINT valid_verification CHECK (verification_status IN (
        'pending', 'verified', 'rejected', 'needs_review'
    ))
);

-- Sources / evidence for each incident
CREATE TABLE incident_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    source_type VARCHAR(30) NOT NULL,  -- news_article, government_report, scientific_paper, witness_account, video, photo, social_media, other
    source_url TEXT,
    source_title VARCHAR(500),
    source_publisher VARCHAR(200),
    source_date DATE,
    source_notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Species reference table
CREATE TABLE shark_species (
    id SERIAL PRIMARY KEY,
    common_name VARCHAR(100) NOT NULL,
    scientific_name VARCHAR(100) NOT NULL UNIQUE,
    family VARCHAR(100),
    danger_rating VARCHAR(20),  -- high, moderate, low, minimal
    max_size_meters DECIMAL(4,1),
    notes TEXT
);

-- Users / contributors
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(100),
    role VARCHAR(20) DEFAULT 'public',  -- admin, verified_contributor, public
    bio TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_login TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE,
    
    CONSTRAINT valid_role CHECK (role IN ('admin', 'verified_contributor', 'public'))
);

-- Audit log for incident changes
CREATE TABLE incident_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    action VARCHAR(20) NOT NULL,  -- created, updated, verified, rejected, reclassified
    changed_by UUID REFERENCES users(id),
    changed_at TIMESTAMPTZ DEFAULT NOW(),
    changes JSONB,  -- diff of what changed
    notes TEXT
);

-- Spatial index for map queries
CREATE INDEX idx_incidents_coordinates ON incidents USING GIST (coordinates);

-- Common query indexes
CREATE INDEX idx_incidents_classification ON incidents (classification);
CREATE INDEX idx_incidents_country ON incidents (country);
CREATE INDEX idx_incidents_date ON incidents (incident_date);
CREATE INDEX idx_incidents_verification ON incidents (verification_status);
CREATE INDEX idx_incidents_fatal ON incidents (fatal);
CREATE INDEX idx_incident_sources_incident ON incident_sources (incident_id);
```

---

## API Design (FastAPI)

### Project Structure

```
osaf/
├── docker-compose.yml
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── alembic/                    # DB migrations
│   │   ├── alembic.ini
│   │   └── versions/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI app entry
│   │   ├── config.py               # Settings / env vars
│   │   ├── database.py             # SQLAlchemy + PostGIS engine
│   │   ├── models/                 # SQLAlchemy ORM models
│   │   │   ├── __init__.py
│   │   │   ├── incident.py
│   │   │   ├── source.py
│   │   │   ├── species.py
│   │   │   ├── user.py
│   │   │   └── audit.py
│   │   ├── schemas/                # Pydantic request/response schemas
│   │   │   ├── __init__.py
│   │   │   ├── incident.py
│   │   │   ├── source.py
│   │   │   ├── species.py
│   │   │   ├── user.py
│   │   │   └── stats.py
│   │   ├── api/                    # Route handlers
│   │   │   ├── __init__.py
│   │   │   ├── v1/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── router.py       # Aggregates all v1 routes
│   │   │   │   ├── incidents.py    # CRUD + search + map endpoints
│   │   │   │   ├── stats.py        # Aggregation / trend endpoints
│   │   │   │   ├── species.py      # Species reference data
│   │   │   │   ├── submissions.py  # Public submission + review queue
│   │   │   │   ├── users.py        # User management
│   │   │   │   └── auth.py         # Login / token endpoints
│   │   ├── services/               # Business logic
│   │   │   ├── __init__.py
│   │   │   ├── incident_service.py
│   │   │   ├── stats_service.py
│   │   │   ├── submission_service.py
│   │   │   └── auth_service.py
│   │   └── utils/
│   │       ├── __init__.py
│   │       ├── case_number.py      # OSAF-YYYY-NNNN generator
│   │       └── geo.py              # Coordinate helpers
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_incidents.py
│       ├── test_stats.py
│       └── test_submissions.py
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   ├── public/
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── api/                    # API client / hooks
│       │   ├── client.js
│       │   ├── useIncidents.js
│       │   ├── useStats.js
│       │   └── useMap.js
│       ├── components/
│       │   ├── layout/
│       │   │   ├── Header.jsx
│       │   │   ├── Footer.jsx
│       │   │   └── Sidebar.jsx
│       │   ├── map/
│       │   │   ├── IncidentMap.jsx          # Main Leaflet map
│       │   │   ├── IncidentMarker.jsx       # Custom marker by classification
│       │   │   ├── IncidentPopup.jsx        # Popup card on click
│       │   │   ├── MapFilters.jsx           # Filter controls overlay
│       │   │   └── MapLegend.jsx            # Classification color legend
│       │   ├── incidents/
│       │   │   ├── IncidentTable.jsx        # Searchable/filterable table
│       │   │   ├── IncidentDetail.jsx       # Full incident view
│       │   │   ├── IncidentFilters.jsx      # Filter sidebar
│       │   │   └── IncidentCard.jsx         # Summary card
│       │   ├── stats/
│       │   │   ├── TrendDashboard.jsx       # Main stats page
│       │   │   ├── AttacksByYear.jsx        # Recharts line/bar
│       │   │   ├── AttacksByCountry.jsx     # Choropleth or bar
│       │   │   ├── AttacksBySpecies.jsx     # Pie/bar chart
│       │   │   ├── AttacksByActivity.jsx    # Victim activity breakdown
│       │   │   └── FatalityTrends.jsx       # Fatal vs non-fatal over time
│       │   ├── submissions/
│       │   │   ├── SubmitForm.jsx           # Public incident submission
│       │   │   └── ReviewQueue.jsx          # Admin review interface
│       │   └── auth/
│       │       ├── LoginForm.jsx
│       │       └── ProtectedRoute.jsx
│       ├── pages/
│       │   ├── MapPage.jsx
│       │   ├── DatabasePage.jsx
│       │   ├── StatsPage.jsx
│       │   ├── SubmitPage.jsx
│       │   ├── IncidentPage.jsx
│       │   ├── AboutPage.jsx
│       │   ├── AdminPage.jsx
│       │   └── LoginPage.jsx
│       └── utils/
│           ├── constants.js         # Classification colors, labels
│           └── formatters.js        # Date, coordinate formatting
└── nginx/
    └── nginx.conf
```

### Key API Endpoints

```
# Public endpoints (no auth)
GET    /api/v1/incidents                    # List/search/filter incidents
GET    /api/v1/incidents/{id}               # Single incident detail
GET    /api/v1/incidents/map                 # GeoJSON for map (bbox filter)
GET    /api/v1/incidents/map/clusters        # Clustered points for zoom levels
GET    /api/v1/stats/overview                # High-level stats (total, by year, etc.)
GET    /api/v1/stats/by-year                 # Yearly breakdown
GET    /api/v1/stats/by-country              # Country breakdown
GET    /api/v1/stats/by-species              # Species breakdown
GET    /api/v1/stats/by-activity             # Victim activity breakdown
GET    /api/v1/stats/fatality-trends         # Fatal vs non-fatal over time
GET    /api/v1/species                       # Species reference list
GET    /api/v1/docs                          # Auto-generated OpenAPI docs

# Auth
POST   /api/v1/auth/login                   # JWT token
POST   /api/v1/auth/register                # Account creation

# Submissions (authenticated)
POST   /api/v1/submissions                  # Submit new incident (any authenticated user)

# Verified contributor endpoints
POST   /api/v1/incidents                    # Direct create (auto-published)
PUT    /api/v1/incidents/{id}               # Update incident

# Admin endpoints
GET    /api/v1/admin/submissions             # Review queue
PUT    /api/v1/admin/submissions/{id}/verify # Approve submission
PUT    /api/v1/admin/submissions/{id}/reject # Reject submission
PUT    /api/v1/admin/users/{id}/role         # Change user role
GET    /api/v1/admin/audit-log               # View changes
```

### Query Parameters for GET /incidents

```
?classification=unprovoked,provoked       # Comma-separated classifications
&country=Australia,United States          # Filter by country
&species=Carcharodon carcharias           # Filter by species (scientific name)
&fatal=true                               # Fatal only
&date_from=2020-01-01                     # Date range start
&date_to=2025-12-31                       # Date range end
&activity=surfing,swimming                # Victim activity
&severity=fatal,severe                    # Injury severity
&verification=verified                    # Verification status
&search=new smyrna beach                  # Full-text search
&bbox=-82,28,-80,30                       # Bounding box (west,south,east,north)
&sort=incident_date                       # Sort field
&order=desc                               # Sort order
&page=1                                   # Pagination
&per_page=50                              # Page size
```

---

## Map Feature Details

### Classification Color Scheme
- **Unprovoked**: `#e74c3c` (red)
- **Provoked**: `#f39c12` (orange)
- **Boat Bite**: `#3498db` (blue)
- **Scavenge**: `#9b59b6` (purple)
- **Aquaria**: `#1abc9c` (teal)
- **Doubtful**: `#95a5a6` (grey)
- **No Assignment**: `#bdc3c7` (light grey)
- **Not Confirmed**: `#ecf0f1` (very light grey)

### Map Behavior
- Default view: world map with clustered markers
- Cluster markers show count, colored by dominant classification in cluster
- Zoom in to de-cluster into individual pins
- Click pin → popup with: date, location, classification, species, severity, link to full record
- Filter panel overlaid on map (classification checkboxes, date range, species, fatal toggle)
- GeoJSON endpoint with bbox filtering for performance

---

## Submission Workflow

### Public Users
1. Fill out submission form (all incident fields + at least one source URL)
2. Submission enters review queue with status `pending`
3. Admin reviews, can request more info (`needs_review`), approve (`verified`), or reject (`rejected`)
4. On approval, incident goes live with auto-generated case number (OSAF-YYYY-NNNN)

### Verified Contributors
1. Direct incident creation via the same form
2. Automatically published with status `verified`
3. Still logged in audit trail
4. Can edit existing incidents (changes logged)

### Admins
- Full CRUD on all incidents
- Manage review queue
- Promote/demote user roles
- View audit log

---

## Environment Variables

```env
# Database
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_DB=osaf
POSTGRES_USER=osaf
POSTGRES_PASSWORD=<generate-strong-password>

# API
API_HOST=0.0.0.0
API_PORT=8000
SECRET_KEY=<generate-strong-secret>
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24
CORS_ORIGINS=http://localhost:3000

# Frontend
VITE_API_URL=http://localhost:8000/api/v1
```

---

## Build Order (Priority)

### Phase 1: Foundation
- [ ] Docker Compose (postgres+postgis, fastapi, react, nginx)
- [ ] Database schema + Alembic migrations
- [ ] FastAPI project scaffold with health check
- [ ] SQLAlchemy models + Pydantic schemas
- [ ] Basic CRUD endpoints for incidents
- [ ] Seed data: shark species reference table + sample incidents

### Phase 2: Interactive Map (Priority 1)
- [ ] GeoJSON endpoint with bbox filtering
- [ ] Marker clustering endpoint
- [ ] React Leaflet map component
- [ ] Classification-colored markers + legend
- [ ] Popup cards on marker click
- [ ] Map filter panel (classification, date range, species, severity)

### Phase 3: Searchable Database Table (Priority 2)
- [ ] Incident list endpoint with full query params
- [ ] Full-text search via PostgreSQL tsvector
- [ ] React table component with column sorting
- [ ] Filter sidebar
- [ ] Incident detail page
- [ ] Pagination

### Phase 4: Trend Charts & Statistics (Priority 3)
- [ ] Stats aggregation endpoints (by year, country, species, activity, fatality)
- [ ] Recharts dashboard components
- [ ] Overview stats cards (total incidents, fatality rate, most active country, etc.)

### Phase 5: Submissions & Admin (Priority 4)
- [ ] JWT auth (login, register)
- [ ] Public submission form
- [ ] Admin review queue
- [ ] Role-based route protection
- [ ] Audit logging
- [ ] Verified contributor auto-publish flow

---

## Development Commands

```bash
# Start full stack
docker compose up -d

# Run backend only (development)
cd backend
pip install -e ".[dev]"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run frontend only (development)
cd frontend
npm install
npm run dev

# Database migrations
cd backend
alembic upgrade head            # Apply migrations
alembic revision --autogenerate -m "description"  # Create migration

# Run tests
cd backend
pytest -v

# Seed database
cd backend
python -m app.utils.seed_data
```

---

## Coding Standards

- **Python**: Follow PEP 8. Use type hints everywhere. Async endpoints where beneficial.
- **SQL**: Use Alembic for all schema changes — never modify the DB directly.
- **React**: Functional components + hooks only. No class components.
- **CSS**: Tailwind utility classes preferred. No separate CSS files unless necessary.
- **API**: Always return consistent JSON envelope: `{ "data": ..., "meta": { "total", "page", "per_page" } }`
- **Errors**: Return `{ "detail": "message" }` with appropriate HTTP status codes.
- **Git**: Conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`).

---

## Notes

- The project name is **OSAF** (Open Shark Attack File). Use this in branding, case number prefixes, etc.
- Case numbers follow the format `OSAF-YYYY-NNNN` (year + sequential number).
- All timestamps stored in UTC. Frontend converts to local time for display.
- Coordinates stored as WGS84 (SRID 4326) — standard GPS coordinates.
- The ISAF is the gold standard for classification methodology. When in doubt, refer to: https://www.floridamuseum.ufl.edu/shark-attacks/about/isaf-case-classifications/
- **Domain**: osaf.net
- **Repo**: Forgejo-only — `git.home.rlmx.tech/russ/osaf` (GitHub removed 2026-07-01)
- This project is NOT affiliated with ISAF or the Florida Museum. It is an independent open-source effort.
