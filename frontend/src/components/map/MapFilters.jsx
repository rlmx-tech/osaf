import { useState } from "react";
import {
  CLASSIFICATION_COLORS,
  CLASSIFICATION_LABELS,
  SEVERITY_OPTIONS,
  ACTIVITY_OPTIONS,
} from "../../utils/constants";

export default function MapFilters({ filters, onFilterChange }) {
  const [expanded, setExpanded] = useState(true);

  const toggleClassification = (key) => {
    const current = filters.classification ? filters.classification.split(",") : [];
    const updated = current.includes(key)
      ? current.filter((c) => c !== key)
      : [...current, key];
    onFilterChange({
      ...filters,
      classification: updated.length > 0 ? updated.join(",") : undefined,
    });
  };

  const activeClassifications = filters.classification
    ? filters.classification.split(",")
    : [];

  return (
    <div className="absolute top-4 left-4 z-[1000] w-64">
      <button
        onClick={() => setExpanded(!expanded)}
        className="bg-gray-900/90 backdrop-blur-sm text-white px-3 py-2 rounded-lg shadow-lg text-sm font-medium w-full text-left flex justify-between items-center"
      >
        <span>Filters</span>
        <span className="text-gray-400">{expanded ? "−" : "+"}</span>
      </button>

      {expanded && (
        <div className="bg-gray-900/90 backdrop-blur-sm text-white rounded-lg shadow-lg mt-1 p-3 max-h-[calc(100vh-200px)] overflow-y-auto">
          {/* Classification */}
          <div className="mb-3">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2">
              Classification
            </h4>
            <div className="space-y-1">
              {Object.entries(CLASSIFICATION_LABELS).map(([key, label]) => (
                <label
                  key={key}
                  className="flex items-center gap-2 text-xs cursor-pointer hover:bg-gray-800/50 rounded px-1 py-0.5"
                >
                  <input
                    type="checkbox"
                    checked={
                      activeClassifications.length === 0 ||
                      activeClassifications.includes(key)
                    }
                    onChange={() => toggleClassification(key)}
                    className="rounded border-gray-600 text-blue-500 focus:ring-blue-500 focus:ring-offset-0 bg-gray-700"
                  />
                  <span
                    className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                    style={{ backgroundColor: CLASSIFICATION_COLORS[key] }}
                  />
                  <span>{label}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Fatal toggle */}
          <div className="mb-3">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2">
              Outcome
            </h4>
            <div className="flex gap-1">
              {[
                { value: undefined, label: "All" },
                { value: true, label: "Fatal" },
                { value: false, label: "Non-fatal" },
              ].map((opt) => (
                <button
                  key={String(opt.value)}
                  onClick={() => onFilterChange({ ...filters, fatal: opt.value })}
                  className={`text-xs px-2 py-1 rounded ${
                    filters.fatal === opt.value
                      ? "bg-blue-600 text-white"
                      : "bg-gray-700 text-gray-300 hover:bg-gray-600"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Date range */}
          <div className="mb-3">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2">
              Date Range
            </h4>
            <div className="flex gap-1">
              <input
                type="date"
                value={filters.date_from || ""}
                onChange={(e) =>
                  onFilterChange({ ...filters, date_from: e.target.value || undefined })
                }
                className="bg-gray-700 text-white text-xs rounded px-2 py-1 w-full border border-gray-600"
              />
              <input
                type="date"
                value={filters.date_to || ""}
                onChange={(e) =>
                  onFilterChange({ ...filters, date_to: e.target.value || undefined })
                }
                className="bg-gray-700 text-white text-xs rounded px-2 py-1 w-full border border-gray-600"
              />
            </div>
          </div>

          {/* Severity */}
          <div className="mb-3">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2">
              Severity
            </h4>
            <select
              value={filters.severity || ""}
              onChange={(e) =>
                onFilterChange({ ...filters, severity: e.target.value || undefined })
              }
              className="bg-gray-700 text-white text-xs rounded px-2 py-1 w-full border border-gray-600"
            >
              <option value="">All severities</option>
              {SEVERITY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Activity */}
          <div className="mb-3">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2">
              Activity
            </h4>
            <select
              value={filters.activity || ""}
              onChange={(e) =>
                onFilterChange({ ...filters, activity: e.target.value || undefined })
              }
              className="bg-gray-700 text-white text-xs rounded px-2 py-1 w-full border border-gray-600"
            >
              <option value="">All activities</option>
              {ACTIVITY_OPTIONS.map((act) => (
                <option key={act} value={act}>
                  {act.charAt(0).toUpperCase() + act.slice(1)}
                </option>
              ))}
            </select>
          </div>

          {/* Clear filters */}
          <button
            onClick={() => onFilterChange({ date_from: `${new Date().getFullYear()}-01-01` })}
            className="text-xs text-gray-400 hover:text-white w-full text-center py-1"
          >
            Clear all filters
          </button>
        </div>
      )}
    </div>
  );
}
