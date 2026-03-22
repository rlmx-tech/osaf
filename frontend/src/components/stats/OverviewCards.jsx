import { formatSpecies } from "../../utils/formatters";

function StatCard({ label, value, sub, color = "text-white" }) {
  return (
    <div className="bg-gray-800 rounded-lg p-5">
      <p className="text-xs uppercase tracking-wider text-gray-500 mb-1">{label}</p>
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
      {sub && <p className="text-xs text-gray-500 mt-1">{sub}</p>}
    </div>
  );
}

export default function OverviewCards({ data }) {
  if (!data) return null;

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
      <StatCard
        label="Total Incidents"
        value={data.total_incidents.toLocaleString()}
      />
      <StatCard
        label="Fatal Incidents"
        value={data.total_fatal.toLocaleString()}
        color="text-red-400"
      />
      <StatCard
        label="Fatality Rate"
        value={`${data.fatality_rate}%`}
        color="text-amber-400"
      />
      <StatCard
        label="Most Active Country"
        value={data.most_active_country || "—"}
        color="text-blue-400"
      />
      <StatCard
        label="Most Common Species"
        value={data.most_common_species ? formatSpecies(data.most_common_species) : "—"}
        sub={data.most_common_species}
        color="text-teal-400"
      />
      <StatCard
        label="Year Range"
        value={data.year_range || "—"}
      />
    </div>
  );
}
