import { CircleMarker } from "react-leaflet";
import { CLASSIFICATION_COLORS } from "../../utils/constants";
import IncidentPopup from "./IncidentPopup";

export default function IncidentMarker({ feature }) {
  const { properties, geometry } = feature;
  const [lon, lat] = geometry.coordinates;
  const color = CLASSIFICATION_COLORS[properties.classification] || "#95a5a6";

  return (
    <CircleMarker
      center={[lat, lon]}
      radius={properties.fatal ? 9 : 7}
      pathOptions={{
        color: properties.fatal ? "#1a1a2e" : color,
        fillColor: color,
        fillOpacity: 0.85,
        weight: properties.fatal ? 2.5 : 1.5,
      }}
    >
      <IncidentPopup properties={properties} />
    </CircleMarker>
  );
}
