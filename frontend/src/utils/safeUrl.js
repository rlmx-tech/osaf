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
