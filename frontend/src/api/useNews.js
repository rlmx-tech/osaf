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
