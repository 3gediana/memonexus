import { useState, useRef, useEffect } from 'react';
import DOMPurify from 'dompurify';
import { ChatMessage } from './ChatMessage';
import { AgentEventLog } from './AgentEventLog';
import { useStreamConnection, type StorageResult } from '../../hooks/useStreamConnection';

interface Message {
  id: string;
  turn: number;
  role: 'user' | 'assistant';
  content: string;
  reasoning?: string;
  recall_blocks?: Array<{
    fingerprint: string;
    key: string;
    tag: string;
    memory: string;
    created_at: string;
    recall_count: number;
  }>;
}

export function ChatDemo() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const reasoningRef = useRef('');
  const [speed] = useState(1);
  const [currentEvents, setCurrentEvents] = useState<Array<{
    id: string;
    timestamp: string;
    agentLabel: string;
    agentColor: string;
    direction: 'call' | 'return' | 'error';
    toolName: string;
    params?: string;
    result?: string;
    duration?: number;
    isOrphan?: boolean;
  }>>([]);
  const [storageResult, setStorageResult] = useState<StorageResult | null>(null);
  const [currentInstanceId, setCurrentInstanceId] = useState<string>('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    fetch('/api/instances/current')
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        const name = data?.data?.name || data?.data?.id;
        setCurrentInstanceId(name || 'study_assistant');
      })
      .catch(() => setCurrentInstanceId('study_assistant'));

    const handleInstanceSwitched = () => {
      fetch('/api/instances/current')
        .then(res => res.ok ? res.json() : null)
        .then(data => {
          const name = data?.data?.name || data?.data?.id;
          setCurrentInstanceId(name || 'study_assistant');
        })
        .catch(() => setCurrentInstanceId('study_assistant'));
    };
    window.addEventListener('instance-switched', handleInstanceSwitched);

    return () => {
      window.removeEventListener('instance-switched', handleInstanceSwitched);
    };
  }, []);

  useEffect(() => {
    if (!currentInstanceId) return;
    const stored = localStorage.getItem(`chat_history_${currentInstanceId}`);
    if (stored) {
      try {
        const parsed = JSON.parse(stored);
        if (Array.isArray(parsed)) setMessages(parsed);
      } catch { /* ignore parse errors */ }
    }
  }, [currentInstanceId]);

  useEffect(() => {
    if (!currentInstanceId || messages.length === 0) return;
    localStorage.setItem(`chat_history_${currentInstanceId}`, JSON.stringify(messages));
  }, [messages, currentInstanceId]);

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
        return [...prev, { id: Date.now().toString(), turn: prev.length + 1, role: 'assistant', content: delta }];
      });
    },
    onDone: (content, hasRecalled, recallBlocks) => {
      setIsStreaming(false);
      setIsThinking(false);
      const finalReasoning = reasoningRef.current || undefined;
      if (hasRecalled || (recallBlocks && recallBlocks.length > 0)) {
        setMessages(prev => {
          const last = prev[prev.length - 1];
          if (last?.role === 'assistant') {
            return [...prev.slice(0, -1), { ...last, reasoning: finalReasoning, recall_blocks: recallBlocks || [] }];
          }
          return prev;
        });
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
          if (last?.role === 'assistant') {
            if (!last.content || last.content.trim() === '') {
              return [...prev.slice(0, -1), { ...last, content }];
            }
          }
          return prev;
        });
      }
      if (hasRecalled) console.log('Response used memory recall');
    },
    onError: (message) => {
      setIsStreaming(false);
      setIsThinking(false);
      setMessages(prev => [...prev, {
        id: `error_${Date.now()}`,
        turn: prev.length > 0 ? prev[prev.length - 1].turn : 1,
        role: 'assistant' as const,
        content: `Error: ${message}`,
      }]);
      console.error('Stream error:', message);
    },
    onStorageResult: (result) => {
      setStorageResult(result);
      setCurrentEvents(prev => [...prev, {
        id: `storage_${Date.now()}`,
        timestamp: new Date().toLocaleTimeString(),
        agentLabel: 'StorageAgent',
        agentColor: '#8b5cf6',
        direction: 'return',
        toolName: 'store_memory',
        result: result.memories_added.length > 0 ? `✓ Stored ${result.memories_added.length} memories` : '⚠ No memories added',
      }]);
    },
    onToolCall: (tool_name, params, tool_call_id, result) => {
      setCurrentEvents(prev => {
        const existingIndex = prev.findIndex(e => e.id === tool_call_id);
        const newEvent = {
          id: tool_call_id,
          timestamp: existingIndex >= 0 ? prev[existingIndex].timestamp : new Date().toLocaleTimeString(),
          agentLabel: tool_name === 'recall_from_key' ? 'RecallAgent'
                    : tool_name === 'report_hits' ? 'HitAgent'
                    : 'KBAction',
          agentColor: tool_name === 'recall_from_key' ? '#f59e0b'
                    : tool_name === 'report_hits' ? '#10b981'
                    : '#6366f1',
          direction: 'call' as const,
          toolName: tool_name,
          params: typeof params === 'string' ? params : JSON.stringify(params),
          result: result,
        };
        if (existingIndex >= 0) {
          const updated = [...prev];
          updated[existingIndex] = { ...updated[existingIndex], ...newEvent, result: result || updated[existingIndex].result };
          return updated;
        }
        return [...prev, newEvent];
      });
    },
    onToolReturn: (tool_name, tool_call_id, result) => {
      setCurrentEvents(prev => {
        const existingIndex = prev.findIndex(e => e.id === tool_call_id);
        if (existingIndex >= 0) {
          const updated = [...prev];
          updated[existingIndex] = { ...updated[existingIndex], result, direction: 'return' };
          return updated;
        }
        return [...prev, {
          id: tool_call_id,
          timestamp: new Date().toLocaleTimeString(),
          agentLabel: tool_name === 'recall_from_key' ? 'RecallAgent'
                    : tool_name === 'report_hits' ? 'HitAgent'
                    : 'KBAction',
          agentColor: tool_name === 'recall_from_key' ? '#f59e0b'
                    : tool_name === 'report_hits' ? '#10b981'
                    : '#6366f1',
          direction: 'return' as const,
          toolName: tool_name,
          result: result,
          isOrphan: true,
        }];
      });
    },
    onAgentThinking: (agent, phase) => {
      setCurrentEvents(prev => [...prev, {
        id: `agent_thinking_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        timestamp: new Date().toLocaleTimeString(),
        agentLabel: agent,
        agentColor: '#8b5cf6',
        direction: 'call' as const,
        toolName: `[thinking] ${phase}`,
      }]);
    },
    onAgentToolCall: (agent, tool, params) => {
      const eventId = `agent_tool_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      setCurrentEvents(prev => [...prev, {
        id: eventId,
        timestamp: new Date().toLocaleTimeString(),
        agentLabel: agent,
        agentColor: '#06b6d4',
        direction: 'call' as const,
        toolName: `[${agent}] ${tool}`,
        params: JSON.stringify(params).slice(0, 200),
      }]);
    },
    onAgentResult: (agent, result) => {
      setCurrentEvents(prev => {
        const firstAgentCallIndex = prev.findIndex(
          e => e.agentLabel === agent && e.direction === 'call' && e.toolName.startsWith(`[${agent}]`)
        );
        if (firstAgentCallIndex >= 0) {
          const updated = [...prev];
          updated[firstAgentCallIndex] = {
            ...updated[firstAgentCallIndex],
            result: JSON.stringify(result).slice(0, 200),
            direction: 'return' as const
          };
          return updated;
        }
        return [...prev, {
          id: `agent_result_${Date.now()}`,
          timestamp: new Date().toLocaleTimeString(),
          agentLabel: agent,
          agentColor: '#10b981',
          direction: 'return' as const,
          toolName: `[result]`,
          result: JSON.stringify(result).slice(0, 200),
        }];
      });
    },
    onStorageProgress: (stage, progress) => {
      setCurrentEvents(prev => [...prev, {
        id: `storage_progress_${Date.now()}`,
        timestamp: new Date().toLocaleTimeString(),
        agentLabel: 'Storage',
        agentColor: '#f59e0b',
        direction: 'call' as const,
        toolName: `[${stage}]`,
        result: JSON.stringify(progress).slice(0, 200),
      }]);
    },
    onHeartbeat: () => {
      // Heartbeat events are not displayed, only used for keepalive detection
    },
  });

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, currentEvents, storageResult]);

  const handleNewConversation = async () => {
    disconnect();
    setIsStreaming(true);
    setIsThinking(false);
    setMessages([]);
    setStorageResult(null);
    reasoningRef.current = '';
    if (currentInstanceId) {
      localStorage.removeItem(`chat_history_${currentInstanceId}`);
    }

    // Add separator for new conversation
    setCurrentEvents(prev => [...prev, {
      id: `sep_${Date.now()}`,
      timestamp: new Date().toLocaleTimeString(),
      agentLabel: 'Session',
      agentColor: '#6b7280',
      direction: 'call' as const,
      toolName: '--- New Conversation ---',
    }]);

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
              if (eventType === 'agent_thinking') {
                setCurrentEvents(prev => [...prev, {
                  id: `clear_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
                  timestamp: new Date().toLocaleTimeString(),
                  agentLabel: data.agent,
                  agentColor: '#8b5cf6',
                  direction: 'call' as const,
                  toolName: `[thinking] ${data.phase}`,
                }]);
              } else if (eventType === 'agent_tool_call') {
                setCurrentEvents(prev => [...prev, {
                  id: `clear_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
                  timestamp: new Date().toLocaleTimeString(),
                  agentLabel: data.agent,
                  agentColor: '#06b6d4',
                  direction: 'call' as const,
                  toolName: `[${data.agent}] ${data.tool}`,
                  params: JSON.stringify(data.params).slice(0, 200),
                }]);
              } else if (eventType === 'agent_result') {
                setCurrentEvents(prev => {
                  const lastCallIndex = prev.findIndex(e => e.direction === 'call' && e.agentLabel === data.agent);
                  if (lastCallIndex >= 0) {
                    const updated = [...prev];
                    updated[lastCallIndex] = { ...updated[lastCallIndex], result: JSON.stringify(data.result).slice(0, 200), direction: 'return' };
                    return updated;
                  }
                  return [...prev, {
                    id: `clear_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
                    timestamp: new Date().toLocaleTimeString(),
                    agentLabel: data.agent,
                    agentColor: '#10b981',
                    direction: 'return' as const,
                    toolName: `[result]`,
                    result: JSON.stringify(data.result).slice(0, 200),
                  }];
                });
              } else if (eventType === 'storage_result') {
                setStorageResult({
                  type: 'storage_result',
                  memories_added: data.memories_added || [],
                  total_memories: data.total_memories || 0,
                });
              }
            } catch { /* skip non-JSON lines */ }
          }
        }
      }
    } catch (e) {
      console.error('Failed to clear dialogue:', e);
    } finally {
      setIsStreaming(false);
    }
  };

  const handleSend = () => {
    if (!input.trim() || isStreaming || !currentInstanceId) return;
    const userMessage: Message = {
      id: Date.now().toString(),
      turn: Math.ceil(messages.length / 2) + 1,
      role: 'user',
      content: input.trim(),
    };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsStreaming(true);
    setStorageResult(null);
    reasoningRef.current = '';
    connect(currentInstanceId, userMessage.content, userMessage.turn);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex h-full overflow-hidden">
      <div className="flex-1 flex flex-col min-w-0">
        <header className="h-14 border-b border-neural-border bg-neural-card/80 backdrop-blur-lg flex-shrink-0">
          <div className="h-full flex items-center gap-3 px-4">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-400 to-cyan-500 flex items-center justify-center flex-shrink-0">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
            </div>
            <div className="flex-1">
              <h1 className="text-xl font-bold text-white font-space">Dialog Demo</h1>
              <p className="text-sm text-slate-400 font-chinese">Memory Recall & Storage Visualization</p>
            </div>
            {isThinking && (
              <div className="flex items-center gap-2 px-3 py-1 bg-amber-500/10 border border-amber-500/30 rounded-full">
                <span className="animate-pulse text-amber-400 text-xs">Thinking...</span>
              </div>
            )}
          </div>
        </header>

        <div className="flex-1 overflow-y-auto relative">
          <div className="px-4 py-1 space-y-6">
            {messages.length === 0 && !isStreaming && (
              <div className="flex flex-col items-center justify-center h-48 text-center">
                <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-cyan-500/20 to-blue-500/20 flex items-center justify-center mb-4">
                  <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-cyan-400">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                  </svg>
                </div>
                <h3 className="text-white font-medium mb-2">Start New Conversation</h3>
                <p className="text-sm text-slate-400">Send a message to start chatting with the memory assistant</p>
              </div>
            )}

            {messages.map((msg, index) => (
              <div key={msg.id}>
                <ChatMessage role={msg.role} content={DOMPurify.sanitize(msg.content, { ALLOWED_TAGS: [] })} reasoning={msg.reasoning} recall_blocks={msg.recall_blocks} />
                {msg.role === 'assistant' && storageResult && index === messages.length - 1 && (
                  <div className="mt-3 ml-4 pl-4 border-l-2 border-emerald-500/50">
                    <div className="flex items-center gap-2 text-xs text-emerald-400 mb-2">
                      <span>Stored new memories</span>
                      <span className="text-slate-500">{storageResult.duration_ms}ms</span>
                    </div>
                    <div className="bg-neural-card/80 border border-neural-border rounded-lg p-3">
                      {storageResult.memories_added.length > 0 ? (
                        storageResult.memories_added.map((m, i) => (
                          <div key={i} className="flex items-center gap-2 mb-1">
                            <span className="px-2 py-0.5 bg-blue-500/20 text-blue-400 rounded text-xs">{m.key}</span>
                            <span className="text-xs text-slate-400">new</span>
                            <span className="text-sm text-slate-300 truncate">{m.content_preview}</span>
                          </div>
                        ))
                      ) : (
                        <div className="text-sm text-slate-400">No memories added</div>
                      )}
                      <div className="text-xs text-slate-500 mt-2">Total {storageResult.total_memories} memories</div>
                    </div>
                  </div>
                )}
              </div>
            ))}

            {isStreaming && (
              <div className="flex justify-start">
                <div className="bg-neural-card border border-neural-border px-4 py-3 rounded-2xl rounded-bl-md">
                  <div className="flex gap-1">
                    <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                    <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        <footer className="border-t border-neural-border bg-neural-card/50 backdrop-blur-lg flex-shrink-0 px-4 py-1">
            <div className="relative">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Type message..."
                rows={1}
                className="w-full bg-neural-bg border border-neural-border rounded-xl px-4 py-3 pr-24 text-white placeholder-slate-500 resize-none focus:outline-none focus:ring-2 focus:ring-cyan-500/50 focus:border-cyan-500/50 font-chinese"
              />
              <div className="absolute right-2 bottom-2 flex gap-2">
                <button onClick={handleNewConversation} className="w-9 h-9 bg-neural-card hover:bg-neural-card-hover border border-neural-border rounded-lg flex items-center justify-center transition-colors" title="New conversation">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M12 5v14M5 12h14" />
                  </svg>
                </button>
                <button onClick={handleSend} disabled={!input.trim() || isStreaming || !currentInstanceId} className="w-9 h-9 bg-gradient-to-br from-blue-500 to-cyan-500 rounded-lg flex items-center justify-center hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-opacity">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <line x1="22" y1="2" x2="11" y2="13" />
                    <polygon points="22 2 15 22 11 13 2 9 22 2" />
                  </svg>
                </button>
              </div>
            </div>
            <p className="text-xs text-slate-500 mt-2 text-center">Press Enter to send, Shift + Enter for new line</p>
        </footer>
      </div>

      <div className="w-[400px] flex-shrink-0">
        {currentEvents.length > 0 ? (
          <AgentEventLog events={currentEvents} speed={speed} />
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-center p-8 border-l border-neural-border bg-neural-card/30">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-cyan-500/20 to-blue-500/20 flex items-center justify-center mb-4">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-cyan-400">
                <circle cx="12" cy="12" r="3" />
                <path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83" />
              </svg>
            </div>
            <h3 className="text-white font-medium mb-2">Agent Event Flow</h3>
            <p className="text-sm text-slate-400">After sending a message, the Agent workflow will be displayed here<br/>Including tool calls, parameters and results</p>
          </div>
        )}
      </div>
    </div>
  );
}