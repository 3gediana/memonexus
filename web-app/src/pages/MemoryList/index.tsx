import { useState, useMemo, useCallback, useEffect } from 'react';
import { KeyTabs } from './KeyTabs';
import { SearchInput } from './SearchInput';
import { MemoryCard } from './MemoryCard';
import { MemoryDetailModal } from './MemoryDetailModal';
import { MemorySpace } from './MemorySpace';
import type { Memory } from '../../mock/memoryList';

type SubPage = 'list' | 'space';

export function MemoryList() {
  const [activeKey, setActiveKey] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedMemory, setSelectedMemory] = useState<Memory | null>(null);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [keys, setKeys] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [subPage, setSubPage] = useState<SubPage>('list');

  useEffect(() => {
    fetchKeys();
  }, []);

  // keys 加载后获取记忆
  useEffect(() => {
    if (keys.length > 0) {
      fetchMemories();
    }
  }, [activeKey, keys]);

  const fetchKeys = async () => {
    try {
      const res = await fetch('/api/memory/keys');
      if (res.ok) {
        const data = await res.json();
        // 后端返回 {success: true, data: [{key, memory_count}, ...]}，提取key字段
        const keyNames = (data.data || []).map((k: any) => k.key || k);
        setKeys(keyNames);
      }
    } catch (err) {
      console.error('Failed to fetch keys:', err);
    }
  };

  const fetchMemories = async () => {
    try {
      setLoading(true);

      if (activeKey === 'all') {
        // 获取所有key的记忆
        const allMemories: any[] = [];
        await Promise.all(
          keys.map(async (key) => {
            const res = await fetch(`/api/memory/list?key=${encodeURIComponent(key)}`);
            if (res.ok) {
              const data = await res.json();
              allMemories.push(...(data.data || []));
            }
          })
        );
        setMemories(allMemories);
      } else {
        const res = await fetch(`/api/memory/list?key=${encodeURIComponent(activeKey)}`);
        if (res.ok) {
          const data = await res.json();
          setMemories(data.data || []);
        } else if (res.status === 422) {
          setMemories([]);
        }
      }
    } catch (err) {
      console.error('Failed to fetch memories:', err);
    } finally {
      setLoading(false);
    }
  };

  // Filter memories by search
  const filteredMemories = useMemo(() => {
    if (!searchQuery) return memories;
    return memories.filter((memory) => {
      return (
        memory.tag.toLowerCase().includes(searchQuery.toLowerCase()) ||
        memory.memory.toLowerCase().includes(searchQuery.toLowerCase())
      );
    });
  }, [memories, searchQuery]);

  const handleSearch = useCallback((query: string) => {
    setSearchQuery(query);
  }, []);

  return (
    <div className="min-h-screen neural-grid">
      {/* Header */}
      <header className="px-8 py-6 border-b border-neural-border sticky top-0 bg-neural-bg/80 backdrop-blur-lg z-10">
        <div className="max-w-5xl mx-auto">
          <div className="flex items-center justify-between mb-5">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-400 to-pink-500 flex items-center justify-center">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 2a10 10 0 1 0 10 10H12V2Z" />
                  <path d="M12 2a10 10 0 0 1 10 10" />
                  <circle cx="12" cy="12" r="6" />
                </svg>
              </div>
              <div>
                <h1 className="text-xl font-bold text-white font-space">记忆</h1>
                <p className="text-sm text-slate-400 font-chinese">
                  {subPage === 'list' ? `共 ${filteredMemories.length} 条记忆` : '永久便签 · 始终出现在对话上下文中'}
                </p>
              </div>
            </div>

            {/* Sub-page Tabs */}
            <div className="flex items-center gap-1 bg-neural-card/50 rounded-lg p-1">
              <button
                onClick={() => setSubPage('list')}
                className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all ${
                  subPage === 'list'
                    ? 'bg-cyan-500/20 text-cyan-400'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                记忆列表
              </button>
              <button
                onClick={() => setSubPage('space')}
                className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all ${
                  subPage === 'space'
                    ? 'bg-cyan-500/20 text-cyan-400'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                记忆空间
              </button>
            </div>
          </div>

          {/* Search - only show on list page */}
          {subPage === 'list' && (
            <div className="max-w-md">
              <SearchInput onSearch={handleSearch} />
            </div>
          )}
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-5xl mx-auto px-8 py-8">
        {subPage === 'space' ? (
          <MemorySpace />
        ) : (
          <>
            {/* Key Tabs */}
            <div className="mb-6">
              <KeyTabs keys={keys} activeKey={activeKey} onSelect={setActiveKey} />
            </div>

            {/* Memory Grid */}
            {loading ? (
              <div className="flex items-center justify-center py-20">
                <div className="w-12 h-12 border-4 border-cyan-500/30 border-t-cyan-500 rounded-full animate-spin" />
              </div>
            ) : filteredMemories.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {filteredMemories.map((memory, index) => (
                  <div
                    key={memory.fingerprint}
                    className="animate-in fade-in slide-in-from-bottom-4 duration-300"
                    style={{ animationDelay: `${index * 50}ms` }}
                  >
                    <MemoryCard
                      memory={memory}
                      onClick={() => setSelectedMemory(memory)}
                    />
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-20 text-center">
                <div className="w-16 h-16 rounded-full bg-neural-card/50 flex items-center justify-center mb-4">
                  <svg className="w-8 h-8 text-slate-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="11" cy="11" r="8" />
                    <path d="m21 21-4.35-4.35" />
                  </svg>
                </div>
                <p className="text-slate-400 font-chinese">没有找到匹配的记忆</p>
                <p className="text-sm text-slate-500 mt-1">尝试调整搜索条件或切换分类</p>
              </div>
            )}
          </>
        )}
      </main>

      {/* Detail Modal */}
      <MemoryDetailModal
        memory={selectedMemory}
        onClose={() => setSelectedMemory(null)}
      />

      {/* Footer */}
      <footer className="px-8 py-4 border-t border-neural-border mt-auto">
        <div className="max-w-5xl mx-auto flex items-center justify-between text-sm text-slate-500">
          <span className="font-chinese">记忆助手 v1.0</span>
          <span className="font-space">Memory {subPage === 'list' ? 'List' : 'Space'}</span>
        </div>
      </footer>
    </div>
  );
}
