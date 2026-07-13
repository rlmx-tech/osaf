import { useState } from "react";
import {
  CLASSIFICATION_COLORS,
  CLASSIFICATION_LABELS,
  SEVERITY_OPTIONS,
  ACTIVITY_OPTIONS,
} from "../../utils/constants";

export default function MapFilters({ filters, onFilterChange }) {
  const [expanded, setExpanded] = useState(() =>
    typeof window === "undefined" ? true : window.innerWidth >= 768
  );

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
    <div className="absolute left-3 top-3 z-[1000] w-[calc(100%-1.5rem)] max-w-72 md:left-4 md:top-4">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between rounded-lg border border-gray-700/70 bg-gray-900/95 px-3 py-2 text-left text-sm font-medium text-white shadow-lg backdrop-blur-sm"
        aria-expanded={expanded}
      >
        <span>Filters</span>
        <span className="text-gray-400">{expanded ? "−" : "+"}</span>
      </button>

      {expanded && (
        <div className="mt-1 max-h-[calc(100dvh-8.5rem)] overflow-y-auto overflow-x-hidden rounded-lg border border-gray-700/70 bg-gray-900/95 p-3 text-white shadow-xl backdrop-blur-sm">
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
            <div className="grid grid-cols-3 gap-1">
              {[
                { value: undefined, label: "All" },
                { value: true, label: "Fatal" },
                { value: false, label: "Non-fatal" },
              ].map((opt) => (
                <button
                  key={String(opt.value)}
                  onClick={() => onFilterChange({ ...filters, fatal: opt.value })}
                  className={`rounded px-2 py-1.5 text-xs ${
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
            <div className="grid grid-cols-1 gap-1.5">
              <input
                type="date"
                value={filters.date_from || ""}
                onChange={(e) =>
                  onFilterChange({ ...filters, date_from: e.target.value || undefined })
                }
                aria-label="Start date"
                className="min-w-0 w-full rounded border border-gray-600 bg-gray-700 px-2 py-1.5 text-xs text-white"
              />
              <input
                type="date"
                value={filters.date_to || ""}
                onChange={(e) =>
                  onFilterChange({ ...filters, date_to: e.target.value || undefined })
                }
                aria-label="End date"
                className="min-w-0 w-full rounded border border-gray-600 bg-gray-700 px-2 py-1.5 text-xs text-white"
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
            type="button"
            onClick={() => onFilterChange({ date_from: `${new Date().getFullYear()}-01-01` })}
            className="w-full rounded border border-gray-700 py-2 text-center text-xs text-gray-400 hover:border-gray-600 hover:text-white"
          >
            Reset to this year
          </button>
        </div>
      )}
    </div>
  );
}
