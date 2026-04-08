import { getKeyColor } from '../../mock/statsDashboard';

interface TopMemory {
  fingerprint: string;
  key: string;
  tag: string;
  recall_count: number;
  value_score: number;
  last_recall_at: string;
}

interface TopMemoryListProps {
  data: TopMemory[];
}

export function TopMemoryList({ data }: TopMemoryListProps) {
  return (
    <div className="space-y-3">
      {data.map((item, index) => {
        const color = getKeyColor(item.key);
        return (
          <div
            key={item.fingerprint}
            className="flex items-center gap-4 p-3 rounded-lg bg-neural-bg/50 hover:bg-neural-card-hover transition-colors cursor-pointer group"
          >
            {/* Rank */}
            <div
              className="w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold font-space"
              style={{
                backgroundColor: `${color}20`,
                color: index < 3 ? color : '#64748b',
              }}
            >
              {index + 1}
            </div>

            {/* Content */}
            <div className="flex-1 min-w-0">
              <p className="text-slate-200 text-sm font-medium truncate font-chinese">
                {item.tag}
              </p>
              <div className="flex items-center gap-2 mt-1">
                <span
                  className="text-xs px-2 py-0.5 rounded-full"
                  style={{ backgroundColor: `${color}20`, color }}
                >
                  {item.key}
                </span>
                <span className="text-xs text-slate-500">
                  {new Date(item.last_recall_at).toLocaleDateString('zh-CN')}
                </span>
              </div>
            </div>

            {/* Stats */}
            <div className="flex items-center gap-4 text-right">
              <div>
                <p className="text-xs text-slate-500">价值分</p>
                <p
                  className="text-sm font-bold font-space"
                  style={{ color: item.value_score > 0.8 ? '#22c55e' : '#f97316' }}
                >
                  {item.value_score.toFixed(2)}
                </p>
              </div>
              <div>
                <p className="text-xs text-slate-500">召回</p>
                <p className="text-sm font-bold text-cyan-400 font-space">
                  {item.recall_count}
                </p>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
