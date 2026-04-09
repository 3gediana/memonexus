import { useState, useEffect } from 'react';
import { getKeyColor } from '../../mock/memoryGraph';

interface SubRecord {
  id: number;
  raw_message: string;
  created_at: string;
  turn_index: number;
}

interface SubMemory {
  fingerprint: string;
  key: string;
  tag: string;
  memory: string;
  created_at: string;
}

export function Sub() {
  const [records, setRecords] = useState<SubRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [subMemories, setSubMemories] = useState<Record<number, SubMemory[]>>({});
  const [loadingMemories, setLoadingMemories] = useState<number | null>(null);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const limit = 20;

  useEffect(() => {
    fetchRecords();
  }, [offset]);

  const fetchRecords = async () => {
    try {
      setLoading(true);
      const res = await fetch(`/api/sub/list?limit=${limit}&offset=${offset}`);
      if (res.ok) {
        const json = await res.json();
        const items = json.data?.items || json.items || [];
        if (offset === 0) {
          setRecords(items);
        } else {
          setRecords(prev => [...prev, ...items]);
        }
        setHasMore(items.length === limit);
      }
    } catch (err) {
      console.error('Failed to fetch sub records:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchSubMemories = async (subId: number) => {
    try {
      setLoadingMemories(subId);
      const res = await fetch(`/api/sub/${subId}/memories`);
      if (res.ok) {
        const data = await res.json();
        setSubMemories(prev => ({ ...prev, [subId]: data.data?.items || [] }));
      }
    } catch (err) {
      console.error('Failed to fetch sub memories:', err);
    } finally {
      setLoadingMemories(null);
    }
  };

  const toggleExpand = (subId: number) => {
    if (expandedId === subId) {
      setExpandedId(null);
    } else {
      setExpandedId(subId);
      if (!subMemories[subId]) {
        fetchSubMemories(subId);
      }
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

  if (loading && offset === 0) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="w-12 h-12 border-4 border-cyan-500/30 border-t-cyan-500 rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6">
      <div className="bg-neural-card/80 border border-neural-border rounded-xl p-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-white font-medium">对话历史记录</h3>
            <p className="text-sm text-slate-400 mt-1">共 {records.length} 条记录（原始用户消息）</p>
          </div>
          <button
            onClick={() => { setOffset(0); fetchRecords(); }}
            className="px-3 py-1.5 text-sm bg-neural-bg/50 hover:bg-neural-bg border border-neural-border rounded-lg text-slate-400 transition-colors"
          >
            刷新
          </button>
        </div>
      </div>

      {records.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <div className="w-16 h-16 rounded-full bg-neural-card/50 flex items-center justify-center mb-4">
            <svg className="w-8 h-8 text-slate-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
          </div>
          <p className="text-slate-400 font-chinese">暂无对话记录</p>
          <p className="text-sm text-slate-500 mt-1">开始对话后将显示原始消息记录</p>
        </div>
      ) : (
        <div className="space-y-3">
          {records.map((record) => (
            <div
              key={record.id}
              className="bg-neural-card/80 border border-neural-border rounded-xl overflow-hidden hover:border-cyan-500/30 transition-colors"
            >
              <div
                className="p-4 cursor-pointer"
                onClick={() => toggleExpand(record.id)}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="px-2 py-0.5 bg-cyan-500/20 text-cyan-400 rounded text-xs font-medium">
                        第 {record.turn_index} 轮
                      </span>
                      <span className="text-xs text-slate-500">
                        {formatDate(record.created_at)}
                      </span>
                    </div>
                    <p className="text-slate-200 font-chinese leading-relaxed">
                      {record.raw_message}
                    </p>
                  </div>
                  <svg
                    className={`w-5 h-5 text-slate-400 ml-4 transition-transform ${expandedId === record.id ? 'rotate-180' : ''}`}
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <polyline points="6 9 12 15 18 9" />
                  </svg>
                </div>
              </div>

              {expandedId === record.id && (
                <div className="border-t border-neural-border bg-neural-bg/50 p-4">
                  {loadingMemories === record.id ? (
                    <div className="flex items-center justify-center py-4">
                      <div className="w-6 h-6 border-2 border-cyan-500/30 border-t-cyan-500 rounded-full animate-spin" />
                    </div>
                  ) : subMemories[record.id]?.length > 0 ? (
                    <div className="space-y-3">
                      <h4 className="text-xs text-slate-500 uppercase tracking-wider">提取的记忆</h4>
                      {subMemories[record.id].map((mem: SubMemory, idx: number) => (
                        <div
                          key={mem.fingerprint || idx}
                          className="bg-neural-card rounded-lg p-3 border border-neural-border"
                        >
                          <div className="flex items-center gap-2 mb-2">
                            <span
                              className="px-2 py-0.5 rounded text-xs font-medium"
                              style={{
                                backgroundColor: `${getKeyColor(mem.key)}20`,
                                color: getKeyColor(mem.key),
                              }}
                            >
                              {mem.key}
                            </span>
                            <span className="text-xs text-slate-500">#{mem.fingerprint?.slice(0, 12)}</span>
                          </div>
                          <p className="text-sm text-slate-300 font-chinese">{mem.tag}</p>
                          <p className="text-xs text-slate-500 mt-1 line-clamp-2">{mem.memory}</p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-slate-500 text-center py-4">该轮对话未提取记忆</p>
                  )}
                </div>
              )}
            </div>
          ))}

          {hasMore && (
            <div className="flex justify-center pt-4">
              <button
                onClick={() => setOffset(prev => prev + limit)}
                className="px-4 py-2 bg-neural-card/80 border border-neural-border rounded-lg text-slate-400 hover:text-white hover:border-cyan-500/30 transition-colors"
              >
                加载更多
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}