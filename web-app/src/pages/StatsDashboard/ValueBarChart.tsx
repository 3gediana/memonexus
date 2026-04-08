import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Tooltip,
  Cell,
} from 'recharts';

interface ValueBarChartProps {
  data: Record<string, number>;
}

const VALUE_COLORS = [
  '#64748b', // 0-0.2
  '#8b5cf6', // 0.2-0.4
  '#06b6d4', // 0.4-0.6
  '#22c55e', // 0.6-0.8
  '#f97316', // 0.8-1.0
];

const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div className="custom-tooltip">
        <p className="text-slate-200 font-medium">价值分 {label}</p>
        <p className="text-cyan-400 text-lg font-bold">{payload[0].value} 条</p>
      </div>
    );
  }
  return null;
};

export function ValueBarChart({ data }: ValueBarChartProps) {
  const chartData = Object.entries(data).map(([range, count]) => ({
    range,
    count,
  }));

  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
          <XAxis
            dataKey="range"
            tick={{ fill: '#64748b', fontSize: 11 }}
            axisLine={{ stroke: '#2a3548' }}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: '#64748b', fontSize: 11 }}
            axisLine={{ stroke: '#2a3548' }}
            tickLine={false}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(255,255,255,0.05)' }} />
          <Bar dataKey="count" radius={[4, 4, 0, 0]}>
            {chartData.map((_, index) => (
              <Cell key={`cell-${index}`} fill={VALUE_COLORS[index]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
