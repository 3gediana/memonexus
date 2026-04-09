import {
  XAxis,
  YAxis,
  ResponsiveContainer,
  Tooltip,
  Area,
  AreaChart,
  CartesianGrid,
} from 'recharts';

interface RecallTimelineItem {
  date: string;
  recalls: number;
}

interface RecallLineChartProps {
  data: Record<string, number> | RecallTimelineItem[];
}

// 判断是旧格式（区间分布）还是新格式（时间序列）
function isTimelineData(data: any): data is RecallTimelineItem[] {
  if (!Array.isArray(data)) return false;
  if (data.length === 0) return true;
  return typeof data[0] === 'object' && 'date' in data[0] && 'recalls' in data[0];
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div className="custom-tooltip">
        <p className="text-slate-200 font-medium">{label}</p>
        <p className="text-cyan-400 text-lg font-bold">{payload[0].value} 次召回</p>
      </div>
    );
  }
  return null;
};

// 旧格式的区间顺序
const RANGE_ORDER = ['0', '1-5', '6-10', '10+'];

// 将日期格式化为更友好的显示
function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  const month = date.getMonth() + 1;
  const day = date.getDate();
  return `${month}/${day}`;
}

export function RecallLineChart({ data }: RecallLineChartProps) {
  // 如果是时间序列数据
  if (isTimelineData(data) && data.length > 0) {
    const chartData = data.map((item) => ({
      date: formatDate(item.date),
      fullDate: item.date,
      recalls: item.recalls,
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
            <CartesianGrid strokeDasharray="3 3" stroke="#2a3548" vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fill: '#64748b', fontSize: 11 }}
              axisLine={{ stroke: '#2a3548' }}
              tickLine={false}
            />
            <YAxis
              tick={{ fill: '#64748b', fontSize: 11 }}
              axisLine={{ stroke: '#2a3548' }}
              tickLine={false}
              allowDecimals={false}
            />
            <Tooltip content={<CustomTooltip />} />
            <Area
              type="monotone"
              dataKey="recalls"
              stroke="#00d4ff"
              strokeWidth={2}
              fill="url(#recallGradient)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    );
  }

  // 旧格式：区间分布（兼容性保留）
  const chartData = RANGE_ORDER.map((range) => ({
    range,
    count: (data as Record<string, number>)[range] || 0,
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
          <CartesianGrid strokeDasharray="3 3" stroke="#2a3548" vertical={false} />
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
            allowDecimals={false}
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
