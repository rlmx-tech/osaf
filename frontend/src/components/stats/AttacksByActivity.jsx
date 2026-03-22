import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-xs">
      <p className="text-gray-300 font-semibold mb-1">{label}</p>
      <p style={{ color: payload[0].color }}>Count: {payload[0].value}</p>
    </div>
  );
};

export default function AttacksByActivity({ data }) {
  if (!data || data.length === 0) return null;

  const chartData = data.map((d) => ({
    activity: d.activity.charAt(0).toUpperCase() + d.activity.slice(1),
    count: d.count,
  }));

  return (
    <div className="bg-gray-800 rounded-lg p-5">
      <h3 className="text-sm font-semibold text-white mb-4">
        Incidents by Victim Activity
      </h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis
            dataKey="activity"
            stroke="#9ca3af"
            fontSize={11}
            angle={-35}
            textAnchor="end"
            height={60}
          />
          <YAxis stroke="#9ca3af" fontSize={12} allowDecimals={false} />
          <Tooltip content={<CustomTooltip />} />
          <Bar dataKey="count" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
