import { useEffect, useRef } from 'react';
import { getKeyColor } from '../../mock/statsDashboard';
import type { Memory } from '../../mock/memoryList';

interface MemoryDetailModalProps {
  memory: Memory | null;
  onClose: () => void;
}

export function MemoryDetailModal({ memory, onClose }: MemoryDetailModalProps) {
  const modalRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [onClose]);

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onClose();
  };

  if (!memory) return null;

  const color = getKeyColor(memory.key);

  return (
    <div
      onClick={handleBackdropClick}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200"
    >
      <div
        ref={modalRef}
        className="w-full max-w-lg bg-neural-card border border-neural-border rounded-2xl shadow-2xl animate-in zoom-in-95 duration-200"
      >
        {/* Header */}
        <div className="flex items-start justify-between p-6 border-b border-neural-border">
          <div>
            <span
              className="px-3 py-1 rounded-full text-xs font-medium mb-2 inline-block"
              style={{
                backgroundColor: `${color}20`,
                color: color,
              }}
            >
              {memory.key}
            </span>
            <h2 className="text-xl font-bold text-white font-chinese">
              {memory.tag}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg bg-slate-700/50 flex items-center justify-center text-slate-400 hover:bg-slate-700 hover:text-white transition-colors"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Memory Text */}
          <div>
            <h3 className="text-sm font-medium text-slate-400 mb-2">记忆内容</h3>
            <p className="text-slate-200 font-chinese leading-relaxed">
              {memory.memory}
            </p>
          </div>

          {/* Metadata */}
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-neural-bg/50 rounded-lg p-3">
              <p className="text-xs text-slate-500 mb-1">创建时间</p>
              <p className="text-sm text-slate-300 font-space">
                {new Date(memory.created_at).toLocaleDateString('zh-CN')}
              </p>
            </div>
            <div className="bg-neural-bg/50 rounded-lg p-3">
              <p className="text-xs text-slate-500 mb-1">更新时间</p>
              <p className="text-sm text-slate-300 font-space">
                {new Date(memory.updated_at).toLocaleDateString('zh-CN')}
              </p>
            </div>
          </div>

          {/* Stats */}
          <div className="flex items-center gap-4">
            <div className="flex-1 bg-neural-bg/50 rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-slate-400">价值分</span>
                <span className="text-lg font-bold font-space" style={{ color }}>
                  {memory.value_score.toFixed(2)}
                </span>
              </div>
              <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${memory.value_score * 100}%`,
                    background: `linear-gradient(90deg, ${color}80, ${color})`,
                  }}
                />
              </div>
            </div>
            <div className="bg-neural-bg/50 rounded-lg p-4 text-center min-w-[80px]">
              <p className="text-2xl font-bold text-cyan-400 font-space">
                {memory.recall_count}
              </p>
              <p className="text-xs text-slate-500">召回次数</p>
            </div>
            <div className="bg-neural-bg/50 rounded-lg p-4 text-center min-w-[80px]">
              <p className="text-2xl font-bold text-purple-400 font-space">
                {memory.edges_count}
              </p>
              <p className="text-xs text-slate-500">关联边数</p>
            </div>
          </div>

          {/* Status */}
          <div className="flex items-center gap-2">
            <span
              className={`w-2 h-2 rounded-full ${
                memory.semantic_status === 'valid'
                  ? 'bg-emerald-400'
                  : memory.semantic_status === 'invalid'
                  ? 'bg-rose-400'
                  : 'bg-yellow-400'
              }`}
            />
            <span className="text-sm text-slate-400">
              状态：
              {memory.semantic_status === 'valid'
                ? '有效'
                : memory.semantic_status === 'invalid'
                ? '无效'
                : '已过期'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
