import type { ReactNode } from 'react';

interface StatCardProps {
  title: string;
  value: number | string;
  icon: ReactNode;
  trend?: {
    value: number;
    isPositive: boolean;
  };
  color: string;
}

export function StatCard({ title, value, icon, trend, color }: StatCardProps) {
  return (
    <div
      className="stat-card glass-card rounded-xl p-5 relative overflow-hidden group cursor-pointer"
      style={{ borderColor: `${color}20` }}
    >
      {/* Background glow */}
      <div
        className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300"
        style={{
          background: `radial-gradient(circle at 50% 0%, ${color}15, transparent 70%)`,
        }}
      />

      {/* Icon */}
      <div
        className="w-12 h-12 rounded-lg flex items-center justify-center mb-4 relative z-10"
        style={{ backgroundColor: `${color}20` }}
      >
        <div style={{ color }}>{icon}</div>
      </div>

      {/* Content */}
      <div className="relative z-10">
        <p className="text-sm text-slate-400 mb-1 font-chinese">{title}</p>
        <p className="text-3xl font-bold text-white font-space tracking-tight">
          {value}
        </p>

        {/* Trend */}
        {trend && (
          <div className="flex items-center mt-2 text-sm">
            <span
              className={trend.isPositive ? 'text-emerald-400' : 'text-rose-400'}
            >
              {trend.isPositive ? '↑' : '↓'} {Math.abs(trend.value)}%
            </span>
            <span className="text-slate-500 ml-1">vs last week</span>
          </div>
        )}
      </div>

      {/* Bottom accent line */}
      <div
        className="absolute bottom-0 left-0 right-0 h-0.5 opacity-60"
        style={{
          background: `linear-gradient(90deg, transparent, ${color}, transparent)`,
        }}
      />
    </div>
  );
}
