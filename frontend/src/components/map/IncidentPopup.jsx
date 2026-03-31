import { Popup } from "react-leaflet";
import { Link } from "react-router-dom";
import { CLASSIFICATION_LABELS } from "../../utils/constants";
import { formatDate, formatSpecies } from "../../utils/formatters";

export default function IncidentPopup({ properties }) {
  const {
    id,
    case_number,
    incident_date,
    classification,
    classification_subtype,
    species,
    activity,
    severity,
    fatal,
    location,
    country,
  } = properties;

  return (
    <Popup maxWidth={320} className="osaf-popup">
      <div className="text-sm">
        <div className="flex items-center justify-between mb-1">
          <span className="font-bold text-gray-900">{case_number}</span>
          {fatal && (
            <span className="bg-red-600 text-white text-xs px-1.5 py-0.5 rounded font-medium">
              FATAL
            </span>
          )}
        </div>

        <div className="text-gray-600 text-xs mb-2">
          {formatDate(incident_date)}
        </div>

        <div className="space-y-1 text-xs">
          <div>
            <span className="font-medium text-gray-700">Location: </span>
            <span>{location}, {country}</span>
          </div>
          <div>
            <span className="font-medium text-gray-700">Classification: </span>
            <span>{CLASSIFICATION_LABELS[classification] || classification}</span>
            {classification_subtype && (
              <span className="text-gray-500"> ({classification_subtype.replace(/_/g, " ")})</span>
            )}
          </div>
          {species && (
            <div>
              <span className="font-medium text-gray-700">Species: </span>
              <span>{formatSpecies(species)}</span>
            </div>
          )}
          {activity && (
            <div>
              <span className="font-medium text-gray-700">Activity: </span>
              <span className="capitalize">{activity}</span>
            </div>
          )}
          {severity && (
            <div>
              <span className="font-medium text-gray-700">Severity: </span>
              <span className="capitalize">{severity.replace(/_/g, " ")}</span>
            </div>
          )}
        </div>

        <Link
          to={`/incidents/${id}`}
          className="block mt-2 text-center text-xs font-medium text-blue-600 hover:text-blue-800 hover:underline"
        >
          View Full Details →
        </Link>
      </div>
    </Popup>
  );
}
