# OSAF — Shark News Feed Page (SP2)

**Date:** 2026-06-30
**Status:** Approved design (pre-implementation)
**Scope:** Sub-project 2 of 2. Frontend only. Consumes the SP1 backend (`GET /api/v1/news`). Builds the public "Shark News" feed page.

---

## Problem / Goal

SP1 built the backend: a `news_items` capture store and a public `GET /api/v1/news` endpoint. SP2 surfaces it as a public, recency-first "Shark News" ticker — a feed of everything shark-related the collector captured (sightings, attacks, general news), newest first, on osaf.net.

**Sightings surfacing is already done** (no SP2 work): the map legend, map filters, DB filters, markers, popups, table, and by-classification stats all iterate `Object.entries(CLASSIFICATION_LABELS/COLORS)` and key off `classification`, and `constants.js` already defines `sighting` (color `#2ecc71`, label "Sighting"). So `classification='sighting'` incidents already render across the existing UI. SP2 adds only the news feed page.

## Non-Goals (SP2)

- Country / source-platform / date-range filters (the ticker uses tabs + search only; richer filters deferred).
- Component-render test harness (React Testing Library) — out of scope; minimal vitest for logic only.
- Any backend change — SP1's `GET /api/v1/news` is the fixed contract.
- A per-news-item detail page — rows link out to the source and (if promoted) to the existing incident page.

---

## Backend contract (fixed, from SP1)

`GET /api/v1/news` → `{ data: NewsItemRead[], meta: { total, page, per_page, pages } }`.
Query params used by SP2: `event_type` (one of `attack`/`sighting`/`news`; omit for All), `search`, `page`, `per_page`.
`NewsItemRead` fields used: `id, source_platform, source_name, source_url, title, summary, image_url, published_at, captured_at, event_type, country, promoted_incident_id`.

---

## Architecture & files

Follows existing patterns: axios `client`, `useX` hooks returning state, domain-grouped components under `src/components/<domain>/`, pages under `src/pages/`, `react-router` routes in `App.jsx`.

**Create:**
- `frontend/src/api/useNews.js` — hook with load-more accumulation.
- `frontend/src/pages/NewsPage.jsx` — route `/news`; owns `{eventType, search}` state; composes the page. (Paging lives in `useNews`, not here.)
- `frontend/src/components/news/NewsTabs.jsx` — All / Sightings / Attacks / News.
- `frontend/src/components/news/NewsSearch.jsx` — debounced search input.
- `frontend/src/components/news/NewsFeed.jsx` — list container + loading/empty/error states.
- `frontend/src/components/news/NewsItemRow.jsx` — single media row.
- `frontend/src/utils/safeUrl.js` — URL scheme guard.

**Modify:**
- `frontend/src/App.jsx` — add `<Route path="/news" element={<NewsPage />} />`.
- `frontend/src/components/layout/<Header>` — add a "News" nav link.
- `frontend/src/utils/constants.js` — add `EVENT_TYPE_LABELS`, `EVENT_TYPE_COLORS`.
- `frontend/src/utils/formatters.js` — add `relativeTime(dateStr)`.
- `frontend/package.json` — add `vitest` (dev) + `test` script.

---

## Components & data flow

**`NewsPage`** holds `{ eventType, search }` only (paging is internal to `useNews`).
- Changing tab or search → `useNews` (keyed on these deps) resets to page 1 and **replaces** the list.
- "Load more" → calls `useNews().loadMore()`, which fetches the next page and **appends**.
- Renders: title "Shark News", `NewsTabs`, `NewsSearch`, `NewsFeed`, and a "Load more" button shown only while `hasMore`.

**`useNews({ eventType, search })`** owns paging/accumulation internally:
- Builds params `{ event_type, search, page, per_page: 20 }`, dropping empty/undefined values (same guard as `useIncidents`).
- State: accumulated `items`, latest `meta`, `loading`, `error`, `page`.
- `hasMore` = `meta.page * meta.per_page < meta.total`.
- Exposes `{ items, meta, loading, error, hasMore, loadMore, reset }`. When `eventType`/`search` change (deps), it resets to page 1 and replaces; `loadMore()` fetches the next page and appends. Append must de-dupe defensively by `id` (guards against an item shifting pages between requests).

**`NewsTabs`** — four buttons. "All" sends no `event_type`; the others send `attack`/`sighting`/`news`. Active tab visually highlighted via `EVENT_TYPE_COLORS`.

**`NewsSearch`** — controlled input, debounced ~300ms before propagating to `NewsPage` (avoids a request per keystroke).

**`NewsItemRow`** renders, left→right:
- Thumbnail: `safeUrl(image_url)` → `<img>`; if null, a colored fallback block using `EVENT_TYPE_COLORS[event_type]`. `<img>` has `loading="lazy"` and an `onError` that swaps to the fallback block (handles dead image URLs).
- Event-type chip: colored dot (`EVENT_TYPE_COLORS`) + `EVENT_TYPE_LABELS[event_type]`.
- Meta line: `country ?? "—"` · `relativeTime(published_at ?? captured_at)`.
- Title: plain text (React-escaped).
- Source link: `source_name` as an `<a>` with `href = safeUrl(source_url)`, `target="_blank"`, `rel="noopener noreferrer"`. If `safeUrl` returns null, render `source_name` as plain text (no link).
- If `promoted_incident_id` is set: an "incident" link (react-router `<Link to={`/incidents/${promoted_incident_id}`}>`).

**States:** `NewsFeed` shows a spinner/skeleton on initial load, an empty state ("No shark news yet") when `items` is empty and not loading, and an inline error message on `error`. "Load more" shows a pending state while fetching the next page.

---

## Security

`safeUrl(url)` — the SP1-deferred XSS guard for AI/user-sourced URLs:
- Parse with `new URL(url)`; return the href only if `protocol` is `http:` or `https:`; otherwise return `null`.
- Reject `javascript:`, `data:`, `vbscript:`, malformed input, and null/empty.
- Used for BOTH `source_url` (anchor href) and `image_url` (img src).

Titles and summaries are rendered as React text children (never `dangerouslySetInnerHTML`), so they are escaped by default. Outbound links always carry `rel="noopener noreferrer"`.

---

## Constants

Add to `frontend/src/utils/constants.js`:
```
EVENT_TYPE_LABELS = { attack: "Attack", sighting: "Sighting", news: "News" }
EVENT_TYPE_COLORS = { attack: "#e74c3c", sighting: "#2ecc71", news: "#7f8c8d" }
```
(Reuses the established red/green/grey palette; `sighting` matches the existing classification color.)

---

## Testing (minimal vitest)

Add `vitest` as a dev dependency, a minimal config (jsdom not required for these), and a `"test": "vitest run"` script. Unit tests for pure logic only:

- `safeUrl` (security-critical): accepts `http://`/`https://`; rejects `javascript:`, `data:`, `vbscript:`, empty string, null, and non-URL garbage.
- `relativeTime`: seconds → "just now"/"Ns ago", minutes, hours, days; and null/undefined input → safe fallback (e.g. "").
- `useNews` logic: param object drops empties; `hasMore` computed correctly at boundaries (last page → false); `loadMore` appends and de-dupes by `id`; changing `eventType`/`search` resets to page 1 and replaces. Tested with a mocked `client` (vi.mock).

No component-render tests (matches the project's existing no-frontend-test convention; we add only the logic-level safety net, anchored by the security helper).

---

## Build order within SP2

1. `safeUrl` + `relativeTime` + constants (+ their vitest tests) — pure foundation.
2. `useNews` hook (+ test).
3. `NewsItemRow`, `NewsTabs`, `NewsSearch`, `NewsFeed` presentational components.
4. `NewsPage` + route + Header nav link (wire it together).
5. Manual/browser QA pass of the live page.

## Risks

- **Empty feed at launch:** until the collector runs against the new pipeline, `news_items` may be sparse — the empty state must read well. Acceptable; the page is correct with zero items.
- **`published_at` nullability:** many RSS/news items lack it; `relativeTime(published_at ?? captured_at)` handles the fallback so every row shows a time.
- **Image hotlinking/dead URLs:** third-party `image_url`s may 404 or be slow; `loading="lazy"` + `onError` fallback to the colored block contains this. (Hotlink privacy is acceptable for a public feed; a proxy is out of scope.)
- **Page drift on load-more:** new captures can shift items between page requests; de-duping the append by `id` prevents visible duplicates.
