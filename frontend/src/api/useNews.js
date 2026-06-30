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
  const fetchingRef = useRef(false);
  const abortRef = useRef(null);

  const fetchPage = useCallback(
    async (page, replace) => {
      fetchingRef.current = true;
      // Abort any in-flight request so stale responses cannot overwrite newer ones.
      if (abortRef.current) {
        abortRef.current.abort();
      }
      const controller = new AbortController();
      abortRef.current = controller;

      setLoading(true);
      setError(null);
      try {
        const params = buildNewsParams({ eventType, search }, page, PER_PAGE);
        const resp = await client.get("/news", { params, signal: controller.signal });
        const payload = resp.data;
        setMeta(payload.meta);
        pageRef.current = page;
        setItems((prev) => (replace ? payload.data : mergeNewsItems(prev, payload.data)));
      } catch (err) {
        // Ignore cancellations — a newer request is already in flight.
        if (err.code === "ERR_CANCELED" || err.name === "CanceledError") {
          return;
        }
        setError(err.message);
      } finally {
        // Only clear loading/fetchingRef if this is still the latest request.
        if (abortRef.current === controller) {
          setLoading(false);
          fetchingRef.current = false;
        }
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
    if (fetchingRef.current) return;
    fetchPage(pageRef.current + 1, false);
  }, [fetchPage]);

  return { items, meta, loading, error, hasMore: computeHasMore(meta), loadMore };
}
