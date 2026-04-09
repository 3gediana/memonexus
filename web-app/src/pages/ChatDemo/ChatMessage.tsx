import { useState } from 'react';
import DOMPurify from 'dompurify';
import { getKeyColor } from '../../mock/chatDemo';
import type { RecallBlock, StorageResult } from '../../mock/chatDemo';

interface ChatMessageProps {
  role: 'user' | 'assistant';
  content: string;
  reasoning?: string;
  recall_blocks?: RecallBlock[];
  storage_result?: StorageResult;
}

export function ChatMessage({ role, content, reasoning, recall_blocks, storage_result }: ChatMessageProps) {
  const isUser = role === 'user';
  const [reasoningOpen, setReasoningOpen] = useState(false);
  const [recallOpen, setRecallOpen] = useState(false);

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[75%] ${isUser ? 'order-2' : 'order-1'}`}>
        {/* 推理思考过程（仅 assistant 且存在 reasoning 时显示） */}
        {!isUser && reasoning && (
          <div className="mb-2">
            <button
              onClick={() => setReasoningOpen(!reasoningOpen)}
              className="flex items-center gap-2 text-xs text-slate-400 hover:text-slate-300 transition-colors"
            >
              <svg
                className={`w-3 h-3 transition-transform ${reasoningOpen ? 'rotate-90' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
              <span>思考过程</span>
            </button>
            {reasoningOpen && (
              <div className="mt-1 bg-neural-card/50 border border-neural-border/50 rounded-lg px-3 py-2 text-xs text-slate-400 font-chinese leading-relaxed whitespace-pre-wrap">
                {DOMPurify.sanitize(reasoning, { ALLOWED_TAGS: [] })}
              </div>
            )}
          </div>
        )}

        {/* 气泡 */}
        <div
          className={`px-4 py-3 rounded-2xl ${
            isUser
              ? 'bg-gradient-to-br from-blue-500 to-cyan-500 text-white rounded-br-md'
              : 'bg-neural-card border border-neural-border text-slate-200 rounded-bl-md'
          }`}
        >
          <p className="text-sm leading-relaxed font-chinese whitespace-pre-wrap">{content}</p>
        </div>

        {/* 召回记忆块（可折叠） */}
        {!isUser && recall_blocks && recall_blocks.length > 0 && (
          <div className="mt-1.5">
            <button
              onClick={() => setRecallOpen(!recallOpen)}
              className="inline-flex items-center gap-1.5 text-[11px] text-cyan-400/80 hover:text-cyan-400 transition-colors"
            >
              <svg
                className={`w-2.5 h-2.5 transition-transform ${recallOpen ? 'rotate-90' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
              <span>召回 {recall_blocks.length} 条记忆</span>
            </button>
            {recallOpen && (
              <div className="mt-1 pl-3 border-l-2 border-cyan-500/30 space-y-1">
                {recall_blocks.map((block) => (
                  <div key={block.fingerprint} className="text-[11px] font-chinese">
                    <span
                      className="px-1.5 py-0.5 rounded text-[10px] font-medium mr-1.5"
                      style={{
                        backgroundColor: `${getKeyColor(block.key)}15`,
                        color: getKeyColor(block.key),
                      }}
                    >
                      {block.key}
                    </span>
                    <span className="text-slate-300">{block.memory}</span>
                    <span className="text-slate-500 ml-1">×{block.recall_count}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* 存储结果 */}
        {storage_result && (
          <div className="mt-3">
            <div
              className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs ${
                storage_result.action === 'added'
                  ? 'bg-emerald-500/10 text-emerald-400'
                  : storage_result.action === 'updated'
                  ? 'bg-amber-500/10 text-amber-400'
                  : storage_result.action === 'duplicate'
                  ? 'bg-slate-500/10 text-slate-400'
                  : 'bg-red-500/10 text-red-400'
              }`}
            >
              <span>
                {storage_result.action === 'added'
                  ? '💾'
                  : storage_result.action === 'updated'
                  ? '🔄'
                  : storage_result.action === 'duplicate'
                  ? '📋'
                  : '⚠️'}
              </span>
              <span className="font-medium">
                {storage_result.action === 'added'
                  ? '存储记忆'
                  : storage_result.action === 'updated'
                  ? '更新记忆'
                  : storage_result.action === 'duplicate'
                  ? '记忆已存在'
                  : '存储失败'}
              </span>
              <span className="text-slate-400">
                [{storage_result.key}] {storage_result.tag}
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
