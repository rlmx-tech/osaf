import { useEffect } from "react";

// Client-side per-route SEO. Upserts <title>, description, canonical, and the
// OG/Twitter text tags on navigation so each route is indexed distinctly.
// Social crawlers that don't run JS still get the static defaults from index.html.

const SITE = "https://osaf.net";
const BRAND = "OSAF — Open Shark Attack File";
const DEFAULT_DESCRIPTION =
  "Open-source, community-driven database of worldwide shark-human incidents. Explore an interactive map, searchable records, and trend statistics — free and fully open.";

function upsertMeta(attr, key, content) {
  let el = document.head.querySelector(`meta[${attr}="${key}"]`);
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute(attr, key);
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}

function upsertCanonical(href) {
  let el = document.head.querySelector('link[rel="canonical"]');
  if (!el) {
    el = document.createElement("link");
    el.setAttribute("rel", "canonical");
    document.head.appendChild(el);
  }
  el.setAttribute("href", href);
}

/**
 * @param {object}  opts
 * @param {string} [opts.title]        Page title (brand is appended automatically).
 * @param {string} [opts.description]  Meta/OG/Twitter description (falls back to site default).
 * @param {string} [opts.path]         Route path for canonical/og:url, e.g. "/database".
 */
export function useSEO({ title, description, path } = {}) {
  useEffect(() => {
    const fullTitle = title ? `${title} — OSAF` : BRAND;
    const desc = description || DEFAULT_DESCRIPTION;
    const url = `${SITE}${path || "/"}`;

    document.title = fullTitle;
    upsertMeta("name", "description", desc);
    upsertMeta("property", "og:title", fullTitle);
    upsertMeta("property", "og:description", desc);
    upsertMeta("property", "og:url", url);
    upsertMeta("name", "twitter:title", fullTitle);
    upsertMeta("name", "twitter:description", desc);
    upsertCanonical(url);
  }, [title, description, path]);
}
