import { useState, useEffect } from 'react';
import { StatCard } from './StatCard';
import { ChartCard } from './ChartCard';
import { KeyPieChart } from './KeyPieChart';
import { StrengthPieChart } from './StrengthPieChart';
import { ValueBarChart } from './ValueBarChart';
import { RecallLineChart } from './RecallLineChart';
import { TopMemoryList } from './TopMemoryList';
import { getKeyColor } from '../../mock/memoryGraph';

// Icons as SVG components
const Icons = {
  Brain: () => (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 4.5a2.5 2.5 0 0 0-4.96-.46 2.5 2.5 0 0 0-1.98 3 2.5 2.5 0 0 0 1.32 4.24 3 3 0 0 0 .34 5.58 2.5 2.5 0 0 0 2.96 3.08A2.5 2.5 0 0 0 12 19.5a2.5 2.5 0 0 0 2.54-2.27 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0 1.32-4.24 2.5 2.5 0 0 0-1.98-3A2.5 2.5 0 0 0 12 4.5" />
      <path d="m15.7 10.4-.9.4" />
      <path d="m9.2 13.2-.9.4" />
      <path d="m13.6 15.7-.4-.9" />
      <path d="m10.8 9.2-.4-.9" />
      <path d="m15.7 13.5-.9-.4" />
      <path d="m9.2 10.9-.9-.4" />
      <path d="m10.4 15.7.4-.9" />
      <path d="m13.1 9.2.4-.9" />
    </svg>
  ),
  Link: () => (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
    </svg>
  ),
  Network: () => (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="5" r="3" />
      <circle cx="5" cy="19" r="3" />
      <circle cx="19" cy="19" r="3" />
      <line x1="12" y1="8" x2="5" y2="16" />
      <line x1="12" y1="8" x2="19" y2="16" />
    </svg>
  ),
  TrendingUp: () => (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
      <polyline points="16 7 22 7 22 13" />
    </svg>
  ),
};

export function StatsDashboard() {
  const [animated, setAnimated] = useState(false);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setAnimated(true);
    fetchStats();
  }, []);

  const fetchStats = async () => {
    try {
      setLoading(true);
      // 同时获取记忆统计和边统计
      const [memRes, edgeRes] = await Promise.all([
        fetch('/api/memory/stats'),
        fetch('/api/edge/stats'),
      ]);

      let mergedStats: any = {};

      if (memRes.ok) {
        const memData = await memRes.json();
        // 后端返回 {success: true, data: {...}}，提取data
        const memStats = memData.data || memData;
        // 适配前端字段名 - by_key可能是数组或对象，需要转换
        const adaptedByKey: Record<string, number> = {};
        if (Array.isArray(memStats.by_key)) {
          memStats.by_key.forEach((item: any) => {
            if (typeof item === 'object' && item.key) {
              adaptedByKey[item.key] = item.memory_count || item.count || 0;
            }
          });
        } else {
          Object.assign(adaptedByKey, memStats.by_key || {});
        }

        // value_distribution可能是数组，需要转换为对象
        const adaptedValueDist: Record<string, number> = {};
        if (Array.isArray(memStats.value_distribution)) {
          memStats.value_distribution.forEach((item: any) => {
            if (typeof item === 'object' && item.range) {
              adaptedValueDist[item.range] = item.count || 0;
            }
          });
        } else {
          Object.assign(adaptedValueDist, memStats.value_distribution || {});
        }

        // recall_distribution可能是数组，需要转换为对象
        const adaptedRecallDist: Record<string, number> = {};
        if (Array.isArray(memStats.recall_distribution)) {
          memStats.recall_distribution.forEach((item: any) => {
            if (typeof item === 'object' && item.range) {
              adaptedRecallDist[item.range] = item.count || 0;
            }
          });
        } else {
          Object.assign(adaptedRecallDist, memStats.recall_distribution || {});
        }

        mergedStats = {
          ...mergedStats,
          total_memories: memStats.total || 0,
          by_key: adaptedByKey,
          recall_distribution: adaptedRecallDist,
          value_distribution: adaptedValueDist,
          recent_7days: memStats.recent_7days || 0,
          top_recalled: memStats.top_recalled || [],
        };
      }

      if (edgeRes.ok) {
        const edgeData = await edgeRes.json();
        const edgeStats = edgeData.data || edgeData;
        // by_strength可能是数组，需要转换为对象
        let adaptedStrength: Record<string, number> = {};
        if (Array.isArray(edgeStats.strength_distribution)) {
          edgeStats.strength_distribution.forEach((item: any) => {
            if (typeof item === 'object' && item.strength !== undefined) {
              adaptedStrength[String(item.strength)] = item.count || 0;
            }
          });
        } else if (edgeStats.strength_distribution) {
          adaptedStrength = edgeStats.strength_distribution;
        }

        mergedStats = {
          ...mergedStats,
          total_edges: edgeStats.total || 0,
          clusters_count: edgeStats.clusters_count || 0,
          by_strength: adaptedStrength,
        };
      }

      if (memRes.ok || edgeRes.ok) {
        setStats(mergedStats);
      } else {
        setError('Failed to fetch stats');
      }
    } catch (err) {
      setError('Network error');
    } finally {
      setLoading(false);
    }
  };

  const isEmpty = stats && stats.total_memories === 0;

  if (loading) {
    return (
      <div className="min-h-screen neural-grid flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-cyan-500/30 border-t-cyan-500 rounded-full animate-spin mx-auto mb-4" />
          <p className="text-slate-400">加载中...</p>
        </div>
      </div>
    );
  }

  if (isEmpty) {
    return (
      <div className="min-h-screen neural-grid flex items-center justify-center">
        <div className="text-center">
          <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-cyan-500/20 to-purple-500/20 flex items-center justify-center mx-auto mb-4">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-cyan-400">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
          </div>
          <h3 className="text-white font-medium mb-2">暂无统计数据</h3>
          <p className="text-sm text-slate-400">开始对话后这里将展示统计信息</p>
          <button onClick={fetchStats} className="mt-4 px-4 py-2 bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-400 rounded-lg text-sm transition-colors">
            刷新
          </button>
        </div>
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div className="min-h-screen neural-grid flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-400 mb-2">{error || 'Failed to load stats'}</p>
          <button onClick={fetchStats} className="text-cyan-400 hover:text-cyan-300">
            重试
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen neural-grid">
      {/* Header */}
      <header className="px-8 py-6 border-b border-neural-border">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-400 to-purple-500 flex items-center justify-center">
              <Icons.Network />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white font-space">统计仪表盘</h1>
              <p className="text-sm text-slate-400 font-chinese">记忆助手系统运行状态</p>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-8 py-8">
        {/* Stats Cards */}
        <div className="grid grid-cols-4 gap-5 mb-8">
          <div
            className={`transform transition-all duration-700 ${animated ? 'translate-y-0 opacity-100' : 'translate-y-4 opacity-0'}`}
            style={{ transitionDelay: '0ms' }}
          >
            <StatCard
              title="总记忆数"
              value={stats.total_memories || 0}
              icon={<Icons.Brain />}
              trend={{ value: 12, isPositive: true }}
              color="#00d4ff"
            />
          </div>
          <div
            className={`transform transition-all duration-700 ${animated ? 'translate-y-0 opacity-100' : 'translate-y-4 opacity-0'}`}
            style={{ transitionDelay: '100ms' }}
          >
            <StatCard
              title="总边数"
              value={stats.total_edges || 0}
              icon={<Icons.Link />}
              trend={{ value: 8, isPositive: true }}
              color="#a855f7"
            />
          </div>
          <div
            className={`transform transition-all duration-700 ${animated ? 'translate-y-0 opacity-100' : 'translate-y-4 opacity-0'}`}
            style={{ transitionDelay: '200ms' }}
          >
            <StatCard
              title="总簇数"
              value={stats.clusters_count || 0}
              icon={<Icons.Network />}
              trend={{ value: 3, isPositive: false }}
              color="#22c55e"
            />
          </div>
          <div
            className={`transform transition-all duration-700 ${animated ? 'translate-y-0 opacity-100' : 'translate-y-4 opacity-0'}`}
            style={{ transitionDelay: '300ms' }}
          >
            <StatCard
              title="7日新增"
              value={stats.recent_7days || 0}
              icon={<Icons.TrendingUp />}
              trend={{ value: 25, isPositive: true }}
              color="#f97316"
            />
          </div>
        </div>

        {/* Charts Row 1 */}
        <div className="grid grid-cols-2 gap-5 mb-5">
          <ChartCard title="Key 分布">
            <KeyPieChart data={stats.by_key || []} getKeyColor={getKeyColor} />
          </ChartCard>
          <ChartCard title="价值分分布">
            <ValueBarChart data={stats.value_distribution || []} />
          </ChartCard>
        </div>

        {/* Charts Row 2 */}
        <div className="grid grid-cols-2 gap-5 mb-5">
          <ChartCard title="召回次数分布">
            <RecallLineChart data={stats.recall_distribution || []} />
          </ChartCard>
          <ChartCard title="边强度分布">
            <StrengthPieChart data={stats.by_strength || []} />
          </ChartCard>
        </div>

        {/* Top Memory List */}
        <ChartCard title="高价值记忆 TOP5" className="mt-5">
          <TopMemoryList data={stats.top_recalled || []} />
        </ChartCard>
      </main>

      {/* Footer */}
      <footer className="px-8 py-4 border-t border-neural-border mt-auto">
        <div className="max-w-7xl mx-auto flex items-center justify-between text-sm text-slate-500">
          <span className="font-chinese">记忆助手 v1.0</span>
          <span className="font-space">Last updated: {new Date().toLocaleDateString('zh-CN')}</span>
        </div>
      </footer>
    </div>
  );
}
