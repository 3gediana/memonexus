import { useState, useRef, useEffect, useCallback } from 'react';
import DOMPurify from 'dompurify';
import { useStreamConnection, type StorageResult } from '../../hooks/useStreamConnection';

/* ─────────────── Types ─────────────── */
interface Message {
  id: string;
  turn: number;
  role: 'user' | 'assistant';
  content: string;
  reasoning?: string;
  recallBlocks?: RecallBlock[];
  timestamp: string;
}

interface RecallBlock {
  fingerprint: string;
  key: string;
  tag: string;
  memory: string;
  created_at: string;
  recall_count: number;
}

interface MemoryTimelineItem {
  id: string;
  type: 'recall' | 'store' | 'update' | 'duplicate';
  key: string;
  tag: string;
  memory: string;
  fingerprint: string;
  timestamp: string;
  recallCount?: number;
}

/* ─────────────── Constants ─────────────── */
const KEY_META: Record<string, { label: string; color: string; icon: string }> = {
  study:        { label: '学业',   color: '#3B82F6', icon: '📚' },
  health:       { label: '健康',   color: '#10B981', icon: '🏃' },
  preference:   { label: '偏好',   color: '#F59E0B', icon: '⭐' },
  work:         { label: '工作',   color: '#EF4444', icon: '💼' },
  project:      { label: '项目',   color: '#8B5CF6', icon: '🔧' },
  code:         { label: '代码',   color: '#06B6D4', icon: '💻' },
  schedule:     { label: '日程',   color: '#EC4899', icon: '📅' },
  relationship: { label: '关系',   color: '#F97316', icon: '👥' },
  emotion:      { label: '情绪',   color: '#A855F7', icon: '💭' },
};

const getKeyMeta = (key: string) => KEY_META[key] || { label: key, color: '#6B7280', icon: '📝' };

const QUICK_PROMPTS = [
  '我决定考研了，目标清华计算机',
  '今天高数复习到第三章，感觉好难',
  '最近压力有点大，晚上总失眠',
  '帮我回顾一下最近的学习进度',
  '下周三有个模拟考试，我该怎么准备',
];

/* ─────────────── Component ─────────────── */
export function ScenarioDemo() {
  const [messages, setMessages] = useState<Message[]>(() => {
    const saved = localStorage.getItem('memonexus_scenario_messages');
    return saved ? JSON.parse(saved) : [];
  });
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [memoryTimeline, setMemoryTimeline] = useState<MemoryTimelineItem[]>(() => {
    const saved = localStorage.getItem('memonexus_scenario_timeline');
    return saved ? JSON.parse(saved) : [];
  });
  const [currentInstanceId, setCurrentInstanceId] = useState('');
  const [activeRecallIds, setActiveRecallIds] = useState<Set<string>>(new Set());
  const [storageResult, setStorageResult] = useState<StorageResult | null>(null);
  const reasoningRef = useRef('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const timelineEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Persist to localStorage
  useEffect(() => {
    localStorage.setItem('memonexus_scenario_messages', JSON.stringify(messages));
  }, [messages]);

  useEffect(() => {
    localStorage.setItem('memonexus_scenario_timeline', JSON.stringify(memoryTimeline));
  }, [memoryTimeline]);

  // Fetch current instance
  useEffect(() => {
    fetch('/api/instances/current')
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        const name = data?.data?.name || data?.data?.id;
        setCurrentInstanceId(name || 'study_assistant');
      })
      .catch(() => setCurrentInstanceId('study_assistant'));
  }, []);

  const { connect, disconnect } = useStreamConnection({
    onReasoning: (delta) => {
      setIsThinking(true);
      reasoningRef.current = delta;
    },
    onContent: (delta) => {
      setIsThinking(false);
      setMessages(prev => {
        const last = prev[prev.length - 1];
        if (last?.role === 'assistant') {
          return [...prev.slice(0, -1), { ...last, content: last.content + delta }];
        }
        return [...prev, {
          id: Date.now().toString(),
          turn: prev.length + 1,
          role: 'assistant',
          content: delta,
          timestamp: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
        }];
      });
    },
    onDone: (content, hasRecalled, recallBlocks) => {
      setIsStreaming(false);
      setIsThinking(false);
      const finalReasoning = reasoningRef.current || undefined;

      if (hasRecalled && recallBlocks && recallBlocks.length > 0) {
        setMessages(prev => {
          const last = prev[prev.length - 1];
          if (last?.role === 'assistant') {
            return [...prev.slice(0, -1), { ...last, reasoning: finalReasoning, recallBlocks }];
          }
          return prev;
        });
        // Add recalled memories to timeline
        const newItems: MemoryTimelineItem[] = recallBlocks.map(block => ({
          id: `recall_${block.fingerprint}_${Date.now()}`,
          type: 'recall' as const,
          key: block.key,
          tag: block.tag,
          memory: block.memory,
          fingerprint: block.fingerprint,
          timestamp: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
          recallCount: block.recall_count,
        }));
        setMemoryTimeline(prev => [...prev, ...newItems]);
        setActiveRecallIds(new Set(recallBlocks.map(b => b.fingerprint)));
        setTimeout(() => setActiveRecallIds(new Set()), 3000);
      } else if (finalReasoning) {
        setMessages(prev => {
          const last = prev[prev.length - 1];
          if (last?.role === 'assistant') {
            return [...prev.slice(0, -1), { ...last, reasoning: finalReasoning }];
          }
          return prev;
        });
      } else if (content) {
        setMessages(prev => {
          const last = prev[prev.length - 1];
          if (last?.role === 'assistant' && !last.content) {
            return [...prev.slice(0, -1), { ...last, content }];
          }
          return prev;
        });
      }
    },
    onError: (message) => {
      setIsStreaming(false);
      setIsThinking(false);
      setMessages(prev => [...prev, {
        id: `error_${Date.now()}`,
        turn: prev.length > 0 ? prev[prev.length - 1].turn : 1,
        role: 'assistant',
        content: `⚠️ ${message}`,
        timestamp: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
      }]);
    },
    onStorageResult: (result) => {
      setStorageResult(result);
      if (result.memories_added && result.memories_added.length > 0) {
        const newItems: MemoryTimelineItem[] = result.memories_added.map((m: any) => ({
          id: `store_${m.memory_id || Date.now()}_${Math.random()}`,
          type: 'store' as const,
          key: m.key,
          tag: m.content_preview || '',
          memory: m.content_preview || '',
          fingerprint: m.memory_id || '',
          timestamp: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
        }));
        setMemoryTimeline(prev => [...prev, ...newItems]);
      }
    },
    onToolCall: (toolName, params, toolCallId) => {
      setIsThinking(false);
      setMemoryTimeline(prev => [...prev, {
        id: toolCallId,
        type: 'recall',
        key: toolName,
        tag: '调用工具',
        memory: typeof params === 'string' ? params : JSON.stringify(params),
        timestamp: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
        fingerprint: toolCallId
      }]);
    },
    onToolReturn: (toolName, toolCallId, result) => {
      // Find and update the tool call event
      setMemoryTimeline(prev => prev.map(item => 
        item.id === toolCallId ? { ...item, tag: '已返回结果', memory: result } : item
      ));
    },
    onAgentThinking: (agent, phase) => {
      setIsThinking(true);
      setMemoryTimeline(prev => [...prev, {
        id: `thinking_${Date.now()}`,
        type: 'recall',
        key: agent,
        tag: '正在思考',
        memory: phase,
        timestamp: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
        fingerprint: ''
      }]);
    },
    onAgentToolCall: (agent, tool, params) => {
      setIsThinking(false);
      setMemoryTimeline(prev => [...prev, {
        id: `agent_tool_${Date.now()}`,
        type: 'recall',
        key: agent,
        tag: `使用 ${tool}`,
        memory: JSON.stringify(params),
        timestamp: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
        fingerprint: ''
      }]);
    },
    onAgentResult: (agent, result) => {
      setMemoryTimeline(prev => [...prev, {
        id: `agent_res_${Date.now()}`,
        type: 'recall',
        key: agent,
        tag: '已得出结论',
        memory: JSON.stringify(result),
        timestamp: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
        fingerprint: ''
      }]);
    },
    onStorageProgress: (stage, progress) => {
      setMemoryTimeline(prev => [...prev, {
        id: `progress_${Date.now()}`,
        type: 'store',
        key: '存储引擎',
        tag: stage,
        memory: JSON.stringify(progress),
        timestamp: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
        fingerprint: ''
      }]);
    },
    onHeartbeat: () => {},
  });

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => { scrollToBottom(); }, [messages, scrollToBottom]);
  useEffect(() => {
    timelineEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [memoryTimeline]);

  const handleNewConversation = async () => {
    disconnect();
    setMessages([]);
    setMemoryTimeline([]);
    localStorage.removeItem('memonexus_scenario_messages');
    localStorage.removeItem('memonexus_scenario_timeline');
    setStorageResult(null);
    reasoningRef.current = '';
    setIsStreaming(true);

    try {
      const res = await fetch('/api/dialogue/clear', { method: 'POST' });
      if (!res.ok || !res.body) {
        setIsStreaming(false);
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        let eventType = '';
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (eventType === 'storage_result') {
                setStorageResult({
                  type: 'storage_result',
                  memories_added: data.memories_added || [],
                  total_memories: data.total_memories || 0,
                  duration_ms: data.duration_ms || 0,
                });
              } else if (eventType === 'agent_thinking') {
                setMemoryTimeline(prev => [...prev, {
                  id: `clear_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
                  type: 'store',
                  key: data.agent,
                  tag: data.phase,
                  memory: '',
                  timestamp: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
                  fingerprint: ''
                }]);
              } else if (eventType === 'agent_result') {
                setMemoryTimeline(prev => {
                  const updated = [...prev];
                  const lastIdx = updated.findIndex(e => e.key === data.agent && e.type === 'store');
                  if (lastIdx >= 0) {
                    updated[lastIdx] = { ...updated[lastIdx], memory: JSON.stringify(data.result).slice(0, 200) };
                  }
                  return updated;
                });
              } else if (eventType === 'done') {
                // storage complete
              }
            } catch { /* skip non-JSON lines */ }
          }
        }
      }
    } catch { /* ignore */ } finally {
      setIsStreaming(false);
    }
  };

  const handleSend = (text?: string) => {
    const msg = (text || input).trim();
    if (!msg || isStreaming || !currentInstanceId) return;
    const userMessage: Message = {
      id: Date.now().toString(),
      turn: Math.ceil(messages.length / 2) + 1,
      role: 'user',
      content: msg,
      timestamp: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
    };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsStreaming(true);
    setStorageResult(null);
    reasoningRef.current = '';
    
    // Convert current messages to history format
    const history = messages.map(m => ({
      role: m.role,
      content: m.content
    }));
    
    connect(currentInstanceId, userMessage.content, userMessage.turn, 'study_mentor', history);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  /* ─────────────── Render ─────────────── */
  return (
    <div className="h-full flex overflow-hidden" style={{ background: 'linear-gradient(135deg, #0a0e17 0%, #0d1525 50%, #0a0e17 100%)' }}>
      {/* ========== LEFT: Chat Area ========== */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header className="h-16 border-b border-white/5 flex items-center px-6 flex-shrink-0"
          style={{ background: 'linear-gradient(90deg, rgba(99,102,241,0.08) 0%, rgba(6,182,212,0.05) 100%)' }}>
          <div className="flex items-center gap-3 flex-1">
            <div className="w-11 h-11 rounded-2xl flex items-center justify-center text-xl"
              style={{ background: 'linear-gradient(135deg, #6366f1, #06b6d4)', boxShadow: '0 0 24px rgba(99,102,241,0.3)' }}>
              🧠
            </div>
            <div>
              <h1 className="text-lg font-bold text-white" style={{ fontFamily: "'Noto Sans SC', sans-serif" }}>
                Memonexus · 考研陪伴导师
              </h1>
              <p className="text-xs text-slate-400">
                {isThinking ? (
                  <span className="text-amber-400 animate-pulse">正在思考并检索记忆...</span>
                ) : isStreaming ? (
                  <span className="text-cyan-400">正在回复...</span>
                ) : (
                  <span>我记住关于你的一切，陪你走完这段考研路</span>
                )}
              </p>
            </div>
          </div>
          <button onClick={handleNewConversation}
            className="px-4 py-2 rounded-xl text-xs font-medium transition-all duration-200 border"
            style={{ borderColor: 'rgba(99,102,241,0.3)', color: '#818cf8', background: 'rgba(99,102,241,0.08)' }}
            onMouseEnter={e => { (e.target as HTMLElement).style.background = 'rgba(99,102,241,0.2)'; }}
            onMouseLeave={e => { (e.target as HTMLElement).style.background = 'rgba(99,102,241,0.08)'; }}
          >
            新对话
          </button>
        </header>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto chat-scroll px-6 py-4">
          {messages.length === 0 && !isStreaming && (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <div className="w-24 h-24 rounded-3xl flex items-center justify-center text-5xl mb-6"
                style={{ background: 'linear-gradient(135deg, rgba(99,102,241,0.15), rgba(6,182,212,0.1))', boxShadow: '0 0 60px rgba(99,102,241,0.1)' }}>
                🎓
              </div>
              <h2 className="text-xl font-bold text-white mb-2" style={{ fontFamily: "'Noto Sans SC', sans-serif" }}>
                你好，我是你的考研陪伴导师
              </h2>
              <p className="text-sm text-slate-400 mb-8 max-w-md leading-relaxed">
                我会记住你的每一个学习计划、情绪波动和生活习惯。<br />
                不论隔了多久，我都能精确回忆起关于你的一切。
              </p>
              <div className="flex flex-wrap gap-2 justify-center max-w-lg">
                {QUICK_PROMPTS.map((prompt, i) => (
                  <button key={i} onClick={() => handleSend(prompt)}
                    className="px-4 py-2.5 rounded-xl text-sm transition-all duration-200 border"
                    style={{
                      fontFamily: "'Noto Sans SC', sans-serif",
                      borderColor: 'rgba(99,102,241,0.2)',
                      color: '#c7d2fe',
                      background: 'rgba(99,102,241,0.06)',
                    }}
                    onMouseEnter={e => {
                      (e.target as HTMLElement).style.background = 'rgba(99,102,241,0.15)';
                      (e.target as HTMLElement).style.borderColor = 'rgba(99,102,241,0.4)';
                      (e.target as HTMLElement).style.transform = 'translateY(-1px)';
                    }}
                    onMouseLeave={e => {
                      (e.target as HTMLElement).style.background = 'rgba(99,102,241,0.06)';
                      (e.target as HTMLElement).style.borderColor = 'rgba(99,102,241,0.2)';
                      (e.target as HTMLElement).style.transform = 'translateY(0)';
                    }}
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg) => (
            <div key={msg.id} className="mb-5 animate-fadeIn">
              {msg.role === 'user' ? (
                /* ── User Bubble ── */
                <div className="flex justify-end gap-3">
                  <div className="max-w-[70%]">
                    <div className="px-5 py-3 rounded-2xl rounded-br-md text-sm text-white leading-relaxed"
                      style={{
                        background: 'linear-gradient(135deg, #6366f1, #4f46e5)',
                        fontFamily: "'Noto Sans SC', sans-serif",
                        boxShadow: '0 4px 16px rgba(99,102,241,0.25)',
                      }}>
                      {msg.content}
                    </div>
                    <div className="text-right mt-1">
                      <span className="text-[10px] text-slate-500">{msg.timestamp}</span>
                    </div>
                  </div>
                  <div className="w-9 h-9 rounded-xl flex items-center justify-center text-sm flex-shrink-0"
                    style={{ background: 'linear-gradient(135deg, #4f46e5, #6366f1)' }}>
                    👤
                  </div>
                </div>
              ) : (
                /* ── Assistant Bubble ── */
                <div className="flex justify-start gap-3">
                  <div className="w-9 h-9 rounded-xl flex items-center justify-center text-sm flex-shrink-0"
                    style={{ background: 'linear-gradient(135deg, #06b6d4, #0891b2)' }}>
                    🧠
                  </div>
                  <div className="max-w-[70%]">
                    {/* Memory Insight Banner */}
                    {msg.recallBlocks && msg.recallBlocks.length > 0 && (
                      <div className="mb-2 px-3 py-2 rounded-xl text-xs flex items-center gap-2"
                        style={{ background: 'rgba(6,182,212,0.08)', border: '1px solid rgba(6,182,212,0.15)' }}>
                        <span className="text-base">💡</span>
                        <span className="text-cyan-300" style={{ fontFamily: "'Noto Sans SC', sans-serif" }}>
                          基于你的 <strong>{msg.recallBlocks.length}</strong> 条专属记忆生成回答
                        </span>
                        <div className="flex gap-1 ml-auto">
                          {msg.recallBlocks.map(b => {
                            const meta = getKeyMeta(b.key);
                            return (
                              <span key={b.fingerprint} className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                                style={{ backgroundColor: `${meta.color}20`, color: meta.color }}>
                                {meta.icon} {meta.label}
                              </span>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    {/* Reasoning Toggle */}
                    {msg.reasoning && (
                      <ReasoningToggle reasoning={msg.reasoning} />
                    )}

                    <div className="px-5 py-3 rounded-2xl rounded-bl-md text-sm leading-relaxed"
                      style={{
                        background: 'rgba(30,41,59,0.8)',
                        border: '1px solid rgba(100,116,139,0.15)',
                        color: '#e2e8f0',
                        fontFamily: "'Noto Sans SC', sans-serif",
                      }}>
                      <p className="whitespace-pre-wrap">{DOMPurify.sanitize(msg.content, { ALLOWED_TAGS: [] })}</p>
                    </div>

                    <div className="mt-1">
                      <span className="text-[10px] text-slate-500">{msg.timestamp}</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}

          {/* Typing Indicator */}
          {isStreaming && messages.length > 0 && messages[messages.length - 1]?.role === 'user' && (
            <div className="flex justify-start gap-3 mb-5 animate-fadeIn">
              <div className="w-9 h-9 rounded-xl flex items-center justify-center text-sm flex-shrink-0"
                style={{ background: 'linear-gradient(135deg, #06b6d4, #0891b2)' }}>
                🧠
              </div>
              <div className="px-5 py-3 rounded-2xl rounded-bl-md"
                style={{ background: 'rgba(30,41,59,0.8)', border: '1px solid rgba(100,116,139,0.15)' }}>
                <div className="flex gap-1.5 items-center">
                  {isThinking ? (
                    <>
                      <div className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                      <span className="text-xs text-amber-400">检索记忆中...</span>
                    </>
                  ) : (
                    <>
                      <span className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                      <span className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                      <span className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                    </>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Storage Result */}
          {storageResult && storageResult.memories_added && storageResult.memories_added.length > 0 && (
            <div className="mb-5 ml-12 animate-fadeIn">
              <div className="px-4 py-3 rounded-xl text-xs"
                style={{ background: 'rgba(34,197,94,0.06)', border: '1px solid rgba(34,197,94,0.15)' }}>
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="text-base">💾</span>
                  <span className="text-emerald-400 font-medium" style={{ fontFamily: "'Noto Sans SC', sans-serif" }}>
                    已将 {storageResult.memories_added.length} 条新记忆存入大脑
                  </span>
                  <span className="text-slate-500 ml-auto">{storageResult.duration_ms}ms</span>
                </div>
                {storageResult.memories_added.map((m: any, i: number) => {
                  const meta = getKeyMeta(m.key);
                  return (
                    <div key={i} className="flex items-center gap-2 mt-1">
                      <span className="px-1.5 py-0.5 rounded text-[10px]"
                        style={{ backgroundColor: `${meta.color}20`, color: meta.color }}>
                        {meta.label}
                      </span>
                      <span className="text-slate-300 truncate">{m.content_preview}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <footer className="border-t border-white/5 px-6 py-3 flex-shrink-0"
          style={{ background: 'rgba(15,23,42,0.6)', backdropFilter: 'blur(12px)' }}>
          <div className="relative">
            <textarea
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="和导师说说你的学习近况..."
              rows={1}
              style={{ fontFamily: "'Noto Sans SC', sans-serif" }}
              className="w-full bg-slate-800/50 border border-slate-700/50 rounded-xl px-5 py-3.5 pr-24 text-white placeholder-slate-500 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500/40 text-sm"
            />
            <div className="absolute right-2.5 bottom-2 flex gap-2">
              <button onClick={() => handleSend()} disabled={!input.trim() || isStreaming || !currentInstanceId}
                className="w-9 h-9 rounded-xl flex items-center justify-center transition-all disabled:opacity-30 disabled:cursor-not-allowed"
                style={{ background: 'linear-gradient(135deg, #6366f1, #4f46e5)' }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2">
                  <line x1="22" y1="2" x2="11" y2="13" />
                  <polygon points="22 2 15 22 11 13 2 9 22 2" />
                </svg>
              </button>
            </div>
          </div>
          <p className="text-[10px] text-slate-500 mt-2 text-center">Enter 发送 · Shift+Enter 换行 · 所有对话都会被记忆引擎自动分析</p>
        </footer>
      </div>

      {/* ========== RIGHT: Memory Timeline Sidebar ========== */}
      <div className="w-[340px] flex-shrink-0 flex flex-col border-l border-white/5"
        style={{ background: 'linear-gradient(180deg, rgba(15,23,42,0.95) 0%, rgba(10,14,23,0.98) 100%)' }}>
        {/* Sidebar Header */}
        <div className="h-16 px-5 flex items-center gap-3 border-b border-white/5 flex-shrink-0">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center text-lg"
            style={{ background: 'linear-gradient(135deg, rgba(168,85,247,0.2), rgba(236,72,153,0.15))' }}>
            🧬
          </div>
          <div>
            <h3 className="text-sm font-bold text-white" style={{ fontFamily: "'Noto Sans SC', sans-serif" }}>
              记忆活动流
            </h3>
            <p className="text-[10px] text-slate-500">
              实时展示 AI 的记忆召回与存储
            </p>
          </div>
          <div className="ml-auto px-2 py-1 rounded-lg text-[10px] font-medium"
            style={{ background: 'rgba(168,85,247,0.15)', color: '#c084fc' }}>
            {memoryTimeline.length} 条
          </div>
        </div>

        {/* Timeline Content */}
        <div className="flex-1 overflow-y-auto agent-scroll px-4 py-4">
          {memoryTimeline.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center px-4">
              <div className="w-16 h-16 rounded-2xl flex items-center justify-center text-3xl mb-4"
                style={{ background: 'linear-gradient(135deg, rgba(168,85,247,0.1), rgba(236,72,153,0.08))' }}>
                🔮
              </div>
              <h4 className="text-sm font-medium text-white mb-2" style={{ fontFamily: "'Noto Sans SC', sans-serif" }}>
                记忆活动流
              </h4>
              <p className="text-xs text-slate-500 leading-relaxed">
                开始对话后，你可以在这里实时看到<br/>
                AI 如何<span className="text-cyan-400">召回过去的记忆</span>来理解你，<br/>
                以及如何<span className="text-emerald-400">存储新的记忆</span>到大脑中。
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {memoryTimeline.map((item, index) => {
                const meta = getKeyMeta(item.key);
                const isRecall = item.type === 'recall';
                const isActive = activeRecallIds.has(item.fingerprint);

                return (
                  <div key={item.id}
                    className="rounded-xl p-3 transition-all duration-500 animate-fadeIn"
                    style={{
                      background: isActive
                        ? `linear-gradient(135deg, ${meta.color}15, ${meta.color}08)`
                        : 'rgba(30,41,59,0.4)',
                      border: `1px solid ${isActive ? `${meta.color}40` : 'rgba(100,116,139,0.1)'}`,
                      boxShadow: isActive ? `0 0 20px ${meta.color}15` : 'none',
                      animationDelay: `${index * 50}ms`,
                    }}
                  >
                    {/* Item Header */}
                    <div className="flex items-center gap-2 mb-1.5">
                      <div className="w-5 h-5 rounded-md flex items-center justify-center text-[10px]"
                        style={{
                          background: isRecall ? 'rgba(6,182,212,0.15)' : 'rgba(34,197,94,0.15)',
                        }}>
                        {isRecall ? '🔍' : '💾'}
                      </div>
                      <span className="text-[10px] font-medium"
                        style={{ color: isRecall ? '#22d3ee' : '#4ade80' }}>
                        {isRecall ? '召回记忆' : '存储新记忆'}
                      </span>
                      <span className="px-1.5 py-0.5 rounded text-[9px] font-medium"
                        style={{ backgroundColor: `${meta.color}20`, color: meta.color }}>
                        {meta.icon} {meta.label}
                      </span>
                      <span className="text-[9px] text-slate-500 ml-auto">{item.timestamp}</span>
                    </div>

                    {/* Tag */}
                    <div className="text-xs text-slate-200 font-medium mb-0.5"
                      style={{ fontFamily: "'Noto Sans SC', sans-serif" }}>
                      {item.tag}
                    </div>

                    {/* Memory Content */}
                    <div className="text-[11px] text-slate-400 leading-relaxed line-clamp-2"
                      style={{ fontFamily: "'Noto Sans SC', sans-serif" }}>
                      {item.memory}
                    </div>

                    {/* Recall Count */}
                    {isRecall && item.recallCount !== undefined && (
                      <div className="mt-1.5 flex items-center gap-1">
                        <div className="flex-1 h-1 rounded-full bg-slate-700/50 overflow-hidden">
                          <div className="h-full rounded-full transition-all duration-1000"
                            style={{
                              width: `${Math.min(item.recallCount * 8, 100)}%`,
                              background: `linear-gradient(90deg, ${meta.color}, ${meta.color}80)`,
                            }} />
                        </div>
                        <span className="text-[9px] text-slate-500">
                          ×{item.recallCount}
                        </span>
                      </div>
                    )}
                  </div>
                );
              })}
              <div ref={timelineEndRef} />
            </div>
          )}
        </div>

        {/* Sidebar Footer */}
        <div className="px-5 py-3 border-t border-white/5 flex-shrink-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5">
                <div className="w-2 h-2 rounded-full bg-cyan-400" />
                <span className="text-[10px] text-slate-400">
                  {memoryTimeline.filter(t => t.type === 'recall').length} 召回
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-2 h-2 rounded-full bg-emerald-400" />
                <span className="text-[10px] text-slate-400">
                  {memoryTimeline.filter(t => t.type === 'store').length} 存储
                </span>
              </div>
            </div>
            <span className="text-[10px] text-slate-500">Powered by GraphRAG</span>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─────────────── Sub-components ─────────────── */
function ReasoningToggle({ reasoning }: { reasoning: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mb-2">
      <button onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-[11px] text-slate-400 hover:text-slate-300 transition-colors">
        <svg className={`w-2.5 h-2.5 transition-transform ${open ? 'rotate-90' : ''}`}
          fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
        <span>思考过程</span>
      </button>
      {open && (
        <div className="mt-1 px-3 py-2 rounded-lg text-[11px] text-slate-400 leading-relaxed whitespace-pre-wrap"
          style={{ background: 'rgba(30,41,59,0.5)', border: '1px solid rgba(100,116,139,0.1)' }}>
          {DOMPurify.sanitize(reasoning, { ALLOWED_TAGS: [] })}
        </div>
      )}
    </div>
  );
}
