import { useState } from "react";
import {
  CLASSIFICATION_COLORS,
  CLASSIFICATION_LABELS,
  REPORT_SOURCE_LABELS,
  SEVERITY_OPTIONS,
  ACTIVITY_OPTIONS,
} from "../../utils/constants";

export default function IncidentFilters({ filters, onFilterChange }) {
  const [searchInput, setSearchInput] = useState(filters.search || "");

  const handleSearch = (e) => {
    e.preventDefault();
    onFilterChange({ ...filters, search: searchInput || undefined, page: 1 });
  };

  const toggleClassification = (key) => {
    const current = filters.classification
      ? filters.classification.split(",")
      : [];
    const updated = current.includes(key)
      ? current.filter((c) => c !== key)
      : [...current, key];
    onFilterChange({
      ...filters,
      classification: updated.length > 0 ? updated.join(",") : undefined,
      page: 1,
    });
  };

  const activeClassifications = filters.classification
    ? filters.classification.split(",")
    : [];

  const setFilter = (key, value) => {
    onFilterChange({ ...filters, [key]: value || undefined, page: 1 });
  };

  const activeCount = Object.entries(filters).filter(
    ([k, v]) => v !== undefined && k !== "page" && k !== "per_page" && k !== "sort" && k !== "order"
  ).length;

  return (
    <div className="space-y-4">
      {/* Search */}
      <form onSubmit={handleSearch}>
        <div className="relative">
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search incidents..."
            className="w-full bg-gray-800 text-white text-sm rounded-lg px-4 py-2.5 pl-9 border border-gray-700 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none placeholder-gray-500"
          />
          <svg
            className="absolute left-3 top-3 w-4 h-4 text-gray-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
        </div>
      </form>

      {/* Classification */}
      <div>
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
              <span className="text-gray-300">{label}</span>
            </label>
          ))}
        </div>
      </div>

      {/* Fatal */}
      <div>
        <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2">
          Outcome
        </h4>
        <div className="flex gap-1">
          {[
            { value: undefined, label: "All" },
            { value: "true", label: "Fatal" },
            { value: "false", label: "Non-fatal" },
          ].map((opt) => (
            <button
              key={String(opt.value)}
              onClick={() => setFilter("fatal", opt.value)}
              className={`text-xs px-3 py-1.5 rounded ${
                String(filters.fatal) === String(opt.value)
                  ? "bg-blue-600 text-white"
                  : "bg-gray-800 text-gray-300 hover:bg-gray-700"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Date Range */}
      <div>
        <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2">
          Date Range
        </h4>
        <div className="space-y-1">
          <input
            type="date"
            value={filters.date_from || ""}
            onChange={(e) => setFilter("date_from", e.target.value)}
            className="bg-gray-800 text-white text-xs rounded px-2 py-1.5 w-full border border-gray-700"
          />
          <input
            type="date"
            value={filters.date_to || ""}
            onChange={(e) => setFilter("date_to", e.target.value)}
            className="bg-gray-800 text-white text-xs rounded px-2 py-1.5 w-full border border-gray-700"
          />
        </div>
      </div>

      {/* Severity */}
      <div>
        <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2">
          Severity
        </h4>
        <select
          value={filters.severity || ""}
          onChange={(e) => setFilter("severity", e.target.value)}
          className="bg-gray-800 text-white text-xs rounded px-2 py-1.5 w-full border border-gray-700"
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
      <div>
        <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2">
          Activity
        </h4>
        <select
          value={filters.activity || ""}
          onChange={(e) => setFilter("activity", e.target.value)}
          className="bg-gray-800 text-white text-xs rounded px-2 py-1.5 w-full border border-gray-700"
        >
          <option value="">All activities</option>
          {ACTIVITY_OPTIONS.map((act) => (
            <option key={act} value={act}>
              {act.charAt(0).toUpperCase() + act.slice(1)}
            </option>
          ))}
        </select>
      </div>

      {/* Report Source */}
      <div>
        <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2">
          Report Source
        </h4>
        <select
          value={filters.report_source || ""}
          onChange={(e) => setFilter("report_source", e.target.value)}
          className="bg-gray-800 text-white text-xs rounded px-2 py-1.5 w-full border border-gray-700"
        >
          <option value="">All sources</option>
          {Object.entries(REPORT_SOURCE_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
      </div>

      {/* Clear */}
      {activeCount > 0 && (
        <button
          onClick={() => {
            setSearchInput("");
            onFilterChange({});
          }}
          className="text-xs text-gray-400 hover:text-white w-full text-center py-2 border border-gray-700 rounded hover:border-gray-600"
        >
          Clear all filters ({activeCount})
        </button>
      )}
    </div>
  );
}
