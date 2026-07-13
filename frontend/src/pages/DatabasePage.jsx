import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useIncidents } from "../api/useIncidents";
import IncidentTable from "../components/incidents/IncidentTable";
import IncidentFilters from "../components/incidents/IncidentFilters";
import Pagination from "../components/incidents/Pagination";
import { useSEO } from "../utils/useSEO";

export default function DatabasePage() {
  useSEO({
    title: "Shark Attack Database",
    description:
      "Search and filter a public database of documented shark-human incidents worldwide — by species, country, activity, date, classification, and outcome.",
    path: "/database",
  });
  const navigate = useNavigate();
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false);
  const [filters, setFilters] = useState({
    sort: "incident_date",
    order: "desc",
    page: 1,
    per_page: 25,
  });

  const { data, loading, error } = useIncidents(filters);

  const handleFilterChange = useCallback((newFilters) => {
    setFilters((prev) => ({
      ...prev,
      ...newFilters,
      sort: newFilters.sort || prev.sort,
      order: newFilters.order || prev.order,
      per_page: prev.per_page,
    }));
  }, []);

  const handleSortChange = useCallback((sort, order) => {
    setFilters((prev) => ({ ...prev, sort, order }));
  }, []);

  const handlePageChange = useCallback((page) => {
    setFilters((prev) => ({ ...prev, page }));
  }, []);

  const handleRowClick = useCallback(
    (id) => navigate(`/incidents/${id}`),
    [navigate]
  );

  return (
    <div className="flex-1 flex min-w-0 overflow-hidden bg-gray-900">
      {/* Sidebar */}
      <aside className="hidden w-64 flex-shrink-0 overflow-y-auto border-r border-gray-700 p-4 md:block">
        <h2 className="text-sm font-semibold text-white mb-4">Filters</h2>
        <IncidentFilters filters={filters} onFilterChange={handleFilterChange} />
      </aside>

      {mobileFiltersOpen && (
        <div className="fixed inset-0 z-[2100] flex md:hidden" role="dialog" aria-modal="true" aria-label="Incident filters">
          <button
            type="button"
            className="absolute inset-0 bg-black/70"
            onClick={() => setMobileFiltersOpen(false)}
            aria-label="Close filters"
          />
          <aside className="relative h-full w-[min(22rem,90vw)] overflow-y-auto border-r border-gray-700 bg-gray-900 p-4 shadow-2xl">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-white">Filters</h2>
              <button
                type="button"
                onClick={() => setMobileFiltersOpen(false)}
                className="rounded-md border border-gray-700 px-3 py-1.5 text-xs text-gray-300 hover:bg-gray-800"
              >
                Done
              </button>
            </div>
            <IncidentFilters filters={filters} onFilterChange={handleFilterChange} />
          </aside>
        </div>
      )}

      {/* Main content */}
      <main className="flex-1 min-w-0 flex flex-col overflow-hidden">
        {/* Header bar */}
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-700 px-3 py-3 sm:px-4">
          <div className="flex min-w-0 items-center gap-2 sm:gap-3">
            <button
              type="button"
              onClick={() => setMobileFiltersOpen(true)}
              className="rounded-md border border-gray-700 bg-gray-800 px-2.5 py-1.5 text-xs text-gray-200 md:hidden"
            >
              Filters
            </button>
            <h1 className="text-lg font-semibold text-white">
              Incident Database
            </h1>
            {data?.meta && (
              <span className="text-xs text-gray-500 bg-gray-800 px-2 py-0.5 rounded">
                {data.meta.total.toLocaleString()} incidents
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            <label className="hidden text-xs text-gray-400 sm:inline">Per page:</label>
            <select
              value={filters.per_page}
              onChange={(e) =>
                setFilters((prev) => ({
                  ...prev,
                  per_page: Number(e.target.value),
                  page: 1,
                }))
              }
              className="bg-gray-800 text-white text-xs rounded px-2 py-1 border border-gray-700"
            >
              {[10, 25, 50, 100].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Table */}
        <div className="flex-1 overflow-y-auto">
          {loading && (
            <div className="flex items-center justify-center py-16">
              <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            </div>
          )}

          {error && (
            <div className="text-center text-red-400 py-16">
              <p>Failed to load incidents</p>
              <p className="text-sm text-gray-500 mt-1">{error}</p>
            </div>
          )}

          {!loading && !error && data && (
            <IncidentTable
              incidents={data.data}
              sort={filters.sort}
              order={filters.order}
              onSortChange={handleSortChange}
              onRowClick={handleRowClick}
            />
          )}
        </div>

        {/* Pagination */}
        {data?.meta && (
          <Pagination meta={data.meta} onPageChange={handlePageChange} />
        )}
      </main>
    </div>
  );
}
