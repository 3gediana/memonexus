import { useState, useEffect, useCallback, useRef } from 'react';
import { AGENTS } from '../../mock/agentFlow';
import { useStreamConnection } from '../../hooks/useStreamConnection';

const CARD_WIDTH = 160;
const CARD_HEIGHT = 90;

interface KeyAgentInfo {
  name: string;
  memoryCount: number;
  status: 'idle' | 'working' | 'completed';
  lastActivity?: string;
}

interface AgentEvent {
  id: string;
  timestamp: string;
  agentLabel: string;
  agentColor: string;
  direction: 'call' | 'return' | 'error';
  toolName: string;
  params?: string;
  result?: string;
  duration?: number;
}

const AGENT_CONFIG: Record<string, { color: string; label: string; description: string; tools: string[] }> = {
  RoutingAgent: {
    color: '#3B82F6',
    label: '路由Agent',
    description: '判断消息是否值得记忆，分配到哪个Key',
    tools: ['get_key_summaries', 'assign_memory_to_keys'],
  },
  KeyDecisionAgent: {
    color: '#22C55E',
    label: '记忆审核',
    description: '新增 / 替换 / 驳回 / 标记重复',
    tools: ['add_memory_to_key', 'replace_memory_in_key', 'reject_candidate', 'mark_duplicate'],
  },
  KeyEdgeBuilderAgent: {
    color: '#F97316',
    label: '同Key建边',
    description: '与同Key已有记忆建立关联边',
    tools: ['build_edges'],
  },
  CrossKeyAssocAgent: {
    color: '#A855F7',
    label: '跨Key关联',
    description: '与其他Key下的记忆建立跨域关联',
    tools: ['create_edges'],
  },
  CompressionAgent: {
    color: '#6B7280',
    label: '对话压缩',
    description: '上下文超阈值时压缩对话历史',
    tools: [],
  },
  DialogueAgent: {
    color: '#06B6D4',
    label: '对话管理',
    description: '召回记忆、生成回复、引用上报',
    tools: ['recall_from_key', 'add_to_memory_space', 'remove_from_memory_space', 'update_memory_space', 'report_hits'],
  },
};

function AgentCard({ color, label, description, status, onClick }: {
  color: string;
  label: string;
  description: string;
  status: 'idle' | 'working' | 'completed' | 'error';
  onClick: () => void;
}) {
  const isActive = status !== 'idle';
  const statusColor = status === 'working' ? '#22C55E' : status === 'completed' ? '#22C55E' : status === 'error' ? '#EF4444' : '#6B7280';
  const borderColor = status === 'working' ? color : status === 'completed' ? '#22C55E' : status === 'error' ? '#EF4444' : '#475569';

  return (
    <div
      className="relative cursor-pointer transition-all duration-300 hover:scale-105"
      style={{ width: CARD_WIDTH }}
      onClick={onClick}
    >
      <div
        className="rounded-2xl p-4 border-2 transition-all duration-300"
        style={{
          borderColor,
          backgroundColor: status === 'idle' ? 'rgba(30, 41, 59, 0.95)' : `${color}20`,
          boxShadow: status === 'working' ? `0 0 30px ${color}60` : 'none',
          height: CARD_HEIGHT,
        }}
      >
        <div className="flex items-center gap-2">
          <div
            className="w-3 h-3 rounded-full flex-shrink-0"
            style={{
              backgroundColor: statusColor,
              boxShadow: isActive ? `0 0 10px ${statusColor}` : 'none',
            }}
          />
          <div className="flex-1 min-w-0">
            <span className="text-xs font-bold text-white truncate block">{label}</span>
            <p className="text-[10px] text-slate-400 truncate mt-0.5">{description}</p>
          </div>
        </div>
        {status === 'working' && (
          <div className="absolute -bottom-1 left-1/2 -translate-x-1/2 px-2 py-0.5 bg-emerald-500 rounded-full text-[9px] text-white font-medium">
            工作中
          </div>
        )}
        {status === 'completed' && (
          <div className="absolute -bottom-1 left-1/2 -translate-x-1/2 px-2 py-0.5 bg-slate-600 rounded-full text-[9px] text-white font-medium">
            完成
          </div>
        )}
      </div>
    </div>
  );
}

function KeyAgentCard({ keyName, memoryCount, status, color }: {
  keyName: string;
  memoryCount: number;
  status: 'idle' | 'working' | 'completed';
  color: string;
}) {
  const borderColor = status === 'completed' ? '#22C55E' : status === 'working' ? color : '#475569';

  return (
    <div
      className="relative transition-all duration-300"
      style={{ width: CARD_WIDTH }}
    >
      <div
        className="rounded-2xl p-4 border-2"
        style={{
          borderColor,
          backgroundColor: status === 'completed' ? 'rgba(34, 197, 94, 0.15)' : 'rgba(30, 41, 59, 0.95)',
          boxShadow: status === 'completed' ? '0 0 20px rgba(34, 197, 94, 0.3)' : 'none',
          height: CARD_HEIGHT,
        }}
      >
        <div className="flex items-center gap-2">
          <div
            className="w-3 h-3 rounded-full flex-shrink-0"
            style={{
              backgroundColor: status === 'idle' ? '#6B7280' : '#22C55E',
              boxShadow: status !== 'idle' ? '0 0 10px #22C55E' : 'none',
            }}
          />
          <div className="flex-1 min-w-0">
            <span className="text-xs font-bold capitalize text-white truncate block">{keyName}</span>
            <p className="text-[10px] text-slate-400 mt-0.5">{memoryCount} 条记忆</p>
          </div>
        </div>
        {status === 'completed' && (
          <div className="absolute -bottom-1 left-1/2 -translate-x-1/2 px-2 py-0.5 bg-slate-600 rounded-full text-[9px] text-white font-medium">
            已同步
          </div>
        )}
      </div>
    </div>
  );
}

function EventLogItem({ event }: { event: AgentEvent }) {
  const getDirectionIcon = () => {
    switch (event.direction) {
      case 'call': return <span className="text-cyan-400">→</span>;
      case 'return': return <span className="text-emerald-400">←</span>;
      case 'error': return <span className="text-red-400">✗</span>;
    }
  };

  return (
    <div className="bg-slate-800/90 border border-slate-700 rounded-xl p-3 mb-2">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-[10px] text-slate-500 font-mono">{event.timestamp}</span>
        <span
          className="px-2 py-0.5 rounded text-[10px] font-medium"
          style={{
            backgroundColor: `${event.agentColor}20`,
            color: event.agentColor,
          }}
        >
          {event.agentLabel}
        </span>
        {getDirectionIcon()}
      </div>
      <div className="font-mono text-cyan-400 text-xs">
        {event.toolName}
      </div>
      {event.result && (
        <div className={`text-[10px] mt-1 ${event.result.includes('✓') || event.result.includes('返回') ? 'text-emerald-400' : 'text-slate-400'}`}>
          {event.result}
        </div>
      )}
      {event.duration && (
        <div className="text-[10px] text-slate-500 mt-1">{event.duration}ms</div>
      )}
    </div>
  );
}

export function AgentFlow() {
  const [keyAgents, setKeyAgents] = useState<KeyAgentInfo[]>([]);
  const [agentStatuses] = useState<Record<string, string>>({
    RoutingAgent: 'idle',
    KeyDecisionAgent: 'idle',
    KeyEdgeBuilderAgent: 'idle',
    CrossKeyAssocAgent: 'idle',
    CompressionAgent: 'idle',
    DialogueAgent: 'idle',
  });
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [instanceName, setInstanceName] = useState('');
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchMonitorData = useCallback(async () => {
    try {
      const res = await fetch('/api/monitor/status');
      if (res.ok) {
        const json = await res.json();
        const data = json.data || json;
        setInstanceName(data.instance || '未知实例');

        if (data.memory?.by_key) {
          const keyList = Object.entries(data.memory.by_key).map(([name, count]) => ({
            name,
            memoryCount: count as number,
            status: 'completed' as const,
          }));
          setKeyAgents(keyList);
        }
      }
    } catch (err) {
      console.error('Failed to fetch monitor data:', err);
    }
  }, []);

  const { connect, disconnect } = useStreamConnection({
    onAgentThinking: (agent, phase) => {
      setEvents(prev => [...prev, {
        id: `evt_${Date.now()}_${Math.random()}`,
        timestamp: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
        agentLabel: agent,
        agentColor: '#8b5cf6',
        direction: 'call',
        toolName: `[thinking] ${phase}`,
      }]);
    },
    onAgentToolCall: (agent, tool, params) => {
      setEvents(prev => [...prev, {
        id: `evt_${Date.now()}_${Math.random()}`,
        timestamp: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
        agentLabel: agent,
        agentColor: '#8b5cf6',
        direction: 'call',
        toolName: tool,
        params: params ? JSON.stringify(params) : undefined,
      }]);
    },
    onAgentResult: (agent, result) => {
      setEvents(prev => [...prev, {
        id: `evt_${Date.now()}_${Math.random()}`,
        timestamp: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
        agentLabel: agent,
        agentColor: '#22C55E',
        direction: 'return',
        toolName: 'result',
        result: typeof result === 'string' ? result : JSON.stringify(result),
      }]);
    },
  });

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await fetchMonitorData();
      setLoading(false);
    };
    init();

    // Establish SSE connection
    connect('', '', 0);

    pollTimerRef.current = setInterval(fetchMonitorData, 10000);
    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
      disconnect();
    };
  }, [fetchMonitorData, connect, disconnect]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center neural-grid">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-cyan-500/30 border-t-cyan-500 rounded-full animate-spin mx-auto mb-4" />
          <p className="text-slate-400">加载Agent状态...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full neural-grid flex overflow-hidden">
      <div className="flex-1 flex flex-col min-w-0 overflow-auto">
        <div className="px-8 py-5 border-b border-slate-700/50 bg-slate-900/80 flex-shrink-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-pink-500 via-rose-500 to-purple-500 flex items-center justify-center shadow-lg shadow-pink-500/30">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="3" />
                  <path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83" />
                </svg>
              </div>
              <div>
                <h1 className="text-xl font-bold text-white">Agent 协作监控</h1>
                <p className="text-sm text-slate-400">
                  实例: {instanceName} · {keyAgents.length} 个KeyAgent
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={() => { fetchMonitorData(); }}
                className="px-3 py-1.5 rounded-lg text-xs bg-neural-bg/50 hover:bg-neural-bg border border-neural-border transition-colors text-slate-400"
              >
                刷新
              </button>
            </div>
          </div>
        </div>

        <div className="flex-1 flex items-center justify-center p-8 overflow-auto">
          <div className="relative w-full max-w-6xl">
            <div className="absolute inset-0 opacity-5">
              <div className="w-full h-full" style={{
                backgroundImage: 'radial-gradient(circle, #64748b 1px, transparent 1px)',
                backgroundSize: '30px 30px',
              }} />
            </div>

            <div className="flex flex-col items-center gap-12">
              <div className="relative z-10">
                <AgentCard
                  color={AGENT_CONFIG.CrossKeyAssocAgent.color}
                  label={AGENT_CONFIG.CrossKeyAssocAgent.label}
                  description={AGENT_CONFIG.CrossKeyAssocAgent.description}
                  status={(agentStatuses.CrossKeyAssocAgent as any) || 'idle'}
                  onClick={() => setSelectedAgent(AGENTS.find(a => a.type === 'CrossKeyAssocAgent'))}
                />
              </div>

              <div className="relative z-10">
                <AgentCard
                  color={AGENT_CONFIG.DialogueAgent.color}
                  label={AGENT_CONFIG.DialogueAgent.label}
                  description={AGENT_CONFIG.DialogueAgent.description}
                  status={(agentStatuses.DialogueAgent as any) || 'idle'}
                  onClick={() => setSelectedAgent(AGENTS.find(a => a.type === 'DialogueAgent'))}
                />
              </div>

              <div className="relative z-10">
                <AgentCard
                  color={AGENT_CONFIG.RoutingAgent.color}
                  label={AGENT_CONFIG.RoutingAgent.label}
                  description={AGENT_CONFIG.RoutingAgent.description}
                  status={(agentStatuses.RoutingAgent as any) || 'idle'}
                  onClick={() => setSelectedAgent(AGENTS.find(a => a.type === 'RoutingAgent'))}
                />
              </div>

              {keyAgents.length > 0 && (
                <div className="flex flex-wrap gap-4 justify-center">
                  {keyAgents.map((key) => (
                    <KeyAgentCard
                      key={key.name}
                      keyName={key.name}
                      memoryCount={key.memoryCount}
                      status={key.status}
                      color="#22C55E"
                    />
                  ))}
                </div>
              )}

              <div className="flex flex-wrap gap-4 justify-center">
                <div className="relative z-10">
                  <AgentCard
                    color={AGENT_CONFIG.KeyDecisionAgent.color}
                    label={AGENT_CONFIG.KeyDecisionAgent.label}
                    description={AGENT_CONFIG.KeyDecisionAgent.description}
                    status={(agentStatuses.KeyDecisionAgent as any) || 'idle'}
                    onClick={() => setSelectedAgent(AGENTS.find(a => a.type === 'KeyDecisionAgent'))}
                  />
                </div>
                <div className="relative z-10">
                  <AgentCard
                    color={AGENT_CONFIG.KeyEdgeBuilderAgent.color}
                    label={AGENT_CONFIG.KeyEdgeBuilderAgent.label}
                    description={AGENT_CONFIG.KeyEdgeBuilderAgent.description}
                    status={(agentStatuses.KeyEdgeBuilderAgent as any) || 'idle'}
                    onClick={() => setSelectedAgent(AGENTS.find(a => a.type === 'KeyEdgeBuilderAgent'))}
                  />
                </div>
                <div className="relative z-10">
                  <AgentCard
                    color={AGENT_CONFIG.CompressionAgent.color}
                    label={AGENT_CONFIG.CompressionAgent.label}
                    description={AGENT_CONFIG.CompressionAgent.description}
                    status={(agentStatuses.CompressionAgent as any) || 'idle'}
                    onClick={() => setSelectedAgent(AGENTS.find(a => a.type === 'CompressionAgent'))}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="w-[360px] flex-shrink-0 flex flex-col border-l border-slate-700/50 bg-slate-900/80">
        <div className="px-5 py-4 border-b border-slate-700/50 flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center shadow-lg shadow-purple-500/20">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="16" y1="13" x2="8" y2="13" />
                <line x1="16" y1="17" x2="8" y2="17" />
              </svg>
            </div>
            <div>
              <h3 className="text-sm font-bold text-white">事件流日志</h3>
              <p className="text-xs text-slate-400">最近Agent处理过程</p>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {events.length > 0 ? (
            events.map(event => <EventLogItem key={event.id} event={event} />)
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-center">
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-purple-500/20 to-pink-500/20 flex items-center justify-center mb-4">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-purple-400">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                </svg>
              </div>
              <h3 className="text-base font-bold text-white mb-2">Agent 事件流</h3>
              <p className="text-xs text-slate-500">发送消息后显示处理过程</p>
            </div>
          )}
        </div>
      </div>

      {selectedAgent && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center" onClick={() => setSelectedAgent(null)}>
          <div className="bg-slate-900 border border-slate-700 rounded-2xl p-6 max-w-md w-full mx-4 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-4 mb-5">
              <div
                className="w-14 h-14 rounded-2xl flex items-center justify-center"
                style={{ backgroundColor: `${selectedAgent.color}25` }}
              >
                <div className="w-5 h-5 rounded-full" style={{ backgroundColor: selectedAgent.color, boxShadow: `0 0 15px ${selectedAgent.color}` }} />
              </div>
              <div>
                <h3 className="text-lg font-bold text-white">{selectedAgent.label}</h3>
                <p className="text-sm text-slate-400">{selectedAgent.description}</p>
              </div>
            </div>
            <div className="mb-5">
              <h4 className="text-sm font-medium text-slate-300 mb-3">可用工具</h4>
              {selectedAgent.tools?.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {selectedAgent.tools.map((tool: string) => (
                    <span key={tool} className="px-3 py-1.5 bg-cyan-500/15 text-cyan-400 rounded-xl text-xs font-mono">
                      {tool}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-slate-500">此Agent无工具调用</p>
              )}
            </div>
            <button
              onClick={() => setSelectedAgent(null)}
              className="w-full px-4 py-3 bg-slate-700 hover:bg-slate-600 rounded-xl text-sm font-medium text-white transition-colors"
            >
              关闭
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
