# Shark News Feed Page (SP2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the public, recency-first "Shark News" feed page at `/news`, consuming SP1's `GET /api/v1/news`.

**Architecture:** A single page (`NewsPage`) with event-type tabs + debounced search, rendering media-list rows via a `useNews` hook with load-more paging. Pure logic (URL safety, relative time, param/paging helpers) is extracted into tested utils; presentational components are verified by a clean `npm run build`. Sightings already render across the existing UI via dynamic `CLASSIFICATION_*` constants — no work needed there.

**Tech Stack:** React 18.3 (functional components + hooks), react-router-dom 6.28, axios (shared `client`), Tailwind 3.4 (dark theme), Vite 6, Vitest 2.1 (pure-logic unit tests, node env).

## Global Constraints

- React function components only; hooks; no class components.
- Tailwind utility classes, dark theme (bg `gray-900`, borders `gray-700/800`, text `gray-100/400/500`, accents `blue-400`). No separate CSS files.
- NEVER use `dangerouslySetInnerHTML`. All text rendered as React children (auto-escaped).
- ALL external URLs (`source_url` href, `image_url` src) MUST pass through `safeUrl()`; outbound links carry `target="_blank" rel="noopener noreferrer"`.
- Backend contract is fixed: `GET /api/v1/news` → `{ data: NewsItemRead[], meta: {total, page, per_page, pages} }`. Params used: `event_type` (`attack`/`sighting`/`news`; omit for All), `search`, `page`, `per_page`.
- `per_page` = 20. Time shown = `published_at ?? captured_at` via `relativeTime`.
- Pure helpers are unit-tested with Vitest; presentational components are verified by `npm run build` (no React Testing Library / jsdom).
- Conventional commits (`feat:`, `test:`, `chore:`). Attribution disabled — no Co-Authored-By trailer.
- All commands run from `~/claude/OSAF/frontend`. Tests: `npm test` (or `npx vitest run <file>` focused). Build: `npm run build`.
- PREREQ already in place (committed on the branch before Task 1): `vitest@2.1.8` devDep, `"test": "vitest run"` script, `vitest.config.js` (node env, `include: src/**/*.test.{js,jsx}`), and `node_modules` installed.

---

## File Structure

**Create:**
- `src/utils/safeUrl.js` + `src/utils/safeUrl.test.js` — URL scheme guard (security).
- `src/utils/news.js` + `src/utils/news.test.js` — `buildNewsParams`, `computeHasMore`, `mergeNewsItems`.
- `src/api/useNews.js` — hook (consumes news helpers + `client`).
- `src/components/news/NewsItemRow.jsx` — one media row (security-sensitive rendering).
- `src/components/news/NewsTabs.jsx` — event-type tabs.
- `src/components/news/NewsSearch.jsx` — debounced search input.
- `src/components/news/NewsFeed.jsx` — list container + states.
- `src/pages/NewsPage.jsx` — `/news` page.

**Modify:**
- `src/utils/formatters.js` — add `relativeTime` (+ `src/utils/formatters.test.js` new).
- `src/utils/constants.js` — add `EVENT_TYPE_LABELS`, `EVENT_TYPE_COLORS`.
- `src/App.jsx` — add `/news` route.
- `src/components/layout/Header.jsx` — add "News" nav link.

---

## Task 1: `safeUrl` URL-scheme guard

**Files:**
- Create: `src/utils/safeUrl.js`
- Test: `src/utils/safeUrl.test.js`

**Interfaces:**
- Produces: `safeUrl(url: unknown) -> string | null` — returns the href only for `http:`/`https:` URLs; `null` otherwise.

- [ ] **Step 1: Write the failing test**

`src/utils/safeUrl.test.js`:
```js
import { describe, it, expect } from "vitest";
import { safeUrl } from "./safeUrl";

describe("safeUrl", () => {
  it("accepts http and https", () => {
    expect(safeUrl("http://example.com/x")).toBe("http://example.com/x");
    expect(safeUrl("https://example.com/y?a=1")).toBe("https://example.com/y?a=1");
  });
  it("rejects dangerous and non-http schemes", () => {
    expect(safeUrl("javascript:alert(1)")).toBeNull();
    expect(safeUrl("data:text/html,<script>")).toBeNull();
    expect(safeUrl("vbscript:msgbox")).toBeNull();
    expect(safeUrl("ftp://example.com")).toBeNull();
  });
  it("rejects empty, null, and garbage", () => {
    expect(safeUrl("")).toBeNull();
    expect(safeUrl(null)).toBeNull();
    expect(safeUrl(undefined)).toBeNull();
    expect(safeUrl("not a url")).toBeNull();
    expect(safeUrl(42)).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/claude/OSAF/frontend && npx vitest run src/utils/safeUrl.test.js`
Expected: FAIL — cannot resolve `./safeUrl`.

- [ ] **Step 3: Write minimal implementation**

`src/utils/safeUrl.js`:
```js
/**
 * Returns the URL href only if it is an http(s) URL, else null.
 * Guards against javascript:/data:/vbscript: and malformed input for
 * AI/user-sourced URLs (source_url, image_url) rendered in the news feed.
 */
export function safeUrl(url) {
  if (!url || typeof url !== "string") return null;
  try {
    const parsed = new URL(url);
    if (parsed.protocol === "http:" || parsed.protocol === "https:") {
      return parsed.href;
    }
    return null;
  } catch {
    return null;
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/claude/OSAF/frontend && npx vitest run src/utils/safeUrl.test.js`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
cd ~/claude/OSAF
git add frontend/src/utils/safeUrl.js frontend/src/utils/safeUrl.test.js
git commit -m "feat(frontend): safeUrl http(s) scheme guard for news URLs"
```

---

## Task 2: `relativeTime` formatter

**Files:**
- Modify: `src/utils/formatters.js`
- Test: `src/utils/formatters.test.js`

**Interfaces:**
- Produces: `relativeTime(dateStr: string | null | undefined) -> string` — "just now", "Nm ago", "Nh ago", "Nd ago", else a localized date; `""` for null/invalid.

- [ ] **Step 1: Write the failing test**

`src/utils/formatters.test.js`:
```js
import { describe, it, expect } from "vitest";
import { relativeTime } from "./formatters";

const iso = (msAgo) => new Date(Date.now() - msAgo).toISOString();

describe("relativeTime", () => {
  it("handles recent ranges", () => {
    expect(relativeTime(iso(5 * 1000))).toBe("just now");
    expect(relativeTime(iso(5 * 60 * 1000))).toBe("5m ago");
    expect(relativeTime(iso(3 * 3600 * 1000))).toBe("3h ago");
    expect(relativeTime(iso(2 * 86400 * 1000))).toBe("2d ago");
  });
  it("falls back to a date for old timestamps", () => {
    const out = relativeTime("2020-01-15T00:00:00Z");
    expect(out).toMatch(/2020/);
  });
  it("returns empty string for null/invalid", () => {
    expect(relativeTime(null)).toBe("");
    expect(relativeTime(undefined)).toBe("");
    expect(relativeTime("not a date")).toBe("");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/claude/OSAF/frontend && npx vitest run src/utils/formatters.test.js`
Expected: FAIL — `relativeTime` is not exported.

- [ ] **Step 3: Write minimal implementation** (append to `src/utils/formatters.js`)

```js
export function relativeTime(dateStr) {
  if (!dateStr) return "";
  const then = new Date(dateStr);
  if (isNaN(then.getTime())) return "";
  const seconds = Math.floor((Date.now() - then.getTime()) / 1000);
  if (seconds < 45) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 2592000) return `${Math.floor(seconds / 86400)}d ago`;
  return then.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/claude/OSAF/frontend && npx vitest run src/utils/formatters.test.js`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
cd ~/claude/OSAF
git add frontend/src/utils/formatters.js frontend/src/utils/formatters.test.js
git commit -m "feat(frontend): relativeTime formatter"
```

---

## Task 3: News paging helpers

**Files:**
- Create: `src/utils/news.js`
- Test: `src/utils/news.test.js`

**Interfaces:**
- Produces:
  - `buildNewsParams({ eventType, search }, page, perPage) -> object` — `{ page, per_page }` plus `event_type`/`search` only when non-empty.
  - `computeHasMore(meta) -> boolean` — `meta.page * meta.per_page < meta.total`; `false` if `meta` is null.
  - `mergeNewsItems(prev, next) -> array` — concatenates, de-duping by `id`.

- [ ] **Step 1: Write the failing test**

`src/utils/news.test.js`:
```js
import { describe, it, expect } from "vitest";
import { buildNewsParams, computeHasMore, mergeNewsItems } from "./news";

describe("buildNewsParams", () => {
  it("drops empty event_type/search", () => {
    expect(buildNewsParams({ eventType: "", search: "" }, 1, 20)).toEqual({ page: 1, per_page: 20 });
  });
  it("includes non-empty filters", () => {
    expect(buildNewsParams({ eventType: "sighting", search: "bondi" }, 2, 20)).toEqual({
      page: 2, per_page: 20, event_type: "sighting", search: "bondi",
    });
  });
});

describe("computeHasMore", () => {
  it("is false when meta is null", () => {
    expect(computeHasMore(null)).toBe(false);
  });
  it("is true when more pages remain", () => {
    expect(computeHasMore({ page: 1, per_page: 20, total: 50 })).toBe(true);
  });
  it("is false on the last page", () => {
    expect(computeHasMore({ page: 3, per_page: 20, total: 60 })).toBe(false);
  });
});

describe("mergeNewsItems", () => {
  it("appends and de-dupes by id", () => {
    const prev = [{ id: "a" }, { id: "b" }];
    const next = [{ id: "b" }, { id: "c" }];
    expect(mergeNewsItems(prev, next).map((i) => i.id)).toEqual(["a", "b", "c"]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/claude/OSAF/frontend && npx vitest run src/utils/news.test.js`
Expected: FAIL — cannot resolve `./news`.

- [ ] **Step 3: Write minimal implementation**

`src/utils/news.js`:
```js
export function buildNewsParams({ eventType = "", search = "" } = {}, page = 1, perPage = 20) {
  const params = { page, per_page: perPage };
  if (eventType) params.event_type = eventType;
  if (search) params.search = search;
  return params;
}

export function computeHasMore(meta) {
  if (!meta) return false;
  return meta.page * meta.per_page < meta.total;
}

export function mergeNewsItems(prev, next) {
  const seen = new Set(prev.map((i) => i.id));
  return [...prev, ...next.filter((i) => !seen.has(i.id))];
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/claude/OSAF/frontend && npx vitest run src/utils/news.test.js`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
cd ~/claude/OSAF
git add frontend/src/utils/news.js frontend/src/utils/news.test.js
git commit -m "feat(frontend): news paging helpers (params, hasMore, merge-dedupe)"
```

---

## Task 4: `useNews` hook

**Files:**
- Create: `src/api/useNews.js`

**Interfaces:**
- Consumes: `client` (axios) from `./client`; `buildNewsParams`, `computeHasMore`, `mergeNewsItems` from `../utils/news`.
- Produces: `useNews({ eventType, search }) -> { items, meta, loading, error, hasMore, loadMore }`. Resets to page 1 and replaces when `eventType`/`search` change; `loadMore()` fetches the next page and appends (de-duped).

- [ ] **Step 1: Write the implementation** (no unit test — logic lives in Task 3's tested helpers; verified by build in Step 2)

`src/api/useNews.js`:
```js
import { useState, useEffect, useCallback, useRef } from "react";
import client from "./client";
import { buildNewsParams, computeHasMore, mergeNewsItems } from "../utils/news";

const PER_PAGE = 20;

export function useNews({ eventType = "", search = "" } = {}) {
  const [items, setItems] = useState([]);
  const [meta, setMeta] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const pageRef = useRef(1);

  const fetchPage = useCallback(
    async (page, replace) => {
      setLoading(true);
      setError(null);
      try {
        const params = buildNewsParams({ eventType, search }, page, PER_PAGE);
        const resp = await client.get("/news", { params });
        const payload = resp.data;
        setMeta(payload.meta);
        pageRef.current = page;
        setItems((prev) => (replace ? payload.data : mergeNewsItems(prev, payload.data)));
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    },
    [eventType, search]
  );

  // Reset to page 1 and replace whenever the filters change.
  useEffect(() => {
    pageRef.current = 1;
    fetchPage(1, true);
  }, [fetchPage]);

  const loadMore = useCallback(() => {
    if (loading) return;
    fetchPage(pageRef.current + 1, false);
  }, [fetchPage, loading]);

  return { items, meta, loading, error, hasMore: computeHasMore(meta), loadMore };
}
```

- [ ] **Step 2: Verify it builds**

Run: `cd ~/claude/OSAF/frontend && npm run build`
Expected: `✓ built` with no errors (imports resolve, JSX/JS compiles).

- [ ] **Step 3: Commit**

```bash
cd ~/claude/OSAF
git add frontend/src/api/useNews.js
git commit -m "feat(frontend): useNews hook with load-more paging"
```

---

## Task 5: Event-type constants + `NewsItemRow`

**Files:**
- Modify: `src/utils/constants.js`
- Create: `src/components/news/NewsItemRow.jsx`

**Interfaces:**
- Consumes: `safeUrl` (Task 1), `relativeTime` (Task 2), and new `EVENT_TYPE_LABELS`/`EVENT_TYPE_COLORS`.
- Produces: `EVENT_TYPE_LABELS`, `EVENT_TYPE_COLORS`; default-export `NewsItemRow({ item })`.

- [ ] **Step 1: Add constants** (append to `src/utils/constants.js`)

```js
export const EVENT_TYPE_LABELS = {
  attack: "Attack",
  sighting: "Sighting",
  news: "News",
};

export const EVENT_TYPE_COLORS = {
  attack: "#e74c3c",
  sighting: "#2ecc71",
  news: "#7f8c8d",
};
```

- [ ] **Step 2: Create `NewsItemRow`**

`src/components/news/NewsItemRow.jsx`:
```jsx
import { useState } from "react";
import { Link } from "react-router-dom";
import { safeUrl } from "../../utils/safeUrl";
import { relativeTime } from "../../utils/formatters";
import { EVENT_TYPE_LABELS, EVENT_TYPE_COLORS } from "../../utils/constants";

export default function NewsItemRow({ item }) {
  const [imgError, setImgError] = useState(false);
  const color = EVENT_TYPE_COLORS[item.event_type] || "#7f8c8d";
  const label = EVENT_TYPE_LABELS[item.event_type] || item.event_type;
  const img = safeUrl(item.image_url);
  const href = safeUrl(item.source_url);
  const when = relativeTime(item.published_at || item.captured_at);
  const showImg = img && !imgError;

  return (
    <article className="flex gap-3 py-3 border-b border-gray-800">
      {showImg ? (
        <img
          src={img}
          alt=""
          loading="lazy"
          onError={() => setImgError(true)}
          className="w-20 h-20 object-cover rounded flex-shrink-0 bg-gray-800"
        />
      ) : (
        <div
          className="w-20 h-20 rounded flex-shrink-0"
          style={{ backgroundColor: color }}
          aria-hidden="true"
        />
      )}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
          <span className="inline-flex items-center gap-1 font-medium" style={{ color }}>
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
            {label}
          </span>
          <span className="text-gray-500">· {item.country || "—"} · {when}</span>
          {item.promoted_incident_id && (
            <Link
              to={`/incidents/${item.promoted_incident_id}`}
              className="text-blue-400 hover:text-blue-300"
            >
              · incident
            </Link>
          )}
        </div>
        <h3 className="text-sm text-gray-100 mt-1">{item.title}</h3>
        <div className="text-xs text-gray-500 mt-1">
          {href ? (
            <a href={href} target="_blank" rel="noopener noreferrer" className="hover:text-gray-300">
              {item.source_name} ↗
            </a>
          ) : (
            <span>{item.source_name}</span>
          )}
        </div>
      </div>
    </article>
  );
}
```

- [ ] **Step 3: Verify it builds**

Run: `cd ~/claude/OSAF/frontend && npm run build`
Expected: `✓ built` with no errors.

- [ ] **Step 4: Commit**

```bash
cd ~/claude/OSAF
git add frontend/src/utils/constants.js frontend/src/components/news/NewsItemRow.jsx
git commit -m "feat(frontend): event-type constants + NewsItemRow (safe URL rendering)"
```

---

## Task 6: `NewsTabs` + `NewsSearch`

**Files:**
- Create: `src/components/news/NewsTabs.jsx`
- Create: `src/components/news/NewsSearch.jsx`

**Interfaces:**
- Produces:
  - `NewsTabs({ active, onChange })` — buttons for All(`""`)/Sightings(`sighting`)/Attacks(`attack`)/News(`news`); calls `onChange(value)`.
  - `NewsSearch({ value, onChange })` — debounced (~300ms) text input; calls `onChange(text)`.

- [ ] **Step 1: Create `NewsTabs`**

`src/components/news/NewsTabs.jsx`:
```jsx
const TABS = [
  { value: "", label: "All" },
  { value: "sighting", label: "Sightings" },
  { value: "attack", label: "Attacks" },
  { value: "news", label: "News" },
];

export default function NewsTabs({ active, onChange }) {
  return (
    <div className="flex gap-1">
      {TABS.map((t) => (
        <button
          key={t.value || "all"}
          onClick={() => onChange(t.value)}
          className={`text-sm px-3 py-1.5 rounded transition-colors ${
            active === t.value
              ? "bg-gray-800 text-white"
              : "text-gray-400 hover:text-white hover:bg-gray-800/50"
          }`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Create `NewsSearch`**

`src/components/news/NewsSearch.jsx`:
```jsx
import { useState, useEffect } from "react";

export default function NewsSearch({ value, onChange }) {
  const [local, setLocal] = useState(value);

  // Keep local input in sync if the parent resets the value.
  useEffect(() => {
    setLocal(value);
  }, [value]);

  // Debounce propagation to avoid a request per keystroke.
  useEffect(() => {
    const t = setTimeout(() => {
      if (local !== value) onChange(local);
    }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [local]);

  return (
    <input
      type="search"
      value={local}
      onChange={(e) => setLocal(e.target.value)}
      placeholder="Search shark news…"
      className="bg-gray-800 text-gray-100 text-sm rounded px-3 py-1.5 border border-gray-700 focus:outline-none focus:border-gray-500 w-full sm:w-64"
    />
  );
}
```

- [ ] **Step 3: Verify it builds**

Run: `cd ~/claude/OSAF/frontend && npm run build`
Expected: `✓ built` with no errors.

- [ ] **Step 4: Commit**

```bash
cd ~/claude/OSAF
git add frontend/src/components/news/NewsTabs.jsx frontend/src/components/news/NewsSearch.jsx
git commit -m "feat(frontend): NewsTabs + debounced NewsSearch"
```

---

## Task 7: `NewsFeed` list container

**Files:**
- Create: `src/components/news/NewsFeed.jsx`

**Interfaces:**
- Consumes: `NewsItemRow` (Task 5).
- Produces: `NewsFeed({ items, loading, error, hasMore, onLoadMore })` — renders rows + loading/empty/error states + a "Load more" button.

- [ ] **Step 1: Create `NewsFeed`**

`src/components/news/NewsFeed.jsx`:
```jsx
import NewsItemRow from "./NewsItemRow";

export default function NewsFeed({ items, loading, error, hasMore, onLoadMore }) {
  if (error) {
    return (
      <div className="text-red-400 text-sm py-8 text-center">
        Failed to load shark news: {error}
      </div>
    );
  }
  if (!loading && items.length === 0) {
    return <div className="text-gray-500 text-sm py-12 text-center">No shark news yet.</div>;
  }
  return (
    <div>
      {items.map((item) => (
        <NewsItemRow key={item.id} item={item} />
      ))}
      {loading && <div className="text-gray-500 text-sm py-4 text-center">Loading…</div>}
      {hasMore && !loading && (
        <div className="py-4 text-center">
          <button
            onClick={onLoadMore}
            className="text-sm text-gray-300 hover:text-white px-4 py-2 rounded bg-gray-800 hover:bg-gray-700"
          >
            Load more
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify it builds**

Run: `cd ~/claude/OSAF/frontend && npm run build`
Expected: `✓ built` with no errors.

- [ ] **Step 3: Commit**

```bash
cd ~/claude/OSAF
git add frontend/src/components/news/NewsFeed.jsx
git commit -m "feat(frontend): NewsFeed list container with load-more + states"
```

---

## Task 8: `NewsPage` + route + nav link

**Files:**
- Create: `src/pages/NewsPage.jsx`
- Modify: `src/App.jsx`
- Modify: `src/components/layout/Header.jsx`

**Interfaces:**
- Consumes: `useNews` (Task 4), `NewsTabs`/`NewsSearch`/`NewsFeed` (Tasks 6, 7).
- Produces: route `/news` → `NewsPage`; "News" link in the public nav.

- [ ] **Step 1: Create `NewsPage`**

`src/pages/NewsPage.jsx`:
```jsx
import { useState, useCallback } from "react";
import { useNews } from "../api/useNews";
import NewsTabs from "../components/news/NewsTabs";
import NewsSearch from "../components/news/NewsSearch";
import NewsFeed from "../components/news/NewsFeed";

export default function NewsPage() {
  const [eventType, setEventType] = useState("");
  const [search, setSearch] = useState("");
  const { items, loading, error, hasMore, loadMore } = useNews({ eventType, search });
  const handleSearch = useCallback((v) => setSearch(v), []);

  return (
    <div className="flex-1 overflow-y-auto bg-gray-900">
      <div className="max-w-3xl mx-auto px-4 py-6">
        <h1 className="text-xl font-bold text-white mb-1">Shark News</h1>
        <p className="text-sm text-gray-500 mb-4">
          Recent shark sightings, incidents, and coverage captured from across the web.
        </p>
        <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-2">
          <NewsTabs active={eventType} onChange={setEventType} />
          <div className="sm:ml-auto">
            <NewsSearch value={search} onChange={handleSearch} />
          </div>
        </div>
        <NewsFeed
          items={items}
          loading={loading}
          error={error}
          hasMore={hasMore}
          onLoadMore={loadMore}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add the route in `src/App.jsx`**

Add the import alongside the other page imports:
```jsx
import NewsPage from "./pages/NewsPage";
```
Add the route inside `<Routes>` (e.g. right after the `/database` route):
```jsx
            <Route path="/news" element={<NewsPage />} />
```

- [ ] **Step 3: Add the nav link in `src/components/layout/Header.jsx`**

Insert a "News" entry into the `publicLinks` array (after "Database"):
```jsx
const publicLinks = [
  { to: "/", label: "Map" },
  { to: "/database", label: "Database" },
  { to: "/news", label: "News" },
  { to: "/stats", label: "Statistics" },
  { to: "/about", label: "About" },
];
```

- [ ] **Step 4: Verify build + full test suite**

Run: `cd ~/claude/OSAF/frontend && npm run build && npm test`
Expected: `✓ built` with no errors; Vitest reports all tests passing (safeUrl + formatters + news = 12 tests across 3 files).

- [ ] **Step 5: Commit**

```bash
cd ~/claude/OSAF
git add frontend/src/pages/NewsPage.jsx frontend/src/App.jsx frontend/src/components/layout/Header.jsx
git commit -m "feat(frontend): Shark News page at /news + nav link"
```

---

## Task 9: Manual/browser QA + docs

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Manual QA of the live page**

Start the dev server (`cd ~/claude/OSAF/frontend && npm run dev`) with the backend reachable (or rely on the Vite `/api` proxy). In a browser (e.g. via `/browse`), verify: the "News" nav link routes to `/news`; rows render with event-type chips and times; tabs filter (All/Sightings/Attacks/News); search filters; "Load more" appends without duplicates; a promoted row shows an "incident" link to `/incidents/:id`; the empty state reads well when there are no items. Note: if `news_items` is empty, confirm the empty state, not an error.

- [ ] **Step 2: Append a CHANGELOG entry** under `## [Unreleased]` → `### Added`:

```markdown
- **Shark News feed page (SP2).** Public recency-first feed at `/news` consuming
  `GET /api/v1/news`: media-list rows (thumbnail, event-type chip, title, source
  link-out, relative time, "incident" link on promoted items), event-type tabs
  (All/Sightings/Attacks/News), debounced search, and load-more paging
  (`useNews`). All external URLs pass through a new `safeUrl()` http(s) guard.
  Adds a minimal Vitest harness for the pure logic (safeUrl, relativeTime, news
  paging helpers). Sightings already render across the map/DB/stats via the
  existing classification constants. Spec/plan:
  `docs/superpowers/specs/2026-06-30-osaf-shark-news-feed-page-design.md`,
  `docs/superpowers/plans/2026-06-30-osaf-shark-news-feed-page.md`.
```

- [ ] **Step 3: Commit**

```bash
cd ~/claude/OSAF
git add CHANGELOG.md
git commit -m "docs: changelog — SP2 Shark News feed page"
```

---

## Notes / deviations from spec

- The spec's "test `useNews` logic" is realized by extracting that logic into pure helpers (`src/utils/news.js`, Task 3) which ARE unit-tested; the hook itself (Task 4) is verified by `npm run build`. This honors the "minimal vitest, no render harness (no jsdom/RTL)" decision while still testing the param/paging/dedupe logic.
- Image error handling uses `useState(imgError)` + `onError` to fall back to the colored event-type block (cleaner than DOM-sibling swapping).
- The SP1-deferred `ai_confidence` bound is backend-only and out of SP2 scope; SP2 discharges only the URL/XSS item via `safeUrl`.
- `NewsTabs` uses the app's standard gray active-state (matching `Header`'s nav links) rather than coloring the active tab with `EVENT_TYPE_COLORS` (as the spec loosely suggested) — chosen for visual consistency with the rest of the app. `EVENT_TYPE_COLORS` is still used for the per-row event-type chips/dots and the thumbnail fallback. If you prefer colored active tabs, it's a one-line change.
