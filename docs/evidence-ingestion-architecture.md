# Evidence ingestion architecture

OSAF separates collected material, extracted claims, real-world incident
hypotheses, and public records. This prevents an article or model response from
being mistaken for the incident itself.

## Data flow

1. A poller captures every discovered item as an immutable `source_documents`
   row. Repeated captures update only `last_seen_at`.
2. The backend creates one `collection_jobs` extraction job per source and
   grants a 15-minute lease. Expired leases can be reclaimed. Transient failures
   use exponential backoff and terminal failures enter `dead_letter`.
3. The collector stores its structured payload in `extracted_observations`,
   including model name, prompt/schema versions, confidence, verification
   output, and a stable payload checksum.
4. Attack and sighting observations enter `incident_candidates`. Complete
   normalized date, country, location, and classification fields form a
   conservative exact match key, allowing multiple sources to support one
   candidate. Incomplete claims remain distinct for manual review.
5. Published candidates reference the canonical `incidents` row. Case numbers
   continue to be issued only by the existing durable yearly counter.

The public news feed remains backed by `news_items`, which now links to the
captured source document. The collector classifies the feed item and records a
candidate, but it never invokes canonical incident submission. An administrator
publishes a reviewed candidate through the existing submission service; that
operation assigns the case number, links every supporting news item, and records
the candidate-to-canonical relationship. Lower-confidence and duplicate-likely
observations remain in the evidence queue instead of being discarded.

## Operations

The admin-only endpoints are:

- `GET /api/v1/admin/candidates`
- `PUT /api/v1/admin/candidates/{id}/publish`
- `PUT /api/v1/admin/candidates/{id}/reject`
- `GET /api/v1/admin/ingestion-health`

Public `/health` intentionally exposes only `{"status":"ok"}`. Queue depth,
dead-letter counts, and activity timestamps are restricted to administrators.

The collector JSON volume now retains only non-critical poll timestamps. Item
deduplication and retry state are authoritative in PostgreSQL.
