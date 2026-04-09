import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts';

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

const renderLegend = (props: any) => {
  const { payload } = props;
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 justify-center px-2">
      {payload.map((entry: any, index: number) => (
        <div key={index} className="flex items-center gap-1 text-xs">
          <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: entry.color }} />
          <span className="text-slate-400">{entry.value}</span>
        </div>
      ))}
    </div>
  );
};

export function KeyPieChart({ data, getKeyColor }: KeyPieChartProps) {
  const chartData = Object.entries(data).map(([name, value]) => ({
    name,
    value,
    color: getKeyColor(name),
  }));

  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={chartData}
            cx="50%"
            cy="40%"
            innerRadius={45}
            outerRadius={70}
            paddingAngle={2}
            dataKey="value"
            stroke="none"
            nameKey="name"
          >
            {chartData.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.color} />
            ))}
          </Pie>
          <Tooltip content={<CustomTooltip />} />
          <Legend content={renderLegend} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
