import {
  XAxis,
  YAxis,
  ResponsiveContainer,
  Tooltip,
  Area,
  AreaChart,
} from 'recharts';

interface RecallLineChartProps {
  data: Record<string, number>;
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div className="custom-tooltip">
        <p className="text-slate-200 font-medium">召回次数 {label}</p>
        <p className="text-cyan-400 text-lg font-bold">{payload[0].value} 条</p>
      </div>
    );
  }
  return null;
};

export function RecallLineChart({ data }: RecallLineChartProps) {
  const chartData = Object.entries(data).map(([range, count]) => ({
    range,
    count,
  }));

  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
          <defs>
            <linearGradient id="recallGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#00d4ff" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#00d4ff" stopOpacity={0} />
            </linearGradient>
          </defs>
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
          <Tooltip content={<CustomTooltip />} />
          <Area
            type="monotone"
            dataKey="count"
            stroke="#00d4ff"
            strokeWidth={2}
            fill="url(#recallGradient)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
