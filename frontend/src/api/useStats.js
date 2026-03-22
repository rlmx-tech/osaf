import { useState, useEffect } from "react";
import client from "./client";

function useStatsEndpoint(endpoint) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    client
      .get(`/stats/${endpoint}`)
      .then((res) => {
        if (!cancelled) setData(res.data.data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [endpoint]);

  return { data, loading, error };
}

export function useOverview() {
  return useStatsEndpoint("overview");
}

export function useByYear() {
  return useStatsEndpoint("by-year");
}

export function useByCountry() {
  return useStatsEndpoint("by-country");
}

export function useBySpecies() {
  return useStatsEndpoint("by-species");
}

export function useByActivity() {
  return useStatsEndpoint("by-activity");
}

export function useFatalityTrends() {
  return useStatsEndpoint("fatality-trends");
}
