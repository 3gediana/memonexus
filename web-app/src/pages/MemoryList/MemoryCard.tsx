import { getKeyColor } from '../../mock/statsDashboard';
import type { Memory } from '../../mock/memoryList';

interface MemoryCardProps {
  memory: Memory;
  onClick: () => void;
}

export function MemoryCard({ memory, onClick }: MemoryCardProps) {
  const color = getKeyColor(memory.key);

  return (
    <div
      onClick={onClick}
      className="glass-card rounded-xl p-5 cursor-pointer group hover:bg-neural-card-hover transition-all duration-200 hover:shadow-lg hover:shadow-black/20"
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <span
            className="px-3 py-1 rounded-full text-xs font-medium"
            style={{
              backgroundColor: `${color}20`,
              color: color,
            }}
          >
            {memory.key}
          </span>
          <h3 className="text-slate-200 font-medium font-chinese">
            {memory.tag}
          </h3>
        </div>
        <svg
          className="w-5 h-5 text-slate-500 opacity-0 group-hover:opacity-100 transition-opacity"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path d="m9 18 6-6-6-6" />
        </svg>
      </div>

      {/* Content */}
      <p className="text-slate-400 text-sm line-clamp-3 mb-4 font-chinese">
        {memory.memory}
      </p>

      {/* Metrics */}
      <div className="flex items-center gap-4 pt-3 border-t border-neural-border">
        {/* Value Score */}
        <div className="flex-1">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-slate-500">价值分</span>
            <span className="text-xs font-medium font-space" style={{ color }}>
              {memory.value_score.toFixed(2)}
            </span>
          </div>
          <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${memory.value_score * 100}%`,
                background: `linear-gradient(90deg, ${color}80, ${color})`,
              }}
            />
          </div>
        </div>

        {/* Recall Count */}
        <div className="text-center px-3">
          <p className="text-lg font-bold text-cyan-400 font-space">
            {memory.recall_count}
          </p>
          <p className="text-xs text-slate-500">召回</p>
        </div>

        {/* Edges Count */}
        <div className="text-center px-3">
          <p className="text-lg font-bold text-purple-400 font-space">
            {memory.edges_count}
          </p>
          <p className="text-xs text-slate-500">关联</p>
        </div>
      </div>
    </div>
  );
}
