import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-xs">
      <p className="text-gray-300 font-semibold mb-1">{label}</p>
      {payload.map((entry) => (
        <p key={entry.name} style={{ color: entry.color }}>
          {entry.name}: {entry.value}
        </p>
      ))}
    </div>
  );
};

export default function AttacksByCountry({ data }) {
  if (!data || data.length === 0) return null;

  // API returns countries sorted by count desc, and recharts renders data[0] at
  // the top of a vertical axis. Show the top 10 so every bar gets a label —
  // rendering all 20 in this height makes recharts thin the labels and skip the
  // #1 country (United States), making #2 (Australia) look like #1.
  const chartData = data.slice(0, 10).map((d) => ({
    country: d.country,
    "Non-Fatal": d.count - d.fatal,
    Fatal: d.fatal,
  }));

  return (
    <div className="bg-gray-800 rounded-lg p-5">
      <h3 className="text-sm font-semibold text-white mb-4">
        Incidents by Country
      </h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={chartData} layout="vertical">
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" horizontal={false} />
          <XAxis type="number" stroke="#9ca3af" fontSize={12} allowDecimals={false} />
          <YAxis
            type="category"
            dataKey="country"
            stroke="#9ca3af"
            fontSize={11}
            width={120}
            interval={0}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend wrapperStyle={{ fontSize: "12px", color: "#9ca3af" }} />
          <Bar dataKey="Non-Fatal" stackId="a" fill="#3b82f6" />
          <Bar dataKey="Fatal" stackId="a" fill="#ef4444" radius={[0, 2, 2, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
