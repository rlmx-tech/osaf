import { useState } from "react";
import { MapContainer, TileLayer } from "react-leaflet";
import { useMapData } from "../../api/useMap";
import IncidentMarker from "./IncidentMarker";
import MapLegend from "./MapLegend";
import MapFilters from "./MapFilters";

import "leaflet/dist/leaflet.css";

export default function IncidentMap() {
  const [filters, setFilters] = useState({});
  const { geojson, loading, error } = useMapData(filters);

  return (
    <div className="relative w-full h-full">
      <MapContainer
        center={[20, 0]}
        zoom={2}
        minZoom={2}
        maxZoom={18}
        className="w-full h-full"
        style={{ background: "#1a1a2e" }}
        worldCopyJump={true}
      >
        <TileLayer
          attribution='&copy; <a href="https://carto.com/">CARTO</a>'
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        />

        {geojson?.features?.map((feature) => (
          <IncidentMarker key={feature.properties.id} feature={feature} />
        ))}
      </MapContainer>

      <MapFilters filters={filters} onFilterChange={setFilters} />
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
