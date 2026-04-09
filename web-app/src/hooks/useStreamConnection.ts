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

  const connect = useCallback((instanceId: string, message: string, turn: number = 1) => {
    // 断开已有连接
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    setIsConnected(false);
    setIsStreaming(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    // 发送 POST 请求启动 SSE 流
    fetch(`/api/chat/stream/${instanceId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, turn }),
      signal: controller.signal,
    })
      .then(response => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        setIsConnected(true);

        const reader = response.body?.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let currentEventType = 'message';

        const readStream = () => {
          reader?.read().then(({ done, value }) => {
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
                // 优先使用 SSE event: 行指定的类型，否则用消息内的 type
                const eventType = currentEventType || rawEvent.type || 'message';
                const event = { ...rawEvent, type: eventType } as StreamEvent;
                currentEventType = 'message'; // 重置

                switch (event.type) {
                  case 'reasoning':
                    options.onReasoning?.((event as any).delta || (event as any).content);
                    break;
                  case 'content':
                    options.onContent?.((event as any).delta || (event as any).content);
                    break;
                  case 'done':
                    options.onDone?.((event as any).content, (event as any).has_recalled, (event as any).recall_blocks);
                    setIsStreaming(false);
                    break;
                  case 'error':
                    options.onError?.((event as any).message);
                    setIsStreaming(false);
                    break;
                  case 'storage_result':
                    options.onStorageResult?.(event as any);
                    break;
                  case 'tool_call':
                    options.onToolCall?.((event as any).tool_name, (event as any).params, (event as any).tool_call_id, (event as any).result);
                    break;
                  case 'tool_return':
                    options.onToolReturn?.((event as any).tool_name, (event as any).tool_call_id, (event as any).result);
                    break;
                  case 'agent_thinking':
                    options.onAgentThinking?.((event as any).agent, (event as any).phase);
                    break;
                  case 'agent_tool_call':
                    options.onAgentToolCall?.((event as any).agent, (event as any).tool, (event as any).params);
                    break;
                  case 'agent_result':
                    options.onAgentResult?.((event as any).agent, (event as any).result);
                    break;
                  case 'storage_progress':
                    options.onStorageProgress?.((event as any).stage, (event as any).progress);
                    break;
                  default:
                    if ((event as any).type === 'heartbeat') {
                      options.onHeartbeat?.();
                    }
                    break;
                }
              } catch {
                // 忽略解析错误
              }
            }

            readStream();
          });
        };

        readStream();
      })
      .catch(err => {
        if (err.name !== 'AbortError') {
          options.onError?.(err.message);
          setIsStreaming(false);
        }
      });

    return () => {
      controller.abort();
    };
  }, [options]);

  const disconnect = useCallback(() => {
    abortControllerRef.current?.abort();
    setIsConnected(false);
    setIsStreaming(false);
  }, []);

  return { connect, disconnect, isConnected, isStreaming };
}
