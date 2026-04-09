import { useState, useEffect } from 'react';

type Page = 'chat' | 'stats' | 'memory' | 'knowledge' | 'graph' | 'agent' | 'settings' | 'sub';

interface Instance {
  id: string;
  name: string;
}

interface HeaderProps {
  currentInstance?: Instance;
  onInstanceSwitch?: (instance: { id: string; name: string }) => void;
  onNewInstance?: () => void;
  currentPage?: Page;
  onPageChange?: (page: Page) => void;
}

const navItems: { key: Page; label: string; icon: React.ReactNode }[] = [
  {
    key: 'chat',
    label: '对话',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
    ),
  },
  {
    key: 'memory',
    label: '记忆',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2" />
        <rect x="9" y="3" width="6" height="4" rx="1" />
        <path d="M9 12h6M9 16h6" />
      </svg>
    ),
  },
  {
    key: 'knowledge',
    label: '知识',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
      </svg>
    ),
  },
  {
    key: 'agent',
    label: 'Agent',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="12" r="3" />
        <path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83" />
      </svg>
    ),
  },
  {
    key: 'graph',
    label: '图谱',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="5" cy="12" r="2" />
        <circle cx="19" cy="5" r="2" />
        <circle cx="19" cy="19" r="2" />
        <path d="M7 12h5M16 7l-2 2M16 17l-2-2" />
      </svg>
    ),
  },
  {
    key: 'stats',
    label: '统计',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M18 20V10M12 20V4M6 20v-6" />
      </svg>
    ),
  },
  {
    key: 'settings',
    label: '设置',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="12" r="3" />
        <path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83" />
      </svg>
    ),
  },
  {
    key: 'sub',
    label: '历史',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M12 8v4l3 3" />
        <circle cx="12" cy="12" r="10" />
      </svg>
    ),
  },
];

export function Header({ currentInstance, onInstanceSwitch, onNewInstance, currentPage, onPageChange }: HeaderProps) {
  const [instances, setInstances] = useState<Instance[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

  useEffect(() => {
    fetchInstances();
  }, []);

  const fetchInstances = async () => {
    try {
      setFetchError(null);
      const res = await fetch('/api/instances');
      if (res.ok) {
        const json = await res.json();
        const data = json.data || json;
        const instancesObj = data.instances || {};
        const currentName = data.current_instance || '';
        const list: Instance[] = Object.entries(instancesObj).map(([id, info]: [string, any]) => ({
          id,
          name: info.name || id,
        }));
        setInstances(list);
        if (list.length === 0 && !currentName) {
          setFetchError('暂无实例');
        }
      } else {
        setFetchError('加载失败');
      }
    } catch (error) {
      console.error('Failed to fetch instances:', error);
      setFetchError('网络错误');
    }
  };

  const handleSwitchInstance = async (instance: Instance) => {
    setLoading(true);
    try {
      const res = await fetch('/api/instances/use', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: instance.id }),
      });
      if (res.ok) {
        // Save current page before reload
        const currentPage = localStorage.getItem('currentPage');
        if (currentPage) {
          sessionStorage.setItem('restorePage', currentPage);
        }
        onInstanceSwitch?.(instance);
        setShowDropdown(false);
        window.location.reload();
      } else {
        setFetchError('切换失败');
      }
    } catch (error) {
      console.error('Failed to switch instance:', error);
      setFetchError('网络错误');
    } finally {
      setLoading(false);
    }
  };

  return (
    <header className="h-14 border-b border-neural-border bg-neural-card/80 backdrop-blur-lg px-4 flex items-center justify-between flex-shrink-0 relative z-50">
      {/* 左侧：Logo + 导航 */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-400 to-blue-500 flex items-center justify-center">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2">
              <path d="M12 2L2 7l10 5 10-5-10-5z" />
              <path d="M2 17l10 5 10-5" />
              <path d="M2 12l10 5 10-5" />
            </svg>
          </div>
          <h1 className="text-base font-bold text-white font-space">Memory Assistant</h1>
        </div>

        {/* 横向导航 */}
        {onPageChange && (
          <nav className="flex items-center gap-1 ml-4 border-l border-neural-border pl-4">
            {navItems.map((item) => (
              <button
                key={item.key}
                onClick={() => onPageChange(item.key)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-200 flex items-center gap-1.5 ${
                  currentPage === item.key
                    ? 'text-white bg-neural-card-hover'
                    : 'text-slate-400 hover:text-white hover:bg-neural-card-hover'
                }`}
              >
                <span className={currentPage === item.key ? 'text-cyan-400' : ''}>{item.icon}</span>
                <span>{item.label}</span>
              </button>
            ))}
          </nav>
        )}
      </div>

      {/* 右侧：实例切换 */}
      <div className="flex items-center gap-3">
        <button
          onClick={onNewInstance}
          className="px-3 py-1.5 text-sm text-slate-300 hover:text-white hover:bg-neural-card-hover rounded-lg transition-colors flex items-center gap-1"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          新建
        </button>

        <div className="relative">
          <button
            onClick={() => setShowDropdown(!showDropdown)}
            className="px-3 py-1.5 text-sm text-slate-300 hover:text-white hover:bg-neural-card-hover rounded-lg transition-colors flex items-center gap-1"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
              <circle cx="9" cy="7" r="4" />
              <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
              <path d="M16 3.13a4 4 0 0 1 0 7.75" />
            </svg>
            {currentInstance?.name || 'Loading...'}
            <span className="ml-1 px-1.5 py-0.5 bg-slate-700 rounded text-[10px]">
              {instances.length}
            </span>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>

          {showDropdown && (
            <div className="absolute right-0 top-full mt-1 w-56 bg-neural-card border border-neural-border rounded-lg shadow-xl py-1 z-[100]">
              {loading && <div className="px-3 py-2 text-sm text-slate-400">切换中...</div>}
              {fetchError && !loading && (
                <div className="px-3 py-2 text-sm text-amber-400">{fetchError}</div>
              )}
              {!loading && !fetchError && instances.length === 0 && (
                <div className="px-3 py-2 text-sm text-slate-400">暂无实例</div>
              )}
              {!loading && instances.map((instance) => (
                <button
                  key={instance.id}
                  onClick={() => handleSwitchInstance(instance)}
                  className={`w-full px-3 py-2 text-sm text-left hover:bg-neural-card-hover transition-colors flex items-center justify-between ${
                    instance.id === currentInstance?.id ? 'text-cyan-400 bg-cyan-500/10' : 'text-slate-300'
                  }`}
                >
                  <span className="truncate">{instance.name}</span>
                  {instance.id === currentInstance?.id && (
                    <span className="w-2 h-2 rounded-full bg-cyan-400 flex-shrink-0" />
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
