import { useState, useEffect, useCallback } from 'react';
import { StatCard } from '../StatsDashboard/StatCard';

interface Config {
  freeze_timeout_seconds: number;
  topk_default: number;
  context_threshold: number;
  idle_timeout: number;
  max_memories_per_recall: number;
}

interface MemoryStats {
  total: number;
  by_key: Record<string, number>;
  recent_7days: number;
  recall_distribution: Record<string, number>;
  value_distribution: Record<string, number>;
  semantic_status: Record<string, number>;
  top_recalled: Array<{ fingerprint: string; key: string; tag: string; recall_count: number; last_recall_at: string }>;
}

interface EdgeStats {
  total: number;
  strength_distribution: Record<string, number>;
  effective_strength_distribution: Record<string, number>;
  avg_strength: number;
  avg_effective_strength: number;
  top_by_hits: Array<{ source: string; target: string; strength: number; effective_strength: number; hit_count: number; recall_count: number; reason: string }>;
  top_by_recalls: Array<{ source: string; target: string; strength: number; effective_strength: number; hit_count: number; recall_count: number; reason: string }>;
}

interface MonitorData {
  instance: string;
  memory: { total: number; by_key: Record<string, number>; recent_7days: number };
  edge: { total: number; by_strength: Record<string, number>; avg_strength: number };
  cluster: { cluster_count: number; memory_count: number };
  preference: { total_calls: number; keys: Record<string, number> };
  sub: { total: number; recent_7days: number };
}

const PARAM_DESCRIPTIONS = [
  {
    key: 'topk_default',
    name: 'top_k 召回数量',
    description: '每次召回记忆时的最大数量。控制上下文窗口中注入的相关记忆条数',
    formula: '召回数 = min(k, 实际匹配数)',
    detail: '值越大，LLM 获得的上下文越丰富，但可能引入噪声。建议 2-5',
  },
  {
    key: 'max_memories_per_recall',
    name: '最大召回上限',
    description: '单次召回操作的记忆数量上限，防止极端情况下过多记忆涌入上下文',
    formula: 'top_n = min(top_k × 实例数, max_memories_per_recall)',
    detail: '安全阀值，即使 top_k 设置很大也不会超过此限制',
  },
  {
    key: 'context_threshold',
    name: '上下文阈值',
    description: '触发压缩的 token 数量阈值。当对话历史超过此值时自动压缩',
    formula: '当 context_tokens > threshold 时触发压缩',
    detail: '150000 tokens ≈ 75000 中文字。压缩由 CompressionAgent 执行',
  },
  {
    key: 'idle_timeout',
    name: '空闲超时',
    description: '实例空闲多少秒后自动冻结，释放资源并停止后台任务',
    formula: '冻结时间 = last_active + idle_timeout',
    detail: '冻结后实例数据保留但不再消耗 API 调用',
  },
  {
    key: 'freeze_timeout_seconds',
    name: '冻结超时',
    description: '冻结队列处理超时时间（秒），防止冻结操作卡死',
    formula: '队列超时 = freeze_timeout_seconds',
    detail: '仅在多实例并发冻结时生效',
  },
];

export function Settings() {
  const [config, setConfig] = useState<Config | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [memoryStats, setMemoryStats] = useState<MemoryStats | null>(null);
  const [edgeStats, setEdgeStats] = useState<EdgeStats | null>(null);
  const [monitorData, setMonitorData] = useState<MonitorData | null>(null);
  const [activeTab, setActiveTab] = useState<'config' | 'algorithm' | 'monitor'>('config');

  useEffect(() => {
    fetchConfig();
    fetchMemoryStats();
    fetchEdgeStats();
    fetchMonitorData();
  }, []);

  const fetchConfig = async () => {
    try {
      const res = await fetch('/api/config');
      if (res.ok) {
        const data = await res.json();
        setConfig(data.data || data);
      }
    } catch (err) {
      console.error('Failed to fetch config:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchMemoryStats = async () => {
    try {
      const res = await fetch('/api/memory/stats');
      if (res.ok) {
        const data = await res.json();
        setMemoryStats(data.data || data);
      }
    } catch (err) {
      console.error('Failed to fetch memory stats:', err);
    }
  };

  const fetchEdgeStats = async () => {
    try {
      const res = await fetch('/api/edge/stats');
      if (res.ok) {
        const data = await res.json();
        setEdgeStats(data.data || data);
      }
    } catch (err) {
      console.error('Failed to fetch edge stats:', err);
    }
  };

  const fetchMonitorData = async () => {
    try {
      const res = await fetch('/api/monitor/status');
      if (res.ok) {
        const data = await res.json();
        setMonitorData(data.data || data);
      }
    } catch (err) {
      console.error('Failed to fetch monitor data:', err);
    }
  };

  const handleSave = async () => {
    if (!config) return;
    setSaving(true);
    setMessage(null);
    try {
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topk_default: config.topk_default,
          context_threshold: config.context_threshold,
          idle_timeout: config.idle_timeout,
          max_memories_per_recall: config.max_memories_per_recall,
          freeze_timeout_seconds: config.freeze_timeout_seconds,
        }),
      });
      if (res.ok) {
        setMessage({ type: 'success', text: '配置保存成功' });
      } else {
        setMessage({ type: 'error', text: '保存失败' });
      }
    } catch (err) {
      setMessage({ type: 'error', text: '网络错误' });
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (!confirm('确定要重置所有配置到默认值吗？')) return;
    setResetting(true);
    setMessage(null);
    try {
      const res = await fetch('/api/config/reset', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setConfig(data.data || data);
        setMessage({ type: 'success', text: '已重置为默认值' });
      } else {
        setMessage({ type: 'error', text: '重置失败' });
      }
    } catch (err) {
      setMessage({ type: 'error', text: '网络错误' });
    } finally {
      setResetting(false);
    }
  };

  const handleChange = (key: keyof Config, value: string) => {
    if (!config) return;
    const numValue = parseInt(value, 10);
    if (!isNaN(numValue) && numValue >= 0) {
      setConfig({ ...config, [key]: numValue });
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen neural-grid flex items-center justify-center">
        <div className="w-16 h-16 border-4 border-cyan-500/30 border-t-cyan-500 rounded-full animate-spin" />
      </div>
    );
  }

  if (!config) {
    return (
      <div className="min-h-screen neural-grid flex items-center justify-center">
        <p className="text-red-400">加载配置失败</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen neural-grid">
      <header className="px-8 py-6 border-b border-neural-border">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="3" />
                <path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83" />
              </svg>
            </div>
            <div>
              <h1 className="text-xl font-bold text-white font-space">设置</h1>
              <p className="text-sm text-slate-400 font-chinese">参数配置 · 算法原理 · 系统监控</p>
            </div>
          </div>
          <button
            onClick={handleReset}
            disabled={resetting}
            className="px-4 py-2 text-sm text-slate-400 hover:text-white border border-neural-border rounded-lg hover:bg-neural-card-hover transition-all disabled:opacity-50"
          >
            {resetting ? '重置中...' : '重置默认'}
          </button>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-8 py-6">
        {message && (
          <div className={`mb-6 px-4 py-3 rounded-lg text-sm ${message.type === 'success' ? 'bg-green-500/20 text-green-400 border border-green-500/30' : 'bg-red-500/20 text-red-400 border border-red-500/30'}`}>
            {message.text}
          </div>
        )}

        <div className="grid grid-cols-4 gap-4 mb-6">
          <StatCard
            title="总记忆数"
            value={memoryStats?.total || 0}
            icon={<span className="text-2xl">🧠</span>}
            color="#00d4ff"
          />
          <StatCard
            title="关联边数"
            value={edgeStats?.total || 0}
            icon={<span className="text-2xl">🔗</span>}
            color="#a855f7"
          />
          <StatCard
            title="社区簇数"
            value={monitorData?.cluster.cluster_count || 0}
            icon={<span className="text-2xl">📊</span>}
            color="#22c55e"
          />
          <StatCard
            title="7日新增"
            value={memoryStats?.recent_7days || 0}
            icon={<span className="text-2xl">📈</span>}
            color="#f97316"
          />
        </div>

        <div className="flex gap-2 mb-6">
          {[
            { key: 'config' as const, label: '参数配置', icon: '⚙' },
            { key: 'algorithm' as const, label: '算法原理', icon: '🧬' },
            { key: 'monitor' as const, label: '系统监控', icon: '📡' },
          ].map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                activeTab === tab.key
                  ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30'
                  : 'text-slate-400 hover:text-white border border-transparent hover:bg-neural-card'
              }`}
            >
              <span className="mr-1">{tab.icon}</span>
              {tab.label}
            </button>
          ))}
        </div>

        {activeTab === 'config' && (
          <div className="bg-neural-card/50 border border-neural-border rounded-2xl p-6">
            <h2 className="text-lg font-bold text-white mb-6 font-space">运行时参数</h2>
            <div className="grid grid-cols-2 gap-6">
              {PARAM_DESCRIPTIONS.map((param) => (
                <div key={param.key} className="space-y-2">
                  <label className="block">
                    <span className="text-sm font-medium text-cyan-400">{param.name}</span>
                  </label>
                  <p className="text-xs text-slate-400">{param.description}</p>
                  <input
                    type="number"
                    value={config[param.key as keyof Config]}
                    onChange={(e) => handleChange(param.key as keyof Config, e.target.value)}
                    min={0}
                    className="w-full px-4 py-2.5 bg-neural-bg border border-neural-border rounded-lg text-white text-sm focus:outline-none focus:border-cyan-500 transition-colors"
                  />
                  <code className="block text-xs text-slate-500 bg-neural-bg/50 px-2 py-1 rounded">
                    {param.formula}
                  </code>
                  <p className="text-xs text-slate-500">{param.detail}</p>
                </div>
              ))}
            </div>
            <div className="mt-8 flex justify-end">
              <button
                onClick={handleSave}
                disabled={saving}
                className="px-6 py-2.5 bg-gradient-to-r from-cyan-500 to-blue-500 text-white text-sm font-medium rounded-lg hover:from-cyan-400 hover:to-blue-400 transition-all disabled:opacity-50"
              >
                {saving ? '保存中...' : '保存配置'}
              </button>
            </div>
          </div>
        )}

        {activeTab === 'algorithm' && (
          <div className="space-y-6">
            <div className="bg-neural-card/50 border border-neural-border rounded-2xl p-6">
              <h2 className="text-lg font-bold text-white mb-4 font-space flex items-center gap-2">
                <span className="text-cyan-400">01</span> 记忆召回权重计算
              </h2>
              <p className="text-sm text-slate-400 mb-4">
                系统通过多维度加权评分决定哪些记忆被召回。每条记忆的得分由基础权重、时间衰减、Key 偏好倍数和价值评估共同决定。
              </p>
              <div className="space-y-3">
                <div>
                  <h3 className="text-cyan-400 font-medium mb-2 text-sm">综合权重公式</h3>
                  <code className="block bg-neural-bg/50 px-4 py-3 rounded-lg text-slate-300 font-mono text-xs overflow-x-auto">
                    weight = base_weight × time_decay × key_multiplier × value_bonus
                  </code>
                </div>
                <div>
                  <h3 className="text-cyan-400 font-medium mb-2 text-sm">时间衰减 (指数衰减)</h3>
                  <code className="block bg-neural-bg/50 px-4 py-3 rounded-lg text-slate-300 font-mono text-xs overflow-x-auto">
                    time_decay = e^(-λ × days_since_last_access)
                  </code>
                  <p className="text-xs text-slate-500 mt-1">λ 为衰减速率，最近访问的记忆衰减更慢</p>
                </div>
                <div>
                  <h3 className="text-cyan-400 font-medium mb-2 text-sm">Key 偏好倍数</h3>
                  <code className="block bg-neural-bg/50 px-4 py-3 rounded-lg text-slate-300 font-mono text-xs overflow-x-auto">
                    health=1.5, study=1.3, preference=1.2, relationship=1.1, other=1.0
                  </code>
                  <p className="text-xs text-slate-500 mt-1">不同 Key 类型有不同的优先级，由 PreferenceTracker 动态学习调整</p>
                </div>
                <div>
                  <h3 className="text-cyan-400 font-medium mb-2 text-sm">最终得分</h3>
                  <code className="block bg-neural-bg/50 px-4 py-3 rounded-lg text-slate-300 font-mono text-xs overflow-x-auto">
                    score = weight × (1 + recall_count × 0.1)
                  </code>
                  <p className="text-xs text-slate-500 mt-1">被频繁召回的记忆会获得额外加成，形成"越用越重要"的正反馈</p>
                </div>
              </div>
            </div>

            <div className="bg-neural-card/50 border border-neural-border rounded-2xl p-6">
              <h2 className="text-lg font-bold text-white mb-4 font-space flex items-center gap-2">
                <span className="text-purple-400">02</span> 关联建边机制
              </h2>
              <p className="text-sm text-slate-400 mb-4">
                当新记忆存入时，系统会自动与已有记忆建立关联边。分为同Key建边和跨Key关联两个阶段。
              </p>
              <div className="space-y-3">
                <div>
                  <h3 className="text-purple-400 font-medium mb-2 text-sm">同Key建边 (KeyEdgeBuilderAgent)</h3>
                  <code className="block bg-neural-bg/50 px-4 py-3 rounded-lg text-slate-300 font-mono text-xs overflow-x-auto">
                    strength = semantic_similarity(content_new, content_existing) × recency_bonus
                  </code>
                  <p className="text-xs text-slate-500 mt-1">同一分类下的记忆通过语义相似度建立关联，近期记忆权重更高</p>
                </div>
                <div>
                  <h3 className="text-purple-400 font-medium mb-2 text-sm">跨Key关联 (CrossKeyAssocAgent)</h3>
                  <code className="block bg-neural-bg/50 px-4 py-3 rounded-lg text-slate-300 font-mono text-xs overflow-x-auto">
                    cross_strength = entity_overlap × temporal_proximity × contextual_relevance
                  </code>
                  <p className="text-xs text-slate-500 mt-1">跨分类关联通过实体重叠、时间邻近和上下文相关性综合计算</p>
                </div>
                <div>
                  <h3 className="text-purple-400 font-medium mb-2 text-sm">边校准 (EdgeCalibrator)</h3>
                  <code className="block bg-neural-bg/50 px-4 py-3 rounded-lg text-slate-300 font-mono text-xs overflow-x-auto">
                    effective_strength = base_strength × (1 + hit_count × 0.05) × decay_factor
                  </code>
                  <p className="text-xs text-slate-500 mt-1">边的有效强度会根据实际召回命中次数动态调整，被频繁使用的关联会增强</p>
                </div>
              </div>
            </div>

            <div className="bg-neural-card/50 border border-neural-border rounded-2xl p-6">
              <h2 className="text-lg font-bold text-white mb-4 font-space flex items-center gap-2">
                <span className="text-emerald-400">03</span> 价值评估系统
              </h2>
              <p className="text-sm text-slate-400 mb-4">
                每条记忆都有独立的 value_score，由 ValueAssessor 在存储时评估。分数影响召回优先级和可视化中的节点大小。
              </p>
              <div className="space-y-3">
                <div>
                  <h3 className="text-emerald-400 font-medium mb-2 text-sm">价值评估维度</h3>
                  <code className="block bg-neural-bg/50 px-4 py-3 rounded-lg text-slate-300 font-mono text-xs overflow-x-auto">
                    value_score = f(specificity, actionability, emotional_weight, uniqueness)
                  </code>
                  <ul className="text-xs text-slate-400 mt-2 space-y-1 ml-4 list-disc">
                    <li>specificity: 信息具体程度，越具体分数越高</li>
                    <li>actionability: 可执行性，包含行动计划的记忆更重要</li>
                    <li>emotional_weight: 情感权重，带有强烈情感的记忆优先保留</li>
                    <li>uniqueness: 独特性，与已有记忆重复度低的获得更高分数</li>
                  </ul>
                </div>
              </div>
            </div>

            <div className="bg-neural-card/50 border border-neural-border rounded-2xl p-6">
              <h2 className="text-lg font-bold text-white mb-4 font-space flex items-center gap-2">
                <span className="text-orange-400">04</span> Agent 协作架构
              </h2>
              <p className="text-sm text-slate-400 mb-4">
                系统采用多Agent协作架构，每个Agent专注特定任务，通过工具调用实现记忆的全生命周期管理。
              </p>
              <div className="grid grid-cols-2 gap-4">
                {[
                  { name: 'RoutingAgent', color: '#3B82F6', desc: '判断消息是否值得记忆，通过Key摘要匹配分配到最相关的分类' },
                  { name: 'KeyDecisionAgent', color: '#22C55E', desc: '审核候选记忆：新增、替换已有记忆、驳回或标记重复' },
                  { name: 'KeyEdgeBuilderAgent', color: '#F97316', desc: '为新记忆与同Key下已有记忆建立语义关联边' },
                  { name: 'CrossKeyAssocAgent', color: '#A855F7', desc: '发现跨分类的隐性关联，建立跨域知识连接' },
                  { name: 'DialogueAgent', color: '#06B6D4', desc: '召回相关记忆、组装上下文、生成回复、上报引用命中' },
                  { name: 'CompressionAgent', color: '#6B7280', desc: '上下文超阈值时执行对话压缩，保留关键信息' },
                ].map(agent => (
                  <div key={agent.name} className="p-3 bg-neural-bg/50 rounded-lg border border-neural-border">
                    <div className="flex items-center gap-2 mb-1">
                      <div className="w-2 h-2 rounded-full" style={{ backgroundColor: agent.color }} />
                      <span className="text-sm font-medium text-white">{agent.name}</span>
                    </div>
                    <p className="text-xs text-slate-400">{agent.desc}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'monitor' && (
          <div className="space-y-6">
            <div className="bg-neural-card/50 border border-neural-border rounded-2xl p-6">
              <h2 className="text-lg font-bold text-white mb-4 font-space">系统运行状态</h2>
              {monitorData ? (
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-4 bg-neural-bg/50 rounded-lg">
                    <h3 className="text-sm font-medium text-cyan-400 mb-2">当前实例</h3>
                    <p className="text-lg font-bold text-white">{monitorData.instance}</p>
                  </div>
                  <div className="p-4 bg-neural-bg/50 rounded-lg">
                    <h3 className="text-sm font-medium text-purple-400 mb-2">社区簇</h3>
                    <p className="text-lg font-bold text-white">{monitorData.cluster.cluster_count} 簇 / {monitorData.cluster.memory_count} 记忆</p>
                  </div>
                  <div className="p-4 bg-neural-bg/50 rounded-lg">
                    <h3 className="text-sm font-medium text-emerald-400 mb-2">偏好追踪</h3>
                    <p className="text-lg font-bold text-white">{monitorData.preference.total_calls} 次调用</p>
                    {Object.keys(monitorData.preference.keys || {}).length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {Object.entries(monitorData.preference.keys).slice(0, 5).map(([key, count]) => (
                          <span key={key} className="px-2 py-0.5 bg-emerald-500/15 text-emerald-400 rounded text-xs">
                            {key}: {count as number}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="p-4 bg-neural-bg/50 rounded-lg">
                    <h3 className="text-sm font-medium text-orange-400 mb-2">对话记录</h3>
                    <p className="text-lg font-bold text-white">{monitorData.sub.total} 条</p>
                    <p className="text-xs text-slate-500">近7天: {monitorData.sub.recent_7days}</p>
                  </div>
                </div>
              ) : (
                <p className="text-slate-400">暂无监控数据</p>
              )}
            </div>

            {memoryStats && (
              <div className="bg-neural-card/50 border border-neural-border rounded-2xl p-6">
                <h2 className="text-lg font-bold text-white mb-4 font-space">记忆分布</h2>
                <div className="grid grid-cols-2 gap-6">
                  <div>
                    <h3 className="text-sm font-medium text-slate-300 mb-3">按Key分类</h3>
                    <div className="space-y-2">
                      {Object.entries(memoryStats.by_key).map(([key, count]) => (
                        <div key={key} className="flex items-center gap-2">
                          <span className="text-xs text-slate-400 w-24 truncate">{key}</span>
                          <div className="flex-1 h-4 bg-neural-bg rounded-full overflow-hidden">
                            <div
                              className="h-full bg-cyan-500/60 rounded-full transition-all"
                              style={{ width: `${memoryStats.total > 0 ? (count / memoryStats.total) * 100 : 0}%` }}
                            />
                          </div>
                          <span className="text-xs text-slate-400 w-8 text-right">{count}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div>
                    <h3 className="text-sm font-medium text-slate-300 mb-3">价值分分布</h3>
                    <div className="space-y-2">
                      {Object.entries(memoryStats.value_distribution || {}).map(([bucket, count]) => (
                        <div key={bucket} className="flex items-center gap-2">
                          <span className="text-xs text-slate-400 w-16">{bucket}</span>
                          <div className="flex-1 h-4 bg-neural-bg rounded-full overflow-hidden">
                            <div
                              className="h-full bg-purple-500/60 rounded-full transition-all"
                              style={{ width: `${memoryStats.total > 0 ? (count as number / memoryStats.total) * 100 : 0}%` }}
                            />
                          </div>
                          <span className="text-xs text-slate-400 w-8 text-right">{count as number}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {edgeStats && (
              <div className="bg-neural-card/50 border border-neural-border rounded-2xl p-6">
                <h2 className="text-lg font-bold text-white mb-4 font-space">关联边统计</h2>
                <div className="grid grid-cols-3 gap-4 mb-4">
                  <div className="p-3 bg-neural-bg/50 rounded-lg text-center">
                    <p className="text-xs text-slate-500">总边数</p>
                    <p className="text-xl font-bold text-white">{edgeStats.total}</p>
                  </div>
                  <div className="p-3 bg-neural-bg/50 rounded-lg text-center">
                    <p className="text-xs text-slate-500">平均强度</p>
                    <p className="text-xl font-bold text-cyan-400">{edgeStats.avg_strength}</p>
                  </div>
                  <div className="p-3 bg-neural-bg/50 rounded-lg text-center">
                    <p className="text-xs text-slate-500">平均有效强度</p>
                    <p className="text-xl font-bold text-purple-400">{edgeStats.avg_effective_strength}</p>
                  </div>
                </div>
                {edgeStats.top_by_hits && edgeStats.top_by_hits.length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium text-slate-300 mb-2">Top 命中边</h3>
                    <div className="space-y-1">
                      {edgeStats.top_by_hits.slice(0, 5).map((edge, i) => (
                        <div key={i} className="flex items-center gap-2 text-xs text-slate-400 p-2 bg-neural-bg/30 rounded">
                          <span className="text-cyan-400 w-4">{i + 1}</span>
                          <span className="truncate">{edge.source.slice(0, 8)} → {edge.target.slice(0, 8)}</span>
                          <span className="text-slate-500">hits: {edge.hit_count}</span>
                          <span className="text-slate-500">strength: {edge.effective_strength}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
