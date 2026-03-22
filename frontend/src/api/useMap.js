import { useState, useEffect, useCallback } from "react";
import client from "./client";

export function useMapData(filters = {}) {
  const [geojson, setGeojson] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async (currentFilters) => {
    setLoading(true);
    setError(null);
    try {
      const params = {};
      if (currentFilters.bbox) params.bbox = currentFilters.bbox;
      if (currentFilters.classification) params.classification = currentFilters.classification;
      if (currentFilters.species) params.species = currentFilters.species;
      if (currentFilters.fatal !== undefined && currentFilters.fatal !== null) params.fatal = currentFilters.fatal;
      if (currentFilters.date_from) params.date_from = currentFilters.date_from;
      if (currentFilters.date_to) params.date_to = currentFilters.date_to;
      if (currentFilters.activity) params.activity = currentFilters.activity;
      if (currentFilters.severity) params.severity = currentFilters.severity;

      const response = await client.get("/incidents/map", { params });
      setGeojson(response.data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData(filters);
  }, [
    filters.bbox,
    filters.classification,
    filters.species,
    filters.fatal,
    filters.date_from,
    filters.date_to,
    filters.activity,
    filters.severity,
    fetchData,
  ]);

  return { geojson, loading, error, refetch: () => fetchData(filters) };
}
