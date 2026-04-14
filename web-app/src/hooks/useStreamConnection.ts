import { useCallback, useRef, useState } from 'react';

export type StreamEventType = 'reasoning' | 'content' | 'done' | 'error' | 'tool_call' | 'storage_result' | 'tool_return' | 'agent_thinking' | 'agent_tool_call' | 'agent_result' | 'storage_progress' | 'heartbeat';

export interface ReasoningEvent {
  type: 'reasoning';
  delta: string;
}

export interface ContentEvent {
  type: 'content';
  delta: string;
}

export interface DoneEvent {
  type: 'done';
  content: string;
  has_recalled: boolean;
  recall_blocks?: Array<{
    fingerprint: string;
    key: string;
    tag: string;
    memory: string;
    created_at: string;
    recall_count: number;
  }>;
}

export interface ErrorEvent {
  type: 'error';
  message: string;
}

export interface StorageResult {
  type: 'storage_result';
  memories_added: Array<{
    memory_id: string;
    key: string;
    content_preview: string;
  }>;
  total_memories: number;
  duration_ms: number;
}

export interface ToolCallEvent {
  type: 'tool_call';
  tool_name: string;
  params: any;
  tool_call_id: string;
  result?: string;
}

export interface ToolReturnEvent {
  type: 'tool_return';
  tool_name: string;
  tool_call_id: string;
  result: string;
}

export interface AgentThinkingEvent {
  type: 'agent_thinking';
  agent: string;
  phase: string;
}

export interface AgentToolCallEvent {
  type: 'agent_tool_call';
  agent: string;
  tool: string;
  params: any;
}

export interface AgentResultEvent {
  type: 'agent_result';
  agent: string;
  result: any;
}

export interface StorageProgressEvent {
  type: 'storage_progress';
  stage: string;
  progress: any;
}

export type StreamEvent = ReasoningEvent | ContentEvent | DoneEvent | ErrorEvent | StorageResult | ToolCallEvent | ToolReturnEvent | AgentThinkingEvent | AgentToolCallEvent | AgentResultEvent | StorageProgressEvent;

interface UseStreamConnectionOptions {
  onReasoning?: (delta: string) => void;
  onContent?: (delta: string) => void;
  onDone?: (content: string, hasRecalled: boolean, recallBlocks?: any[]) => void;
  onError?: (message: string) => void;
  onStorageResult?: (result: StorageResult) => void;
  onToolCall?: (tool_name: string, params: any, tool_call_id: string, result?: string) => void;
  onToolReturn?: (tool_name: string, tool_call_id: string, result: string) => void;
  onAgentThinking?: (agent: string, phase: string) => void;
  onAgentToolCall?: (agent: string, tool: string, params: any) => void;
  onAgentResult?: (agent: string, result: any) => void;
  onStorageProgress?: (stage: string, progress: any) => void;
  onHeartbeat?: () => void;
}

export function useStreamConnection(options: UseStreamConnectionOptions) {
  const [isConnected, setIsConnected] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const connect = useCallback((instanceId: string, message: string, turn: number = 1, persona?: string, history?: any[]) => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    setIsConnected(false);
    setIsStreaming(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    const body: any = { message, turn };
    if (persona) body.persona = persona;
    if (history) body.history = history;

    fetch(`/api/chat/stream/${instanceId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    })
      .then(response => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        setIsConnected(true);

        const reader = response.body?.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let currentEventType = 'message';
        const opts = optionsRef.current;

        const readStream = () => {
          if (!reader || controller.signal.aborted) return;
          reader.read().then(({ done, value }) => {
            if (done || controller.signal.aborted) return;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() ?? '';

            for (const line of lines) {
              if (line.startsWith('event: ')) {
                currentEventType = line.slice(7).trim();
                continue;
              }
              if (!line.startsWith('data: ')) continue;
              const data = line.slice(6).trim();
              if (!data || data === '[DONE]') continue;

              try {
                const rawEvent = JSON.parse(data);
                const eventType = currentEventType || rawEvent.type || 'message';
                const event = { ...rawEvent, type: eventType } as StreamEvent;
                currentEventType = 'message';

                switch (event.type) {
                  case 'reasoning':
                    opts.onReasoning?.((event as any).delta || (event as any).content);
                    break;
                  case 'content':
                    opts.onContent?.((event as any).delta || (event as any).content);
                    break;
                  case 'done':
                    opts.onDone?.((event as any).content, (event as any).has_recalled, (event as any).recall_blocks);
                    setIsStreaming(false);
                    break;
                  case 'error':
                    opts.onError?.((event as any).message);
                    setIsStreaming(false);
                    break;
                  case 'storage_result':
                    opts.onStorageResult?.(event as any);
                    break;
                  case 'tool_call':
                    opts.onToolCall?.((event as any).tool_name, (event as any).params, (event as any).tool_call_id, (event as any).result);
                    break;
                  case 'tool_return':
                    opts.onToolReturn?.((event as any).tool_name, (event as any).tool_call_id, (event as any).result);
                    break;
                  case 'agent_thinking':
                    opts.onAgentThinking?.((event as any).agent, (event as any).phase);
                    break;
                  case 'agent_tool_call':
                    opts.onAgentToolCall?.((event as any).agent, (event as any).tool, (event as any).params);
                    break;
                  case 'agent_result':
                    opts.onAgentResult?.((event as any).agent, (event as any).result);
                    break;
                  case 'storage_progress':
                    opts.onStorageProgress?.((event as any).stage, (event as any).progress);
                    break;
                  default:
                    if ((event as any).type === 'heartbeat') {
                      opts.onHeartbeat?.();
                    }
                    break;
                }
              } catch {
                // ignore parse errors
              }
            }

            readStream();
          }).catch(err => {
            if (err.name !== 'AbortError') {
              console.error('[Stream] read error:', err);
            }
          });
        };

        readStream();
      })
      .catch(err => {
        if (err.name !== 'AbortError') {
          opts.onError?.(err.message);
          setIsStreaming(false);
        }
      });

    return () => {
      controller.abort();
    };
  }, []);

  const disconnect = useCallback(() => {
    abortControllerRef.current?.abort();
    setIsConnected(false);
    setIsStreaming(false);
  }, []);

  return { connect, disconnect, isConnected, isStreaming };
}