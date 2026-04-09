import { useState } from 'react';
import { eventBus } from '../../utils/EventBus';
import { MEMORY_GRAPH_UPDATED } from '../../constants/events';

type Page = 'chat' | 'stats' | 'memory' | 'knowledge' | 'graph' | 'agent' | 'settings' | 'sub';

interface SidebarProps {
  currentPage: Page;
  onPageChange: (page: Page) => void;
}

const navItems: { key: Page; label: string; icon: React.ReactNode }[] = [
  {
    key: 'chat',
    label: '对话',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
    ),
  },
  {
    key: 'memory',
    label: '记忆',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
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
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
      </svg>
    ),
  },
  {
    key: 'agent',
    label: 'Agent',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="12" r="3" />
        <path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83" />
      </svg>
    ),
  },
  {
    key: 'graph',
    label: '图谱',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
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
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M18 20V10M12 20V4M6 20v-6" />
      </svg>
    ),
  },
  {
    key: 'settings',
    label: '设置',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="12" r="3" />
        <path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83" />
      </svg>
    ),
  },
  {
    key: 'sub',
    label: '历史',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M12 8v4l3 3" />
        <circle cx="12" cy="12" r="10" />
      </svg>
    ),
  },
];

export function Sidebar({ currentPage, onPageChange }: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false);

  const handleNavClick = (page: Page) => {
    onPageChange(page);
    if (page === 'graph') {
      eventBus.emit(MEMORY_GRAPH_UPDATED);
    }
  };

  return (
    <nav
      className={`fixed left-4 top-1/2 -translate-y-1/2 z-50 bg-neural-card/95 backdrop-blur-xl border border-neural-border rounded-2xl p-2 flex flex-col gap-1 transition-all duration-300 ${
        collapsed ? 'w-16' : 'w-auto'
      }`}
    >
      {/* 折叠按钮 */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="absolute -right-3 top-1/2 -translate-y-1/2 w-6 h-6 bg-neural-card border border-neural-border rounded-full flex items-center justify-center hover:bg-neural-card-hover transition-colors"
      >
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          className={`transition-transform duration-300 ${collapsed ? 'rotate-180' : ''}`}
        >
          <polyline points="15 18 9 12 15 6" />
        </svg>
      </button>

      {navItems.map((item) => (
        <button
          key={item.key}
          onClick={() => handleNavClick(item.key)}
          className={`px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 flex items-center gap-2 ${
            currentPage === item.key
              ? 'text-white bg-neural-card-hover'
              : 'text-slate-400 hover:text-white hover:bg-neural-card-hover'
          } ${collapsed ? 'justify-center w-12' : ''}`}
          title={collapsed ? item.label : undefined}
        >
          <span className={currentPage === item.key ? 'text-cyan-400' : ''}>{item.icon}</span>
          {!collapsed && <span>{item.label}</span>}
        </button>
      ))}
    </nav>
  );
}
