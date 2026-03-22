import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useIncidents } from "../api/useIncidents";
import IncidentTable from "../components/incidents/IncidentTable";
import IncidentFilters from "../components/incidents/IncidentFilters";
import Pagination from "../components/incidents/Pagination";

export default function DatabasePage() {
  const navigate = useNavigate();
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
    <div className="flex-1 flex overflow-hidden bg-gray-900">
      {/* Sidebar */}
      <aside className="w-64 flex-shrink-0 border-r border-gray-700 p-4 overflow-y-auto">
        <h2 className="text-sm font-semibold text-white mb-4">Filters</h2>
        <IncidentFilters filters={filters} onFilterChange={handleFilterChange} />
      </aside>

      {/* Main content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Header bar */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
          <div className="flex items-center gap-3">
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
            <label className="text-xs text-gray-400">Per page:</label>
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
