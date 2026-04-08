import { useState } from 'react';
import type { KbChunk } from '../../mock/knowledgeBase';

interface ChunkItemProps {
  chunk: KbChunk;
}

const BLOCK_TYPE_STYLES: Record<string, { badge: string; text: string }> = {
  paragraph: { badge: 'bg-slate-500/20 text-slate-400', text: '正文' },
  heading: { badge: 'bg-blue-500/20 text-blue-400', text: '标题' },
  code: { badge: 'bg-emerald-500/20 text-emerald-400', text: '代码' },
  table: { badge: 'bg-purple-500/20 text-purple-400', text: '表格' },
  formula: { badge: 'bg-orange-500/20 text-orange-400', text: '公式' },
  mixed: { badge: 'bg-pink-500/20 text-pink-400', text: '混合' },
};

export function ChunkItem({ chunk }: ChunkItemProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const style = BLOCK_TYPE_STYLES[chunk.block_type] || BLOCK_TYPE_STYLES.paragraph;

  // 渲染表格
  const renderTable = (text: string) => {
    const lines = text.split('\n').filter(line => line.trim());
    const rows = lines.map(line =>
      line.split('|').filter(cell => cell.trim() && !cell.match(/^[-:]+$/)).map(cell => cell.trim())
    );

    if (rows.length < 2) return <p className="whitespace-pre-wrap">{text}</p>;

    const headerRow = rows[0];
    const dataRows = rows.slice(1);

    return (
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr className="bg-neural-bg/50">
              {headerRow.map((cell, i) => (
                <th key={i} className="px-4 py-2 text-left text-sm font-medium text-slate-300 border border-neural-border">
                  {cell}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {dataRows.map((row, i) => (
              <tr key={i} className="hover:bg-neural-bg/30">
                {row.map((cell, j) => (
                  <td key={j} className="px-4 py-2 text-sm text-slate-400 border border-neural-border">
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  // 渲染内容
  const renderContent = () => {
    switch (chunk.block_type) {
      case 'code':
        return (
          <pre className="bg-[#1e1e1e] rounded-lg p-4 overflow-x-auto">
            <code className="text-sm text-slate-300 font-mono leading-relaxed">
              {chunk.text}
            </code>
          </pre>
        );
      case 'table':
        return renderTable(chunk.text);
      case 'formula':
        return (
          <div className="bg-neural-bg/50 rounded-lg p-6 text-center">
            <span className="text-2xl text-orange-400 font-mono">{chunk.text}</span>
          </div>
        );
      case 'heading':
        return (
          <h3 className={`font-bold text-slate-200 ${
            chunk.heading_level === 1 ? 'text-xl' :
            chunk.heading_level === 2 ? 'text-lg' :
            chunk.heading_level === 3 ? 'text-base' : 'text-sm'
          }`}>
            {chunk.text}
          </h3>
        );
      default:
        return (
          <p className="text-slate-300 leading-relaxed whitespace-pre-wrap font-chinese">
            {chunk.text}
          </p>
        );
    }
  };

  return (
    <div className="bg-neural-card/50 border border-neural-border rounded-xl overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-5 py-4 flex items-center gap-3 hover:bg-neural-card-hover/50 transition-colors"
      >
        {/* Expand Icon */}
        <svg
          className={`w-4 h-4 text-slate-500 transition-transform duration-200 ${isExpanded ? 'rotate-90' : ''}`}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <polyline points="9 18 15 12 9 6" />
        </svg>

        {/* Chunk Index */}
        <span className="text-xs font-mono text-slate-500 w-8">
          #{chunk.index}
        </span>

        {/* Block Type Badge */}
        <span className={`px-2 py-0.5 rounded text-xs font-medium ${style.badge}`}>
          {style.text}
        </span>

        {/* Heading Text */}
        {chunk.heading_text && (
          <span className="text-sm text-slate-400 truncate font-chinese">
            {chunk.heading_text}
          </span>
        )}

        {/* Preview (when collapsed) */}
        {!isExpanded && chunk.block_type !== 'heading' && (
          <span className="text-sm text-slate-500 truncate ml-auto">
            {chunk.text.slice(0, 50)}...
          </span>
        )}
      </button>

      {/* Content */}
      {isExpanded && (
        <div className="px-5 pb-5 animate-in fade-in slide-in-from-top-2 duration-200">
          <div className="border-t border-neural-border pt-4">
            {renderContent()}
          </div>
        </div>
      )}
    </div>
  );
}
