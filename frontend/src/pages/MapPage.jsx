import IncidentMap from "../components/map/IncidentMap";
import { useSEO } from "../utils/useSEO";

export default function MapPage() {
  useSEO({
    title: "Interactive Shark Attack Map",
    description:
      "Explore an interactive world map of documented shark-human incidents, color-coded by ISAF classification. Filter by species, activity, date, and outcome.",
    path: "/",
  });
  return (
    <div className="flex-1 relative">
      <IncidentMap />
    </div>
  );
}
