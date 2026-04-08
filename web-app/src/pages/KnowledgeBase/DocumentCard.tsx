import { getFileName, getFileExtension, formatFileSize } from '../../mock/knowledgeBase';
import type { KbDocument } from '../../mock/knowledgeBase';

interface DocumentCardProps {
  doc: KbDocument;
  isSelected: boolean;
  onClick: () => void;
}

const FileIcon = ({ ext }: { ext: string }) => {
  const colors: Record<string, string> = {
    pdf: '#FF6B6B',
    md: '#3B82F6',
    txt: '#64748B',
    doc: '#3B82F6',
    docx: '#3B82F6',
    xls: '#22C55E',
    xlsx: '#22C55E',
  };

  const color = colors[ext] || '#64748B';

  return (
    <div
      className="w-10 h-10 rounded-lg flex items-center justify-center"
      style={{ backgroundColor: `${color}20` }}
    >
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
        <line x1="16" y1="13" x2="8" y2="13" />
        <line x1="16" y1="17" x2="8" y2="17" />
        <line x1="10" y1="9" x2="8" y2="9" />
      </svg>
    </div>
  );
};

export function DocumentCard({ doc, isSelected, onClick }: DocumentCardProps) {
  const fileName = getFileName(doc.path);
  const ext = getFileExtension(doc.path);

  return (
    <div
      onClick={onClick}
      className={`p-4 rounded-xl cursor-pointer transition-all duration-200 group ${
        isSelected
          ? 'bg-gradient-to-r from-cyan-500/10 to-purple-500/10 border border-cyan-500/30'
          : 'bg-neural-card/50 border border-transparent hover:bg-neural-card-hover hover:border-neural-border'
      }`}
    >
      <div className="flex items-start gap-3">
        <FileIcon ext={ext} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-sm font-medium text-slate-200 truncate font-chinese">
              {fileName}
            </h3>
            {doc.status === 'pending' && (
              <span className="px-1.5 py-0.5 rounded text-xs bg-yellow-500/20 text-yellow-400">
                索引中
              </span>
            )}
          </div>
          <div className="flex items-center gap-3 text-xs text-slate-500">
            <span>{formatFileSize(doc.size)}</span>
            <span className="text-neural-border">|</span>
            <span>{doc.chunks_count} 块</span>
            <span className="text-neural-border">|</span>
            <span>{new Date(doc.indexed_at).toLocaleDateString('zh-CN')}</span>
          </div>
        </div>
        {isSelected && (
          <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
        )}
      </div>
    </div>
  );
}
