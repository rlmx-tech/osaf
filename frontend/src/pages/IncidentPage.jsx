import { useParams, useNavigate } from "react-router-dom";
import { useIncident } from "../api/useIncidents";
import {
  CLASSIFICATION_COLORS,
  CLASSIFICATION_LABELS,
  REPORT_SOURCE_LABELS,
  REPORT_PLATFORM_OPTIONS,
} from "../utils/constants";
import { formatDate, formatSpecies, formatCoordinates } from "../utils/formatters";

function isSafeUrl(url) {
  if (!url) return false;
  try {
    const { protocol } = new URL(url);
    return protocol === "https:" || protocol === "http:";
  } catch {
    return false;
  }
}

function Field({ label, value, className = "" }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className={className}>
      <dt className="text-xs text-gray-500 uppercase tracking-wider">{label}</dt>
      <dd className="text-sm text-gray-200 mt-0.5">{value}</dd>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div className="mb-6">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-3 pb-1 border-b border-gray-700">
        {title}
      </h3>
      <dl className="grid grid-cols-2 md:grid-cols-3 gap-4">{children}</dl>
    </div>
  );
}

export default function IncidentPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { incident, loading, error } = useIncident(id);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-gray-900">
        <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center bg-gray-900 text-red-400">
        <div className="text-center">
          <p>Failed to load incident</p>
          <p className="text-sm text-gray-500 mt-1">{error}</p>
          <button
            onClick={() => navigate("/database")}
            className="mt-4 text-sm text-blue-400 hover:text-blue-300"
          >
            Back to database
          </button>
        </div>
      </div>
    );
  }

  if (!incident) return null;

  const species =
    incident.shark_species_confirmed || incident.shark_species_suspected;
  const speciesLabel = species ? formatSpecies(species) : null;
  const scientificName = species || null;

  return (
    <div className="flex-1 overflow-y-auto bg-gray-900 text-white">
      <div className="max-w-4xl mx-auto px-6 py-6">
        {/* Back button + header */}
        <button
          onClick={() => navigate("/database")}
          className="text-sm text-gray-400 hover:text-white mb-4 flex items-center gap-1"
        >
          <span>&larr;</span> Back to database
        </button>

        <div className="flex items-start justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold font-mono">
              {incident.case_number}
            </h1>
            <p className="text-gray-400 mt-1">
              {formatDate(incident.incident_date)} &middot;{" "}
              {incident.location_description}
            </p>
          </div>

          <div className="flex items-center gap-2">
            <span
              className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm"
              style={{
                backgroundColor: `${
                  CLASSIFICATION_COLORS[incident.classification] || "#6b7280"
                }22`,
                color:
                  CLASSIFICATION_COLORS[incident.classification] || "#9ca3af",
              }}
            >
              <span
                className="w-2 h-2 rounded-full"
                style={{
                  backgroundColor:
                    CLASSIFICATION_COLORS[incident.classification] || "#6b7280",
                }}
              />
              {CLASSIFICATION_LABELS[incident.classification] ||
                incident.classification}
            </span>

            {incident.fatal && (
              <span className="px-3 py-1 rounded-full text-sm bg-red-900/30 text-red-400 font-semibold">
                FATAL
              </span>
            )}
          </div>
        </div>

        {/* Description */}
        {incident.description && (
          <div className="mb-6 bg-gray-800/50 rounded-lg p-4">
            <p className="text-sm text-gray-300 leading-relaxed">
              {incident.description}
            </p>
          </div>
        )}

        {/* Location */}
        <Section title="Location">
          <Field label="Location" value={incident.location_description} />
          <Field label="Country" value={incident.country} />
          <Field label="State / Province" value={incident.state_province} />
          <Field label="County / Region" value={incident.county_region} />
          <Field label="Body of Water" value={incident.body_of_water} />
          <Field
            label="Coordinates"
            value={formatCoordinates(incident.longitude, incident.latitude)}
          />
          <Field label="Location Precision" value={incident.location_precision} />
        </Section>

        {/* Shark */}
        <Section title="Shark Information">
          <Field
            label="Species (Confirmed)"
            value={
              incident.shark_species_confirmed
                ? `${formatSpecies(incident.shark_species_confirmed)} (${incident.shark_species_confirmed})`
                : null
            }
          />
          <Field
            label="Species (Suspected)"
            value={
              incident.shark_species_suspected
                ? `${formatSpecies(incident.shark_species_suspected)} (${incident.shark_species_suspected})`
                : null
            }
          />
          {!species && <Field label="Species" value="Unknown" />}
          <Field label="Size Estimate" value={incident.shark_size_estimate} />
          <Field
            label="ID Method"
            value={incident.species_identification_method}
          />
        </Section>

        {/* Victim */}
        <Section title="Victim Information">
          <Field label="Name" value={incident.victim_name} />
          <Field
            label="Age"
            value={incident.victim_age != null ? String(incident.victim_age) : null}
          />
          <Field label="Sex" value={incident.victim_sex} />
          <Field
            label="Activity"
            value={
              incident.victim_activity
                ? incident.victim_activity.charAt(0).toUpperCase() +
                  incident.victim_activity.slice(1)
                : null
            }
          />
          <Field label="Injury Severity" value={incident.victim_injury_severity} />
          <Field
            label="Injury Description"
            value={incident.victim_injury_description}
            className="col-span-2"
          />
        </Section>

        {/* Classification Details */}
        <Section title="Classification">
          <Field
            label="Classification"
            value={
              CLASSIFICATION_LABELS[incident.classification] ||
              incident.classification
            }
          />
          <Field label="Subtype" value={incident.classification_subtype} />
          <Field
            label="Provocation Subtype"
            value={incident.provocation_subtype}
          />
          <Field label="Date Precision" value={incident.date_precision} />
          <Field
            label="Report Source"
            value={REPORT_SOURCE_LABELS[incident.report_source] || incident.report_source}
          />
          <Field
            label="Report Platform"
            value={
              incident.report_platform
                ? (REPORT_PLATFORM_OPTIONS.find((p) => p.value === incident.report_platform)?.label ||
                   incident.report_platform)
                : null
            }
          />
          <Field
            label="Verification Status"
            value={incident.verification_status}
          />
        </Section>

        {/* Sources */}
        {incident.sources && incident.sources.length > 0 && (
          <div className="mb-6">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-3 pb-1 border-b border-gray-700">
              Sources
            </h3>
            <div className="space-y-2">
              {incident.sources.map((source) => (
                <div
                  key={source.id}
                  className="bg-gray-800/50 rounded p-3 text-sm"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-xs bg-gray-700 px-2 py-0.5 rounded text-gray-300">
                      {source.source_type}
                    </span>
                    {source.source_title && (
                      <span className="text-gray-200">{source.source_title}</span>
                    )}
                  </div>
                  {source.source_publisher && (
                    <p className="text-xs text-gray-500 mt-1">
                      {source.source_publisher}
                      {source.source_date && ` — ${formatDate(source.source_date)}`}
                    </p>
                  )}
                  {isSafeUrl(source.source_url) && (
                    <a
                      href={source.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-blue-400 hover:text-blue-300 mt-1 inline-block"
                    >
                      View source &rarr;
                    </a>
                  )}
                  {source.source_notes && (
                    <p className="text-xs text-gray-400 mt-1">
                      {source.source_notes}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Metadata */}
        <div className="text-xs text-gray-600 pt-4 border-t border-gray-800">
          <span>Submitted: {new Date(incident.submitted_at).toLocaleString()}</span>
          <span className="mx-2">|</span>
          <span>Updated: {new Date(incident.updated_at).toLocaleString()}</span>
        </div>
      </div>
    </div>
  );
}
