import { CLASSIFICATION_COLORS, CLASSIFICATION_LABELS } from "../../utils/constants";
import { formatDate, formatSpecies } from "../../utils/formatters";

const COLUMNS = [
  { key: "case_number", label: "Case #", sortable: true },
  { key: "incident_date", label: "Date", sortable: true },
  { key: "country", label: "Location", sortable: true },
  { key: "classification", label: "Type", sortable: true },
  { key: "species", label: "Species", sortable: false },
  { key: "victim_activity", label: "Activity", sortable: true },
  { key: "fatal", label: "Fatal", sortable: true },
];

function SortIcon({ active, direction }) {
  if (!active) {
    return <span className="text-gray-600 ml-1">&udarr;</span>;
  }
  return (
    <span className="text-blue-400 ml-1">
      {direction === "asc" ? "\u2191" : "\u2193"}
    </span>
  );
}

export default function IncidentTable({
  incidents,
  sort,
  order,
  onSortChange,
  onRowClick,
}) {
  const handleSort = (key) => {
    if (!COLUMNS.find((c) => c.key === key)?.sortable) return;
    if (sort === key) {
      onSortChange(key, order === "asc" ? "desc" : "asc");
    } else {
      onSortChange(key, "desc");
    }
  };

  if (!incidents || incidents.length === 0) {
    return (
      <div className="text-center text-gray-500 py-16">
        <p className="text-lg">No incidents found</p>
        <p className="text-sm mt-1">Try adjusting your filters or search terms</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm text-left">
        <thead className="text-xs uppercase tracking-wider text-gray-400 border-b border-gray-700">
          <tr>
            {COLUMNS.map((col) => (
              <th
                key={col.key}
                onClick={() => col.sortable && handleSort(col.key)}
                className={`px-4 py-3 whitespace-nowrap ${
                  col.sortable
                    ? "cursor-pointer hover:text-gray-200 select-none"
                    : ""
                }`}
              >
                {col.label}
                {col.sortable && (
                  <SortIcon active={sort === col.key} direction={order} />
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800">
          {incidents.map((incident) => (
            <tr
              key={incident.id}
              onClick={() => onRowClick(incident.id)}
              className="hover:bg-gray-800/50 cursor-pointer transition-colors"
            >
              <td className="px-4 py-3 font-mono text-xs text-blue-400">
                {incident.case_number}
              </td>
              <td className="px-4 py-3 whitespace-nowrap text-gray-300">
                {formatDate(incident.incident_date)}
              </td>
              <td className="px-4 py-3 text-gray-300">
                <div>{incident.location_description}</div>
                <div className="text-xs text-gray-500">
                  {[incident.state_province, incident.country]
                    .filter(Boolean)
                    .join(", ")}
                </div>
              </td>
              <td className="px-4 py-3">
                <span className="inline-flex items-center gap-1.5">
                  <span
                    className="w-2 h-2 rounded-full flex-shrink-0"
                    style={{
                      backgroundColor:
                        CLASSIFICATION_COLORS[incident.classification] ||
                        "#6b7280",
                    }}
                  />
                  <span className="text-gray-300">
                    {CLASSIFICATION_LABELS[incident.classification] ||
                      incident.classification}
                  </span>
                </span>
              </td>
              <td className="px-4 py-3 text-gray-300">
                {formatSpecies(
                  incident.shark_species_confirmed ||
                    incident.shark_species_suspected
                )}
              </td>
              <td className="px-4 py-3 text-gray-300 capitalize">
                {incident.victim_activity || "—"}
              </td>
              <td className="px-4 py-3">
                {incident.fatal ? (
                  <span className="text-red-400 font-semibold text-xs uppercase">
                    Fatal
                  </span>
                ) : (
                  <span className="text-gray-500 text-xs">No</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
