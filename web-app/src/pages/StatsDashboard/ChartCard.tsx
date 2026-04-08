import type { ReactNode } from 'react';

interface ChartCardProps {
  title: string;
  children: ReactNode;
  className?: string;
}

export function ChartCard({ title, children, className = '' }: ChartCardProps) {
  return (
    <div className={`glass-card rounded-xl p-5 ${className}`}>
      <h3 className="text-sm font-medium text-slate-400 mb-4 font-chinese flex items-center gap-2">
        <span className="w-1 h-4 rounded-full bg-gradient-to-b from-cyan-400 to-purple-500" />
        {title}
      </h3>
      {children}
    </div>
  );
}
