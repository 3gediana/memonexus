import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';

interface KeyPieChartProps {
  data: Record<string, number>;
  getKeyColor: (key: string) => string;
}

const CustomTooltip = ({ active, payload }: any) => {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="custom-tooltip">
        <p className="text-slate-200 font-medium">{data.name}</p>
        <p className="text-cyan-400 text-lg font-bold">{data.value} 条</p>
        <p className="text-slate-400 text-sm">{data.percent}%</p>
      </div>
    );
  }
  return null;
};

export function KeyPieChart({ data, getKeyColor }: KeyPieChartProps) {
  const chartData = Object.entries(data).map(([name, value]) => ({
    name,
    value,
    color: getKeyColor(name),
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
      <div className="grid grid-cols-2 gap-1.5 mt-2">
        {chartData.slice(0, 6).map((item) => (
          <div key={item.name} className="flex items-center gap-1.5 text-xs">
            <span
              className="w-2.5 h-2.5 rounded-full flex-shrink-0"
              style={{ backgroundColor: item.color }}
            />
            <span className="text-slate-400 truncate">{item.name}</span>
            <span className="text-slate-300 ml-auto">
              {Math.round((item.value / total) * 100)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
