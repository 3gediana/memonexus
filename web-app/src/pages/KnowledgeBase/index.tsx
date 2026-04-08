import { useState, useEffect } from 'react';
import { DocumentCard } from './DocumentCard';
import { ChunkItem } from './ChunkItem';
import type { KbDocument, KbChunk } from '../../mock/knowledgeBase';

interface DocWithChunks extends KbDocument {
  chunks?: KbChunk[];
}

export function KnowledgeBase() {
  const [documents, setDocuments] = useState<DocWithChunks[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<DocWithChunks | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    fetchDocuments();
  }, []);

  const fetchDocuments = async () => {
    try {
      setLoading(true);
      // 后端实际端点是 /api/knowledge/files
      const res = await fetch('/api/knowledge/files');
      if (res.ok) {
        const data = await res.json();
        // 后端返回 {success: true, data: [...]}，需要从data中提取
        const docs = data.data || [];
        setDocuments(docs);
      } else {
        // 使用空数组作为后备
        setDocuments([]);
      }
    } catch (err) {
      console.error('Failed to fetch documents:', err);
      setDocuments([]);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) {
      setSearchResults([]);
      return;
    }
    try {
      setSearching(true);
      const res = await fetch('/api/knowledge/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: searchQuery, top_k: 10 }),
      });
      if (res.ok) {
        const data = await res.json();
        // 后端返回 {success: true, data: {results: [...]}}
        setSearchResults(data.data?.results || []);
      }
    } catch (err) {
      console.error('Failed to search:', err);
    } finally {
      setSearching(false);
    }
  };

  const clearSearch = () => {
    setSearchQuery('');
    setSearchResults([]);
  };

  const handleSelectDoc = async (doc: DocWithChunks) => {
    setSelectedDoc(doc);
    // 如果文档没有 chunks，获取详情
    if (!doc.chunks) {
      try {
        const res = await fetch(`/api/knowledge/${doc.fingerprint}/chunks`);
        if (res.ok) {
          const data = await res.json();
          // 后端返回 {success: true, data: {items: [...], total: ...}}
          const rawChunks = data.data?.items || [];
          // 适配前端期望的 KbChunk 格式
          const adaptedChunks = rawChunks.map((c: any, idx: number) => ({
            id: c.chunk_id || `${doc.fingerprint}-${idx}`,
            text: c.text || c.preview || '',
            index: c.index ?? idx,
            start_pos: 0,
            end_pos: 0,
            block_type: 'paragraph' as const,
            heading_level: 0,
            heading_text: '',
          }));
          setSelectedDoc({ ...doc, chunks: adaptedChunks });
        }
      } catch (err) {
        console.error('Failed to fetch chunks:', err);
      }
    }
  };

  const chunks = selectedDoc?.chunks || [];

  // 获取文件名
  const getFileName = (path: string): string => {
    const parts = path.split('/');
    return parts[parts.length - 1] || path;
  };

  // 计算总 chunks 数
  const totalChunks = documents.reduce((sum, d) => sum + (d.chunks_count || 0), 0);

  return (
    <div className="min-h-screen neural-grid">
      {/* Header */}
      <header className="px-8 py-6 border-b border-neural-border">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-400 to-cyan-500 flex items-center justify-center">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
              </svg>
            </div>
            <div>
              <h1 className="text-xl font-bold text-white font-space">知识库</h1>
              <p className="text-sm text-slate-400 font-chinese">
                共 {documents.length} 个文档，{totalChunks} 个文本块
              </p>
            </div>
            <form onSubmit={handleSearch} className="flex gap-2">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="搜索知识库..."
                className="px-4 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white text-sm focus:outline-none focus:border-cyan-500 w-64"
              />
              <button
                type="submit"
                disabled={searching}
                className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 disabled:bg-slate-700 text-white rounded-lg text-sm font-medium transition-colors"
              >
                {searching ? '搜索中...' : '搜索'}
              </button>
              {searchResults.length > 0 && (
                <button
                  type="button"
                  onClick={clearSearch}
                  className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg text-sm font-medium transition-colors"
                >
                  清除
                </button>
              )}
            </form>
          </div>
        </div>
      </header>

      {/* Main Content - Split Layout */}
      <main className="max-w-7xl mx-auto px-8 py-8">
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="w-12 h-12 border-4 border-cyan-500/30 border-t-cyan-500 rounded-full animate-spin" />
          </div>
        ) : documents.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64">
            <div className="w-20 h-20 rounded-full bg-neural-card/50 flex items-center justify-center mb-4">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-slate-500">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
              </svg>
            </div>
            <p className="text-slate-400 font-chinese">暂无文档</p>
            <p className="text-sm text-slate-500 mt-1">请先上传文档到知识库</p>
          </div>
        ) : searchResults.length > 0 ? (
          <div className="flex flex-col items-center justify-center h-64">
            <p className="text-slate-400 font-chinese mb-4">搜索到 {searchResults.length} 条结果</p>
            <div className="w-full max-w-2xl space-y-3">
              {searchResults.map((result, idx) => (
                <div key={idx} className="bg-neural-card border border-neural-border rounded-lg p-4">
                  <p className="text-white text-sm">{result.text || result.preview || '无内容'}</p>
                  {result.score && (
                    <p className="text-xs text-cyan-400 mt-2">相关度: {result.score.toFixed(3)}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-12 gap-6 h-[calc(100vh-200px)]">
            {/* Left Panel - Document List */}
            <div className="col-span-4 lg:col-span-3 overflow-hidden flex flex-col">
              <h2 className="text-sm font-medium text-slate-400 mb-4 flex items-center gap-2">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                </svg>
                文档列表
              </h2>
              <div className="flex-1 overflow-y-auto space-y-3 pr-2">
                {documents.map((doc) => (
                  <DocumentCard
                    key={doc.fingerprint}
                    doc={doc}
                    isSelected={selectedDoc?.fingerprint === doc.fingerprint}
                    onClick={() => handleSelectDoc(doc)}
                  />
                ))}
              </div>
            </div>

            {/* Right Panel - Chunk List */}
            <div className="col-span-8 lg:col-span-9 overflow-hidden flex flex-col">
              {selectedDoc ? (
                <>
                  <h2 className="text-sm font-medium text-slate-400 mb-4 flex items-center gap-2">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                      <line x1="3" y1="9" x2="21" y2="9" />
                      <line x1="9" y1="21" x2="9" y2="9" />
                    </svg>
                    文本块 - {getFileName(selectedDoc.path)}
                  </h2>
                  <div className="flex-1 overflow-y-auto space-y-3 pr-2">
                    {chunks.length > 0 ? (
                      chunks.map((chunk) => (
                        <ChunkItem key={chunk.id} chunk={chunk} />
                      ))
                    ) : (
                      <div className="text-center text-slate-500 py-8">暂无文本块</div>
                    )}
                  </div>
                </>
              ) : (
                <div className="flex-1 flex flex-col items-center justify-center text-center">
                  <div className="w-20 h-20 rounded-full bg-neural-card/50 flex items-center justify-center mb-4">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-slate-500">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                      <polyline points="14 2 14 8 20 8" />
                      <line x1="16" y1="13" x2="8" y2="13" />
                      <line x1="16" y1="17" x2="8" y2="17" />
                      <line x1="10" y1="9" x2="8" y2="9" />
                    </svg>
                  </div>
                  <p className="text-slate-400 font-chinese mb-1">选择一个文档</p>
                  <p className="text-sm text-slate-500">点击左侧文档查看其包含的文本块</p>
                </div>
              )}
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="px-8 py-4 border-t border-neural-border mt-auto">
        <div className="max-w-7xl mx-auto flex items-center justify-between text-sm text-slate-500">
          <span className="font-chinese">记忆助手 v1.0</span>
          <span className="font-space">Knowledge Base</span>
        </div>
      </footer>
    </div>
  );
}
