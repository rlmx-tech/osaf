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
