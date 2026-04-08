import { getKeyColor } from '../../mock/statsDashboard';

interface KeyTabsProps {
  keys: string[];
  activeKey: string;
  onSelect: (key: string) => void;
}

export function KeyTabs({ keys, activeKey, onSelect }: KeyTabsProps) {
  const sortedKeys = [...keys].sort();

  return (
    <div className="flex flex-wrap gap-2">
      {/* All tab */}
      <button
        onClick={() => onSelect('all')}
        className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
          activeKey === 'all'
            ? 'bg-gradient-to-r from-cyan-500/20 to-purple-500/20 text-white border border-cyan-500/50'
            : 'bg-neural-card/50 text-slate-400 border border-transparent hover:bg-neural-card-hover hover:text-slate-200'
        }`}
      >
        全部
        <span className="ml-2 text-xs opacity-60">{keys.length}</span>
      </button>

      {/* Key tabs */}
      {sortedKeys.map((key) => {
        const color = getKeyColor(key);
        const isActive = activeKey === key;
        return (
          <button
            key={key}
            onClick={() => onSelect(key)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
              isActive
                ? 'text-white border'
                : 'bg-neural-card/50 text-slate-400 border border-transparent hover:bg-neural-card-hover hover:text-slate-200'
            }`}
            style={isActive ? {
              backgroundColor: `${color}15`,
              borderColor: `${color}50`
            } : undefined}
          >
            <span
              className="inline-block w-2 h-2 rounded-full mr-2"
              style={{ backgroundColor: color }}
            />
            {key}
          </button>
        );
      })}
    </div>
  );
}
