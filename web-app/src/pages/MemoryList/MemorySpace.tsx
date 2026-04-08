import { useState, useEffect } from 'react';

interface MemorySpaceItem {
  id: number;
  content: string;
  created_at: string;
  updated_at: string;
  source: string;
}

export function MemorySpace() {
  const [items, setItems] = useState<MemorySpaceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [newContent, setNewContent] = useState('');
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editContent, setEditContent] = useState('');

  useEffect(() => {
    fetchItems();
  }, []);

  const fetchItems = async () => {
    try {
      const res = await fetch('/api/memory-space');
      if (res.ok) {
        const data = await res.json();
        setItems(data.data || []);
      }
    } catch (err) {
      console.error('Failed to fetch memory space:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleAdd = async () => {
    if (!newContent.trim()) return;
    try {
      const res = await fetch(`/api/memory-space?content=${encodeURIComponent(newContent.trim())}`, {
        method: 'POST',
      });
      if (res.ok) {
        setNewContent('');
        fetchItems();
      }
    } catch (err) {
      console.error('Failed to add memory space:', err);
    }
  };

  const handleUpdate = async (id: number) => {
    if (!editContent.trim()) return;
    try {
      const res = await fetch(`/api/memory-space/${id}?content=${encodeURIComponent(editContent.trim())}`, {
        method: 'PUT',
      });
      if (res.ok) {
        setEditingId(null);
        setEditContent('');
        fetchItems();
      }
    } catch (err) {
      console.error('Failed to update memory space:', err);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      const res = await fetch(`/api/memory-space/${id}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        fetchItems();
      }
    } catch (err) {
      console.error('Failed to delete memory space:', err);
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="w-12 h-12 border-4 border-cyan-500/30 border-t-cyan-500 rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="bg-neural-card/80 border border-neural-border rounded-xl p-4">
        <div className="flex gap-3">
          <textarea
            value={newContent}
            onChange={(e) => setNewContent(e.target.value)}
            placeholder="添加新的记忆空间条目..."
            rows={2}
            className="flex-1 bg-neural-bg border border-neural-border rounded-lg px-3 py-2 text-white placeholder-slate-500 resize-none focus:outline-none focus:ring-2 focus:ring-cyan-500/50 focus:border-cyan-500/50 font-chinese"
          />
          <button
            onClick={handleAdd}
            disabled={!newContent.trim()}
            className="px-4 py-2 bg-gradient-to-br from-cyan-500 to-blue-500 rounded-lg text-white font-medium hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-opacity self-end"
          >
            添加
          </button>
        </div>
      </div>

      {items.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <div className="w-16 h-16 rounded-full bg-neural-card/50 flex items-center justify-center mb-4">
            <svg className="w-8 h-8 text-slate-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 2a10 10 0 1 0 10 10H12V2Z" />
              <path d="M12 2a10 10 0 0 1 10 10" />
              <circle cx="12" cy="12" r="6" />
            </svg>
          </div>
          <p className="text-slate-400 font-chinese">记忆空间为空</p>
          <p className="text-sm text-slate-500 mt-1">添加的条目会始终出现在对话上下文中</p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            <div
              key={item.id}
              className="bg-neural-card/80 border border-neural-border rounded-xl p-4 hover:border-cyan-500/30 transition-colors group"
            >
              {editingId === item.id ? (
                <div className="space-y-3">
                  <textarea
                    value={editContent}
                    onChange={(e) => setEditContent(e.target.value)}
                    rows={2}
                    className="w-full bg-neural-bg border border-neural-border rounded-lg px-3 py-2 text-white resize-none focus:outline-none focus:ring-2 focus:ring-cyan-500/50 focus:border-cyan-500/50 font-chinese"
                    autoFocus
                  />
                  <div className="flex gap-2 justify-end">
                    <button
                      onClick={() => { setEditingId(null); setEditContent(''); }}
                      className="px-3 py-1.5 text-sm text-slate-400 hover:text-white transition-colors"
                    >
                      取消
                    </button>
                    <button
                      onClick={() => handleUpdate(item.id)}
                      className="px-3 py-1.5 text-sm bg-cyan-500/20 text-cyan-400 rounded-lg hover:bg-cyan-500/30 transition-colors"
                    >
                      保存
                    </button>
                  </div>
                </div>
              ) : (
                <div>
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <p className="text-slate-200 font-chinese leading-relaxed">{item.content}</p>
                      <div className="flex items-center gap-3 mt-2 text-xs text-slate-500">
                        <span>#{item.id}</span>
                        <span>来源: {item.source}</span>
                        <span>创建: {formatDate(item.created_at)}</span>
                        {item.updated_at !== item.created_at && (
                          <span>更新: {formatDate(item.updated_at)}</span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity ml-4">
                      <button
                        onClick={() => { setEditingId(item.id); setEditContent(item.content); }}
                        className="p-2 text-slate-400 hover:text-cyan-400 transition-colors"
                        title="编辑"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                          <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                        </svg>
                      </button>
                      <button
                        onClick={() => handleDelete(item.id)}
                        className="p-2 text-slate-400 hover:text-red-400 transition-colors"
                        title="删除"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <polyline points="3 6 5 6 21 6" />
                          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                        </svg>
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}