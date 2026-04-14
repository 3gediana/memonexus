import { useState, useEffect, useCallback, useRef } from 'react';

/* ═══════════════════════════════════════════════════════════
   Types
   ═══════════════════════════════════════════════════════════ */

type AgentStatus = 'idle' | 'working' | 'completed';

interface NodeCfg {
  id: string;
  label: string;
  desc: string;
  color: string;
  x: number;
  y: number;
  icon: string;
}

interface EvtLog {
  id: string;
  ts: string;
  agent: string;
  kind: 'thinking' | 'tool' | 'result';
  text: string;
  color: string;
}

/* ═══════════════════════════════════════════════════════════
   Pipeline topology — matches real backend agent event names
   ═══════════════════════════════════════════════════════════ */

const NODES: NodeCfg[] = [
  { id: 'DialogueAgent',    label: '对话 Agent',   desc: '意图分析 · 工具调度 · 生成回复',  color: '#06B6D4', x: 35, y: 14, icon: '💬' },
  { id: 'CompressionAgent', label: '压缩 Agent',   desc: '超阈值时压缩对话历史',              color: '#64748B', x: 10, y: 38, icon: '🗜️' },
  { id: 'RecallAgent',      label: '召回引擎',     desc: 'Key 检索 · 图扩展 · 聚类排序',    color: '#10B981', x: 35, y: 38, icon: '🔍' },
  { id: 'KeyAgent',         label: 'Key Agent',    desc: '记忆审核 · 同 Key 建边',          color: '#22C55E', x: 60, y: 38, icon: '🔑' },
  { id: 'AssociationAgent', label: '关联 Agent',   desc: '跨 Key 建立关联边',              color: '#A855F7', x: 75, y: 62, icon: '🔗' },
  { id: 'HitAnalyzer',      label: '引用分析',     desc: '后台检测回复中的记忆引用',          color: '#F59E0B', x: 10, y: 62, icon: '📊' },
];

const EDGES: [string, string][] = [
  ['DialogueAgent',    'CompressionAgent'],
  ['DialogueAgent',    'RecallAgent'],
  ['DialogueAgent',    'KeyAgent'],
  ['DialogueAgent',    'HitAnalyzer'],
  ['RecallAgent',     'KeyAgent'],
  ['KeyAgent',         'AssociationAgent'],
];

const N: Record<string, NodeCfg> = {};
for (const n of NODES) N[n.id] = n;

// Backend event agent name aliases
const ALIAS: Record<string, string> = {
  StorageAgent: 'KeyAgent',
  KBTool:       'DialogueAgent',
};
const resolve = (name: string) => ALIAS[name] ?? name;

// Edge path builder — uses percentage coords, SVG viewBox 0 0 100 100
function edgePath(from: NodeCfg, to: NodeCfg): string {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const dist = Math.sqrt(dx * dx + dy * dy);
  // Control point offset proportional to vertical distance
  const offsetY = Math.abs(dy) * 0.25;
  const cx = (from.x + to.x) / 2;
  const cy1 = from.y + offsetY * (dy > 0 ? 1 : -1);
  const cy2 = to.y - offsetY * (dy > 0 ? 1 : -1);
  if (dist < 20) {
    // Short edge — simple quadratic
    const cpx = cx + (dy > 0 ? 0 : 0);
    const cpy = (from.y + to.y) / 2 - dx * 0.05;
    return `M ${from.x} ${from.y} Q ${cpx} ${cpy} ${to.x} ${to.y}`;
  }
  return `M ${from.x} ${from.y} C ${cx} ${cy1} ${cx} ${cy2} ${to.x} ${to.y}`;
}

/* ═══════════════════════════════════════════════════════════
   Sub-components
   ═══════════════════════════════════════════════════════════ */

function AgentNode({ node, status, bubble }: {
  node: NodeCfg;
  status: AgentStatus;
  bubble?: string;
}) {
  const working = status === 'working';
  const done    = status === 'completed';

  return (
    <div
      className="absolute z-10 select-none"
      style={{
        left: `${node.x}%`,
        top:  `${node.y}%`,
        transform: 'translate(-50%, -50%)',
      }}
    >
      {bubble && (
        <div
          className="absolute -top-8 left-1/2 -translate-x-1/2 whitespace-nowrap
                     px-2.5 py-0.5 rounded-md text-[9px] font-mono text-white/90 border z-30
                     backdrop-blur-sm"
          style={{
            backgroundColor: `${node.color}30`,
            borderColor: `${node.color}70`,
            boxShadow: `0 0 12px ${node.color}40`,
            animation: 'bubbleIn 0.3s ease-out',
          }}
        >
          {bubble}
        </div>
      )}

      <div
        className="rounded-xl px-4 py-3 border backdrop-blur-sm transition-all duration-500"
        style={{
          width: 170,
          borderColor: working ? node.color : done ? '#22C55E60' : '#334155',
          backgroundColor: working  ? `${node.color}10`
                         : done     ? 'rgba(34,197,94,0.05)'
                         :            'rgba(15,23,42,0.85)',
          boxShadow: working
            ? `0 0 20px ${node.color}30, 0 0 40px ${node.color}10, inset 0 0 20px ${node.color}08`
            : done
            ? '0 0 12px rgba(34,197,94,0.10)'
            : '0 1px 3px rgba(0,0,0,0.3)',
        }}
      >
        <div className="flex items-center gap-2 mb-1.5">
          <div
            className="w-6 h-6 rounded-lg flex items-center justify-center text-xs flex-shrink-0"
            style={{
              backgroundColor: working ? `${node.color}20` : '#1e293b',
              boxShadow: working ? `0 0 8px ${node.color}40` : 'none',
            }}
          >
            {node.icon}
          </div>
          <span className="text-[11px] font-bold text-white/90">{node.label}</span>
          <div
            className="ml-auto w-2 h-2 rounded-full flex-shrink-0 transition-all duration-400"
            style={{
              backgroundColor: working ? node.color : done ? '#22C55E' : '#475569',
              boxShadow: working ? `0 0 6px ${node.color}` : done ? '0 0 6px #22C55E30' : 'none',
            }}
          />
        </div>
        <p className="text-[9px] text-slate-500 leading-tight">{node.desc}</p>
      </div>

      {working && (
        <div
          className="absolute -bottom-2 left-1/2 -translate-x-1/2
                     px-1.5 py-px rounded-full text-[8px] font-bold text-white/90"
          style={{ backgroundColor: `${node.color}CC`, animation: 'badgePop 0.3s ease-out' }}
        >
          running
        </div>
      )}
      {done && (
        <div className="absolute -bottom-2 left-1/2 -translate-x-1/2
                        px-1.5 py-px rounded-full text-[8px] font-bold text-white/70 bg-slate-600/80">
          done
        </div>
      )}
    </div>
  );
}

function FlowEdge({ from, to, active, pathD }: {
  from: NodeCfg;
  to: NodeCfg;
  active: boolean;
  pathD: string;
}) {
  return (
    <g>
      {/* Glow track */}
      {active && (
        <path
          d={pathD}
          fill="none"
          stroke={from.color}
          strokeWidth={4}
          strokeOpacity={0.08}
          vectorEffect="non-scaling-stroke"
        />
      )}
      {/* Base line */}
      <path
        d={pathD}
        fill="none"
        stroke={active ? `${from.color}90` : '#1e293b'}
        strokeWidth={active ? 1.5 : 0.8}
        vectorEffect="non-scaling-stroke"
        style={{ transition: 'stroke 0.4s, stroke-width 0.3s' }}
      />
      {/* Animated flowing dashes */}
      {active && (
        <path
          d={pathD}
          fill="none"
          stroke={from.color}
          strokeWidth={1.5}
          strokeOpacity={0.6}
          strokeDasharray="4 6"
          vectorEffect="non-scaling-stroke"
          style={{ animation: 'dashFlow 0.8s linear infinite' }}
        />
      )}
      {/* Direction arrow */}
      {active && (
        <circle r={2.5} fill={from.color} opacity={0.9}>
          <animateMotion dur="1.5s" repeatCount="indefinite" path={pathD} />
        </circle>
      )}
    </g>
  );
}

function EventItem({ evt }: { evt: EvtLog }) {
  const icon = evt.kind === 'thinking' ? '💭'
             : evt.kind === 'tool'     ? '⚡'
             : '✅';
  return (
    <div
      className="flex gap-2 py-2 border-b border-slate-800/30 last:border-0"
      style={{ animation: 'slideIn 0.25s ease-out' }}
    >
      <div className="text-xs mt-0.5 flex-shrink-0 opacity-60">{icon}</div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 mb-0.5">
          <span
            className="px-1.5 py-px rounded text-[8px] font-bold"
            style={{ backgroundColor: `${evt.color}15`, color: evt.color }}
          >
            {evt.agent}
          </span>
          <span className="text-[9px] text-slate-600 font-mono">{evt.ts}</span>
        </div>
        <p className="text-[10px] text-slate-400 leading-snug break-all"
           style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}
        >
          {evt.text}
        </p>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   Main component
   ═══════════════════════════════════════════════════════════ */

export function AgentFlow() {
  const [statuses, setStatuses] = useState<Record<string, AgentStatus>>(
    Object.fromEntries(NODES.map(n => [n.id, 'idle' as AgentStatus]))
  );
  const [bubbles, setBubbles] = useState<Record<string, string>>({});
  const [events,  setEvents]  = useState<EvtLog[]>([]);
  const [keys,    setKeys]    = useState<{ name: string; count: number }[]>([]);
  const [instanceName, setInstanceName] = useState('');
  const [connected, setConnected]       = useState(false);
  const timers     = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const evtLogRef  = useRef<HTMLDivElement>(null);

  // Pre-compute edge paths
  const edgePaths = EDGES.map(([from, to]) => ({
    key: `${from}-${to}`,
    from: N[from],
    to: N[to],
    d: edgePath(N[from], N[to]),
  }));

  useEffect(() => {
    if (evtLogRef.current) {
      evtLogRef.current.scrollTop = evtLogRef.current.scrollHeight;
    }
  }, [events]);

  const fetchStatus = useCallback(() => {
    fetch('/api/monitor/status')
      .then(r => r.ok ? r.json() : null)
      .then(json => {
        if (!json) return;
        const d = json.data || json;
        setInstanceName(d.instance || '');
        if (d.memory?.by_key) {
          setKeys(Object.entries(d.memory.by_key).map(([name, count]) => ({
            name, count: count as number,
          })));
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  const setWorking = useCallback((agentId: string) => {
    if (timers.current[agentId]) clearTimeout(timers.current[agentId]);
    setStatuses(p => ({ ...p, [agentId]: 'working' }));
  }, []);

  const setCompleted = useCallback((agentId: string) => {
    setStatuses(p => ({ ...p, [agentId]: 'completed' }));
    timers.current[agentId] = setTimeout(() => {
      setStatuses(p => ({ ...p, [agentId]: 'idle' }));
    }, 4000);
  }, []);

  const addEvent = useCallback((agent: string, kind: EvtLog['kind'], text: string) => {
    const node = N[resolve(agent)];
    setEvents(p => [...p.slice(-200), {
      id:    `${Date.now()}_${Math.random()}`,
      ts:    new Date().toLocaleTimeString('zh-CN', { hour12: false }),
      agent,
      kind,
      text,
      color: node?.color || '#64748B',
    }]);
  }, []);

  const showBubble = useCallback((agentId: string, tool: string) => {
    setBubbles(p => ({ ...p, [agentId]: tool }));
    setTimeout(() => {
      setBubbles(p => {
        const next = { ...p };
        if (next[agentId] === tool) delete next[agentId];
        return next;
      });
    }, 3500);
  }, []);

  // ── SSE ──
  useEffect(() => {
    let es: EventSource | null = null;
    let retryTimer: ReturnType<typeof setTimeout>;

    const connect = () => {
      es = new EventSource('/api/monitor/stream');
      es.addEventListener('connected', () => setConnected(true));

      es.addEventListener('agent_thinking', (e) => {
        try {
          const data = JSON.parse(e.data);
          const id = resolve(data.agent);
          setWorking(id);
          addEvent(data.agent, 'thinking', data.phase);
        } catch { /* ignore */ }
      });

      es.addEventListener('agent_tool_call', (e) => {
        try {
          const data = JSON.parse(e.data);
          const id = resolve(data.agent);
          setWorking(id);
          showBubble(id, data.tool);
          const paramStr = data.params ? JSON.stringify(data.params).slice(0, 80) : '';
          addEvent(data.agent, 'tool', `${data.tool}(${paramStr})`);
        } catch { /* ignore */ }
      });

      es.addEventListener('agent_result', (e) => {
        try {
          const data = JSON.parse(e.data);
          const id = resolve(data.agent);
          setCompleted(id);
          const resStr = typeof data.result === 'string'
            ? data.result
            : JSON.stringify(data.result || {});
          addEvent(data.agent, 'result', resStr.slice(0, 100));
          fetchStatus();
        } catch { /* ignore */ }
      });

      es.addEventListener('storage_progress', (e) => {
        try {
          const data = JSON.parse(e.data);
          addEvent('Storage', 'thinking', `${data.stage}`);
        } catch { /* ignore */ }
      });

      es.onerror = () => {
        setConnected(false);
        es?.close();
        retryTimer = setTimeout(connect, 3000);
      };
    };

    connect();

    const handleVisibility = () => {
      if (document.visibilityState === 'visible' && (es?.readyState === EventSource.CLOSED || !es)) {
        es?.close();
        clearTimeout(retryTimer);
        connect();
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);

    return () => {
      clearTimeout(retryTimer);
      es?.close();
      document.removeEventListener('visibilitychange', handleVisibility);
    };
  }, [setWorking, setCompleted, addEvent, showBubble, fetchStatus]);

  // ── Compute active edges ──
  const activeEdges = new Set<string>();
  for (const [from, to] of EDGES) {
    if (statuses[to] === 'working') activeEdges.add(`${from}-${to}`);
  }
  // Also highlight edges from working source
  for (const [from] of EDGES) {
    if (statuses[from] === 'working') {
      const edgesFrom = EDGES.filter(([f]) => f === from);
      for (const [, to] of edgesFrom) {
        activeEdges.add(`${from}-${to}`);
      }
    }
  }

  const workingCount = Object.values(statuses).filter(s => s === 'working').length;

  return (
    <>
      <style>{`
        @keyframes dashFlow {
          to { stroke-dashoffset: -20; }
        }
        @keyframes bubbleIn {
          from { opacity: 0; transform: translate(-50%, 4px) scale(0.85); }
          to   { opacity: 1; transform: translate(-50%, 0) scale(1); }
        }
        @keyframes badgePop {
          from { transform: translate(-50%, 0) scale(0); }
          to   { transform: translate(-50%, 0) scale(1); }
        }
        @keyframes slideIn {
          from { opacity: 0; transform: translateX(-6px); }
          to   { opacity: 1; transform: translateX(0); }
        }
      `}</style>

      <div className="h-full neural-grid flex overflow-hidden">
        <div className="flex-1 flex flex-col min-w-0">
          {/* Header */}
          <div className="px-6 py-3 border-b border-slate-700/50 bg-slate-900/80 flex-shrink-0">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-violet-500 to-fuchsia-500
                                flex items-center justify-center shadow-lg shadow-violet-500/20">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="3" />
                    <path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83" />
                  </svg>
                </div>
                <div>
                  <h1 className="text-sm font-bold text-white">Multi-Agent Pipeline</h1>
                  <div className="flex items-center gap-1.5 text-[10px] text-slate-500 mt-0.5">
                    {instanceName && <><span>{instanceName}</span><span className="text-slate-700">·</span></>}
                    <span>{keys.reduce((s, k) => s + k.count, 0)} memories</span>
                    <span className="text-slate-700">·</span>
                    <span className="flex items-center gap-1">
                      <span className={`w-1.5 h-1.5 rounded-full inline-block ${connected ? 'bg-emerald-400' : 'bg-red-400'}`}
                            style={{ boxShadow: connected ? '0 0 4px #34d399' : '0 0 4px #f87171' }} />
                      {connected ? 'SSE' : 'offline'}
                    </span>
                    {workingCount > 0 && (
                      <>
                        <span className="text-slate-700">·</span>
                        <span className="text-cyan-400 font-medium">{workingCount} active</span>
                      </>
                    )}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-1.5">
                <button onClick={fetchStatus}
                  className="px-2.5 py-1 rounded-md text-[10px] bg-slate-800 hover:bg-slate-700
                             border border-slate-600/50 text-slate-300 transition-colors">
                  refresh
                </button>
                <button onClick={() => { setEvents([]); setBubbles({}); }}
                  className="px-2.5 py-1 rounded-md text-[10px] bg-slate-800 hover:bg-slate-700
                             border border-slate-600/50 text-slate-300 transition-colors">
                  clear
                </button>
              </div>
            </div>
          </div>

          {/* Flow canvas */}
          <div className="flex-1 relative overflow-hidden">
            <div className="absolute inset-0 opacity-[0.025]" style={{
              backgroundImage: 'radial-gradient(circle, #94a3b8 1px, transparent 1px)',
              backgroundSize: '24px 24px',
            }} />

            {/* Pipeline zone labels */}
            <div className="absolute z-20 top-3 left-[18%]
                            px-2.5 py-0.5 rounded-md bg-cyan-950/40 border border-cyan-800/20 text-[9px] text-cyan-400/60 font-medium tracking-wider">
              RECALL
            </div>
            <div className="absolute z-20 top-3 right-[15%]
                            px-2.5 py-0.5 rounded-md bg-green-950/40 border border-green-800/20 text-[9px] text-green-400/60 font-medium tracking-wider">
              STORAGE
            </div>

            {/* SVG edges */}
            <svg
              className="absolute inset-0 w-full h-full"
              viewBox="0 0 100 80"
              preserveAspectRatio="none"
              style={{ pointerEvents: 'none' }}
            >
              {edgePaths.map(({ key, from, to, d }) => (
                <FlowEdge key={key} from={from} to={to} active={activeEdges.has(key)} pathD={d} />
              ))}
            </svg>

            {/* Agent nodes */}
            {NODES.map(node => (
              <AgentNode key={node.id} node={node} status={statuses[node.id]} bubble={bubbles[node.id]} />
            ))}

            {/* Key chips */}
            {keys.length > 0 && (
              <div className="absolute z-10 bottom-3 left-1/2 -translate-x-1/2 flex gap-1.5 flex-wrap justify-center max-w-[90%]">
                {keys.slice(0, 8).map(k => {
                  const isActive = statuses.KeyAgent === 'working';
                  return (
                    <div key={k.name}
                      className="px-2 py-1 rounded-lg border text-[9px] transition-all duration-300"
                      style={{
                        borderColor: isActive ? '#22C55E30' : '#1e293b50',
                        backgroundColor: isActive ? 'rgba(34,197,94,0.05)' : 'rgba(15,23,42,0.8)',
                      }}>
                      <span className="font-medium text-emerald-400/80">{k.name}</span>
                      <span className="text-slate-600 ml-1">{k.count}</span>
                    </div>
                  );
                })}
                {keys.length > 8 && (
                  <div className="px-2 py-1 text-[9px] text-slate-500">+{keys.length - 8}</div>
                )}
              </div>
            )}

            {events.length === 0 && (
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-0">
                <div className="text-center opacity-20 mt-8">
                  <div className="text-4xl mb-3">🧠</div>
                  <p className="text-xs text-slate-500">Send a message to see the pipeline</p>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Event log sidebar */}
        <div className="w-[300px] flex-shrink-0 flex flex-col border-l border-slate-700/50 bg-slate-900/90">
          <div className="px-4 py-3 border-b border-slate-700/50 flex-shrink-0">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-violet-500/80 to-fuchsia-500/80
                              flex items-center justify-center">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
                </svg>
              </div>
              <div>
                <h3 className="text-xs font-bold text-white">Event Log</h3>
                <p className="text-[9px] text-slate-600">{events.length} events</p>
              </div>
            </div>
          </div>

          <div ref={evtLogRef} className="flex-1 overflow-y-auto px-3 py-1">
            {events.length > 0 ? (
              events.map(evt => <EventItem key={evt.id} evt={evt} />)
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-center">
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-violet-500/10 to-fuchsia-500/10
                                flex items-center justify-center mb-2">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                       strokeWidth="1.5" className="text-violet-400/40">
                    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
                  </svg>
                </div>
                <p className="text-[10px] text-slate-600">Waiting for agent events...</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}