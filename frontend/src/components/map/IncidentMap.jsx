import { useState, useCallback } from "react";
import { MapContainer, TileLayer, useMapEvents } from "react-leaflet";
import { useMapData } from "../../api/useMap";
import IncidentMarker from "./IncidentMarker";
import MapLegend from "./MapLegend";
import MapFilters from "./MapFilters";

import "leaflet/dist/leaflet.css";

const DEFAULT_CENTER = [20, 0];
const DEFAULT_ZOOM = 2;

// Persist map viewport across navigation (survives unmount, not page refresh)
let savedCenter = null;
let savedZoom = null;

function MapViewTracker() {
  useMapEvents({
    moveend(e) {
      const map = e.target;
      const c = map.getCenter();
      savedCenter = [c.lat, c.lng];
      savedZoom = map.getZoom();
    },
    zoomend(e) {
      const map = e.target;
      const c = map.getCenter();
      savedCenter = [c.lat, c.lng];
      savedZoom = map.getZoom();
    },
  });
  return null;
}

export default function IncidentMap() {
  const [filters, setFilters] = useState({
    date_from: `${new Date().getFullYear()}-01-01`,
  });
  const { geojson, loading, error } = useMapData(filters);

  const handleFilterChange = useCallback((newFilters) => {
    setFilters(newFilters);
  }, []);

  return (
    <div className="relative w-full h-full">
      <MapContainer
        center={savedCenter || DEFAULT_CENTER}
        zoom={savedZoom ?? DEFAULT_ZOOM}
        minZoom={2}
        maxZoom={18}
        className="w-full h-full"
        style={{ background: "#1a1a2e" }}
        worldCopyJump={true}
      >
        <MapViewTracker />
        <TileLayer
          attribution='&copy; <a href="https://carto.com/">CARTO</a>'
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        />

        {geojson?.features?.map((feature) => (
          <IncidentMarker key={feature.properties.id} feature={feature} />
        ))}
      </MapContainer>

      <MapFilters filters={filters} onFilterChange={handleFilterChange} />
      <MapLegend />

      {loading && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-[1000] bg-gray-900/90 text-white text-xs px-3 py-1.5 rounded-full">
          Loading incidents...
        </div>
      )}

      {error && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-[1000] bg-red-900/90 text-white text-xs px-3 py-1.5 rounded-full">
          Error: {error}
        </div>
      )}

      {geojson && (
        <div className="absolute bottom-6 left-4 z-[1000] bg-gray-900/90 text-gray-400 text-xs px-3 py-1.5 rounded-lg">
          {geojson.features.length} incident{geojson.features.length !== 1 ? "s" : ""}
        </div>
      )}
    </div>
  );
}
