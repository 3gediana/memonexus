import { useEffect, useState, useRef } from 'react';
import type { AgentEvent } from '../../mock/chatDemo';

interface AgentEventLogProps {
  events: AgentEvent[];
  speed: number; // 1 = normal, 0.5 = slow, 2 = fast
  onComplete?: () => void;
}

export function AgentEventLog({ events, speed, onComplete }: AgentEventLogProps) {
  const [visibleEvents, setVisibleEvents] = useState<AgentEvent[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const logsEndRef = useRef<HTMLDivElement>(null);

  // 自动滚动
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [visibleEvents]);

  // 重置当events变化时
  useEffect(() => {
    setVisibleEvents([]);
    setCurrentIndex(0);
  }, [events]);

  // 逐步显示事件
  useEffect(() => {
    if (currentIndex >= events.length) {
      onComplete?.();
      return;
    }

    const delay = currentIndex === 0 ? 300 : 800 / speed;

    const timer = setTimeout(() => {
      setVisibleEvents((prev) => [...prev, events[currentIndex]]);
      setCurrentIndex((prev) => prev + 1);
    }, delay);

    return () => clearTimeout(timer);
  }, [currentIndex, events, speed, onComplete]);

  const getDirectionIcon = (direction: string) => {
    switch (direction) {
      case 'call':
        return <span className="text-cyan-400">→</span>;
      case 'return':
        return <span className="text-emerald-400">←</span>;
      case 'error':
        return <span className="text-red-400">✗</span>;
      default:
        return null;
    }
  };

  const getActionColor = (result?: string) => {
    if (!result) return 'text-slate-400';
    if (result.includes('✓') || result.includes('返回')) return 'text-emerald-400';
    if (result.includes('⚠') || result.includes('duplicate')) return 'text-amber-400';
    if (result.includes('✗') || result.includes('error')) return 'text-red-400';
    if (result.includes('→')) return 'text-blue-400';
    return 'text-slate-400';
  };

  return (
    <div className="h-full flex flex-col bg-neural-card/50 border-l border-neural-border">
      {/* Header */}
      <div className="px-4 py-3 border-b border-neural-border bg-neural-card/80">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="3" />
              <path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83" />
            </svg>
          </div>
          <div>
            <h3 className="text-sm font-medium text-white">Agent 事件流</h3>
            <p className="text-xs text-slate-400">{events.length} 个事件</p>
          </div>
        </div>
      </div>

      {/* Events */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2 agent-scroll">
        {visibleEvents.map((event) => (
          <div
            key={event.id}
            className="bg-neural-bg/80 border border-neural-border rounded-lg p-3 text-xs animate-fadeIn"
          >
            {/* 时间戳 + Agent */}
            <div className="flex items-center gap-2 mb-2">
              <span className="text-slate-500 font-mono">{event.timestamp}</span>
              <span
                className="px-2 py-0.5 rounded text-xs font-medium"
                style={{
                  backgroundColor: `${event.agentColor}20`,
                  color: event.agentColor,
                }}
              >
                {event.agentLabel}
              </span>
              <span className="text-slate-500">{getDirectionIcon(event.direction)}</span>
            </div>

            {/* 工具名 */}
            <div className="font-mono text-cyan-400 mb-1">
              {event.toolName}
            </div>

            {/* 参数 */}
            {event.params && event.params !== '{}' && (
              <div className="mt-2 p-2 bg-neural-card rounded text-slate-400 font-mono truncate">
                {event.params}
              </div>
            )}

            {/* 结果 */}
            {event.result && (
              <div className={`mt-2 ${getActionColor(event.result)}`}>
                {event.result}
              </div>
            )}

            {/* 耗时 */}
            {event.duration && (
              <div className="mt-1 text-slate-500">
                {event.duration}ms
              </div>
            )}
          </div>
        ))}

        {/* 正在进行的指示器 */}
        {currentIndex < events.length && (
          <div className="flex items-center gap-2 text-slate-500 text-xs py-2">
            <span className="w-2 h-2 bg-cyan-400 rounded-full animate-pulse" />
            <span>处理中...</span>
          </div>
        )}

        {/* 完成 */}
        {visibleEvents.length > 0 && currentIndex >= events.length && (
          <div className="text-center py-4">
            <span className="text-emerald-400 text-xs">✓ 流程完成</span>
          </div>
        )}

        <div ref={logsEndRef} />
      </div>
    </div>
  );
}
