import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { formatSpecies } from "../../utils/formatters";

const COLORS = [
  "#3b82f6",
  "#ef4444",
  "#f59e0b",
  "#10b981",
  "#8b5cf6",
  "#ec4899",
  "#06b6d4",
  "#f97316",
  "#6366f1",
  "#14b8a6",
];

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const d = payload[0];
  return (
    <div className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-xs">
      <p className="text-gray-300 font-semibold">{d.name}</p>
      <p className="text-gray-400">{d.payload.scientific}</p>
      <p style={{ color: d.payload.fill }}>Count: {d.value}</p>
    </div>
  );
};

export default function AttacksBySpecies({ data }) {
  if (!data || data.length === 0) return null;

  const chartData = data.map((d, i) => ({
    name: formatSpecies(d.species),
    scientific: d.species,
    value: d.count,
    fill: COLORS[i % COLORS.length],
  }));

  return (
    <div className="bg-gray-800 rounded-lg p-5">
      <h3 className="text-sm font-semibold text-white mb-4">
        Incidents by Species
      </h3>
      <ResponsiveContainer width="100%" height={300}>
        <PieChart>
          <Pie
            data={chartData}
            cx="50%"
            cy="50%"
            innerRadius={60}
            outerRadius={100}
            paddingAngle={2}
            dataKey="value"
          >
            {chartData.map((entry, i) => (
              <Cell key={i} fill={entry.fill} />
            ))}
          </Pie>
          <Tooltip content={<CustomTooltip />} />
          <Legend
            wrapperStyle={{ fontSize: "11px", color: "#9ca3af" }}
            formatter={(value) => <span className="text-gray-400">{value}</span>}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
