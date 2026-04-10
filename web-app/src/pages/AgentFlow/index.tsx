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
  x: number;   // center, percentage of canvas width
  y: number;   // center, percentage of canvas height
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
   Pipeline topology — matches real backend agent names
   ═══════════════════════════════════════════════════════════ */

const NODES: NodeCfg[] = [
  // ── Dialogue pipeline (left) ──
  { id: 'DialogueAgent',    label: '对话 Agent',   desc: '召回记忆 · 生成回复',    color: '#06B6D4', x: 24, y: 17 },
  { id: 'RecallAgent',      label: '召回 Agent',   desc: '搜索相关记忆',           color: '#10B981', x: 12, y: 46 },
  { id: 'CompressionAgent', label: '对话压缩',     desc: '超阈值时压缩上下文',      color: '#64748B', x: 36, y: 46 },
  { id: 'HitAnalyzer',      label: '引用分析',     desc: '检测回复中的记忆引用',    color: '#F59E0B', x: 24, y: 76 },
  // ── Storage pipeline (right) ──
  { id: 'RoutingAgent',     label: '路由 Agent',   desc: '分析消息 · 分配 Key',    color: '#3B82F6', x: 66, y: 17 },
  { id: 'KeyAgent',         label: 'Key Agent',    desc: '记忆审核 · 同Key建边',   color: '#22C55E', x: 56, y: 46 },
  { id: 'AssociationAgent', label: '跨Key 关联',   desc: '建立跨域关联边',          color: '#A855F7', x: 72, y: 76 },
];

const EDGES: [string, string][] = [
  ['DialogueAgent', 'RecallAgent'],
  ['DialogueAgent', 'CompressionAgent'],
  ['DialogueAgent', 'HitAnalyzer'],
  ['RoutingAgent',  'KeyAgent'],
  ['KeyAgent',      'AssociationAgent'],
  ['RecallAgent',   'KeyAgent'],
];

// Quick lookup
const N: Record<string, NodeCfg> = {};
for (const n of NODES) N[n.id] = n;

// Backend sometimes uses different agent names
const ALIAS: Record<string, string> = {
  StorageAgent: 'KeyAgent',
  KBTool:       'DialogueAgent',
};
const resolve = (name: string) => ALIAS[name] ?? name;

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
      {/* ── Tool-call bubble ── */}
      {bubble && (
        <div
          className="absolute -top-9 left-1/2 -translate-x-1/2 whitespace-nowrap
                     px-3 py-1 rounded-full text-[10px] font-mono text-white border z-30"
          style={{
            backgroundColor: `${node.color}25`,
            borderColor: `${node.color}60`,
            animation: 'bubbleIn 0.4s ease-out',
          }}
        >
          <span className="mr-1">⚡</span>{bubble}
        </div>
      )}

      {/* ── Card ── */}
      <div
        className="rounded-2xl px-5 py-3.5 border-2 backdrop-blur-sm"
        style={{
          width: 164,
          borderColor: working ? node.color : done ? '#22C55E' : '#1e293b',
          backgroundColor: working  ? `${node.color}12`
                         : done     ? 'rgba(34,197,94,0.06)'
                         :            'rgba(15,23,42,0.92)',
          boxShadow: working
            ? `0 0 24px ${node.color}40, 0 0 48px ${node.color}18`
            : done
            ? '0 0 16px rgba(34,197,94,0.15)'
            : '0 2px 8px rgba(0,0,0,0.3)',
          transition: 'border-color 0.5s, background-color 0.5s, box-shadow 0.5s',
          animation: working ? 'cardPulse 2s ease-in-out infinite' : 'none',
        }}
      >
        <div className="flex items-center gap-2 mb-1">
          {/* Status dot */}
          <div
            className="w-2.5 h-2.5 rounded-full flex-shrink-0"
            style={{
              backgroundColor: working ? node.color : done ? '#22C55E' : '#475569',
              boxShadow: working ? `0 0 10px ${node.color}` : done ? '0 0 8px #22C55E' : 'none',
              transition: 'all 0.4s',
            }}
          />
          <span className="text-xs font-bold text-white truncate">{node.label}</span>
        </div>
        <p className="text-[10px] text-slate-400 leading-tight">{node.desc}</p>
      </div>

      {/* ── Status badge ── */}
      {working && (
        <div
          className="absolute -bottom-2.5 left-1/2 -translate-x-1/2
                     px-2 py-0.5 rounded-full text-[9px] font-bold text-white"
          style={{ backgroundColor: node.color, animation: 'badgePop 0.3s ease-out' }}
        >
          执行中
        </div>
      )}
      {done && (
        <div className="absolute -bottom-2.5 left-1/2 -translate-x-1/2
                        px-2 py-0.5 rounded-full text-[9px] font-bold text-white bg-slate-600">
          完成
        </div>
      )}
    </div>
  );
}

function FlowEdge({ from, to, active }: {
  from: NodeCfg;
  to: NodeCfg;
  active: boolean;
}) {
  // Curved path via midpoint offset
  const mx = (from.x + to.x) / 2;
  const my = (from.y + to.y) / 2;
  // Slight curve offset for aesthetics
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const cx = mx - dy * 0.08;
  const cy = my + dx * 0.08;

  const d = `M ${from.x} ${from.y} Q ${cx} ${cy} ${to.x} ${to.y}`;

  return (
    <g>
      {/* Shadow / glow layer */}
      {active && (
        <path
          d={d}
          fill="none"
          stroke="#22D3EE"
          strokeWidth={6}
          strokeOpacity={0.15}
          vectorEffect="non-scaling-stroke"
        />
      )}
      {/* Main line */}
      <path
        d={d}
        fill="none"
        stroke={active ? '#22D3EE' : '#1e293b'}
        strokeWidth={active ? 2 : 1.2}
        vectorEffect="non-scaling-stroke"
        strokeDasharray={active ? '8 5' : undefined}
        style={{
          transition: 'stroke 0.4s, stroke-width 0.3s',
          animation: active ? 'dashFlow 0.6s linear infinite' : 'none',
        }}
      />
      {/* Animated particle dot on active edges */}
      {active && (
        <circle r={3} fill="#22D3EE" opacity={0.9}>
          <animateMotion dur="1.2s" repeatCount="indefinite" path={d} />
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
      className="flex gap-2.5 py-2.5 border-b border-slate-800/40 last:border-0"
      style={{ animation: 'slideIn 0.3s ease-out' }}
    >
      <div className="text-sm mt-0.5 flex-shrink-0">{icon}</div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <span
            className="px-1.5 py-0.5 rounded text-[9px] font-bold"
            style={{ backgroundColor: `${evt.color}18`, color: evt.color }}
          >
            {evt.agent}
          </span>
          <span className="text-[10px] text-slate-600 font-mono">{evt.ts}</span>
        </div>
        <p className="text-[11px] text-slate-300 leading-snug break-all"
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

  // ── Auto-scroll event log ──
  useEffect(() => {
    if (evtLogRef.current) {
      evtLogRef.current.scrollTop = evtLogRef.current.scrollHeight;
    }
  }, [events]);

  // ── Fetch initial key data ──
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

  // ── Helpers ──
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

  // ── SSE: /api/monitor/stream ──
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
          // refresh key counts
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
        // Auto-reconnect after 3s
        retryTimer = setTimeout(connect, 3000);
      };
    };

    connect();
    return () => {
      clearTimeout(retryTimer);
      es?.close();
    };
  }, [setWorking, setCompleted, addEvent, showBubble, fetchStatus]);

  // ── Compute which edges are active ──
  const activeEdges = new Set<string>();
  for (const [from, to] of EDGES) {
    if (statuses[to] === 'working') activeEdges.add(`${from}-${to}`);
  }

  // ── Count active agents ──
  const workingCount = Object.values(statuses).filter(s => s === 'working').length;

  return (
    <>
      {/* Keyframe animations */}
      <style>{`
        @keyframes cardPulse {
          0%, 100% { transform: translate(-50%, -50%) scale(1); }
          50%      { transform: translate(-50%, -50%) scale(1.015); }
        }
        @keyframes dashFlow {
          to { stroke-dashoffset: -26; }
        }
        @keyframes bubbleIn {
          from { opacity: 0; transform: translate(-50%, 4px) scale(0.9); }
          to   { opacity: 1; transform: translate(-50%, 0) scale(1); }
        }
        @keyframes badgePop {
          from { transform: translate(-50%, 0) scale(0); }
          to   { transform: translate(-50%, 0) scale(1); }
        }
        @keyframes slideIn {
          from { opacity: 0; transform: translateX(-8px); }
          to   { opacity: 1; transform: translateX(0); }
        }
      `}</style>

      <div className="h-full neural-grid flex overflow-hidden">
        {/* ════════════════════════════════════
            Main canvas
            ════════════════════════════════════ */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* ── Header bar ── */}
          <div className="px-8 py-4 border-b border-slate-700/50 bg-slate-900/80 flex-shrink-0">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="w-11 h-11 rounded-2xl bg-gradient-to-br from-pink-500 via-rose-500 to-purple-500
                                flex items-center justify-center shadow-lg shadow-pink-500/30">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="3" />
                    <path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83" />
                  </svg>
                </div>
                <div>
                  <h1 className="text-lg font-bold text-white">Multi-Agent 协作流水线</h1>
                  <div className="flex items-center gap-2 text-xs text-slate-400 mt-0.5">
                    {instanceName && <><span>{instanceName}</span><span className="text-slate-600">·</span></>}
                    <span>{keys.reduce((s, k) => s + k.count, 0)} 条记忆</span>
                    <span className="text-slate-600">·</span>
                    <span className="flex items-center gap-1">
                      <span className={`w-1.5 h-1.5 rounded-full inline-block ${connected ? 'bg-emerald-400' : 'bg-red-400'}`}
                            style={{ boxShadow: connected ? '0 0 6px #34d399' : '0 0 6px #f87171' }} />
                      {connected ? 'SSE 已连接' : '未连接'}
                    </span>
                    {workingCount > 0 && (
                      <>
                        <span className="text-slate-600">·</span>
                        <span className="text-cyan-400 font-medium">{workingCount} 个 Agent 活跃</span>
                      </>
                    )}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={fetchStatus}
                  className="px-3 py-1.5 rounded-lg text-xs bg-slate-800 hover:bg-slate-700
                             border border-slate-600 text-slate-300 transition-colors"
                >
                  刷新
                </button>
                <button
                  onClick={() => { setEvents([]); setBubbles({}); }}
                  className="px-3 py-1.5 rounded-lg text-xs bg-slate-800 hover:bg-slate-700
                             border border-slate-600 text-slate-300 transition-colors"
                >
                  清空
                </button>
              </div>
            </div>
          </div>

          {/* ── Flow diagram area ── */}
          <div className="flex-1 relative overflow-hidden">
            {/* Dot grid background */}
            <div className="absolute inset-0 opacity-[0.03]" style={{
              backgroundImage: 'radial-gradient(circle, #94a3b8 1px, transparent 1px)',
              backgroundSize: '32px 32px',
            }} />

            {/* Pipeline labels */}
            <div className="absolute z-20 top-5 left-[6%]
                            px-3 py-1 rounded-full bg-cyan-950/60 border border-cyan-800/30 text-[10px] text-cyan-400/80 font-bold tracking-wide">
              🗣️  对话·召回
            </div>
            <div className="absolute z-20 top-5 right-[12%]
                            px-3 py-1 rounded-full bg-blue-950/60 border border-blue-800/30 text-[10px] text-blue-400/80 font-bold tracking-wide">
              💾  存储·关联
            </div>

            {/* Center divider */}
            <div className="absolute left-[45%] top-[8%] bottom-[8%] w-px
                            bg-gradient-to-b from-transparent via-slate-700/30 to-transparent" />

            {/* SVG edge layer */}
            <svg
              className="absolute inset-0 w-full h-full"
              viewBox="0 0 100 100"
              preserveAspectRatio="none"
              style={{ pointerEvents: 'none' }}
            >
              {EDGES.map(([from, to]) => (
                <FlowEdge
                  key={`${from}-${to}`}
                  from={N[from]}
                  to={N[to]}
                  active={activeEdges.has(`${from}-${to}`)}
                />
              ))}
            </svg>

            {/* Agent node cards */}
            {NODES.map(node => (
              <AgentNode
                key={node.id}
                node={node}
                status={statuses[node.id]}
                bubble={bubbles[node.id]}
              />
            ))}

            {/* Key summary cards at bottom */}
            {keys.length > 0 && (
              <div className="absolute z-10 bottom-4 left-1/2 -translate-x-1/2 flex gap-2 flex-wrap justify-center max-w-[90%]">
                {keys.map(k => {
                  const isActive = statuses.KeyAgent === 'working';
                  return (
                    <div
                      key={k.name}
                      className="px-3 py-1.5 rounded-xl border transition-all duration-300"
                      style={{
                        borderColor: isActive ? '#22C55E40' : '#1e293b',
                        backgroundColor: isActive ? 'rgba(34,197,94,0.06)' : 'rgba(15,23,42,0.9)',
                        boxShadow: isActive ? '0 0 12px rgba(34,197,94,0.15)' : 'none',
                      }}
                    >
                      <div className="text-[10px] font-bold text-emerald-400 capitalize">{k.name}</div>
                      <div className="text-[9px] text-slate-500">{k.count} 条</div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Empty state hint */}
            {events.length === 0 && (
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-0">
                <div className="text-center opacity-30 mt-12">
                  <div className="text-5xl mb-4">🧠</div>
                  <p className="text-sm text-slate-400 leading-relaxed">
                    在对话页发送消息<br/>此处将实时展示 Agent 协作流程
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ════════════════════════════════════
            Event log sidebar
            ════════════════════════════════════ */}
        <div className="w-[340px] flex-shrink-0 flex flex-col border-l border-slate-700/50 bg-slate-900/80">
          {/* Sidebar header */}
          <div className="px-5 py-4 border-b border-slate-700/50 flex-shrink-0">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-violet-500 to-fuchsia-500
                              flex items-center justify-center shadow-lg shadow-violet-500/20">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
                </svg>
              </div>
              <div>
                <h3 className="text-sm font-bold text-white">实时事件流</h3>
                <p className="text-[11px] text-slate-500">{events.length} 个事件</p>
              </div>
            </div>
          </div>

          {/* Event list */}
          <div ref={evtLogRef} className="flex-1 overflow-y-auto px-4 py-2">
            {events.length > 0 ? (
              events.map(evt => <EventItem key={evt.id} evt={evt} />)
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-center">
                <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-violet-500/15 to-fuchsia-500/15
                                flex items-center justify-center mb-3">
                  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                       strokeWidth="1.5" className="text-violet-400/60">
                    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
                  </svg>
                </div>
                <h4 className="text-sm font-bold text-white/60 mb-1">等待事件</h4>
                <p className="text-[11px] text-slate-500 leading-relaxed">
                  Agent 开始工作后<br/>事件将实时显示在这里
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
