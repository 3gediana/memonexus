import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';

interface StrengthPieChartProps {
  data: Record<string, number>;
}

const STRENGTH_COLORS: Record<string, string> = {
  '0-0.3': '#64748b',
  '0.3-0.6': '#f97316',
  '0.6-0.9': '#06b6d4',
  '0.9+': '#22c55e',
};

const STRENGTH_LABELS: Record<string, string> = {
  '0-0.3': '弱关联',
  '0.3-0.6': '中关联',
  '0.6-0.9': '强关联',
  '0.9+': '很强',
};

const CustomTooltip = ({ active, payload }: any) => {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="custom-tooltip">
        <p className="text-slate-200 font-medium">{data.label}</p>
        <p className="text-cyan-400 text-lg font-bold">{data.value} 条</p>
        <p className="text-slate-400 text-sm">{data.percent}%</p>
      </div>
    );
  }
  return null;
};

export function StrengthPieChart({ data }: StrengthPieChartProps) {
  const chartData = Object.entries(data).map(([key, value]) => ({
    name: key,
    label: STRENGTH_LABELS[key as keyof typeof STRENGTH_LABELS],
    value,
    color: STRENGTH_COLORS[key as keyof typeof STRENGTH_COLORS],
  }));

  const total = chartData.reduce((sum, item) => sum + item.value, 0);

  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={chartData}
            cx="50%"
            cy="45%"
            innerRadius={50}
            outerRadius={80}
            paddingAngle={2}
            dataKey="value"
            stroke="none"
          >
            {chartData.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.color} />
            ))}
          </Pie>
          <Tooltip content={<CustomTooltip />} />
        </PieChart>
      </ResponsiveContainer>

      {/* Legend */}
      <div className="flex justify-center gap-4 mt-2">
        {chartData.map((item) => (
          <div key={item.name} className="flex items-center gap-1.5 text-xs">
            <span
              className="w-2.5 h-2.5 rounded-full flex-shrink-0"
              style={{ backgroundColor: item.color }}
            />
            <span className="text-slate-400">{item.label}</span>
            <span className="text-slate-300 ml-1">
              {Math.round((item.value / total) * 100)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
