// 统计仪表盘的模拟数据

export const mockMemoryStats = {
  total: 128,
  by_key: {
    preference: 25,
    schedule: 15,
    work: 32,
    study: 35,
    health: 8,
    emotion: 5,
    relationship: 3,
    project: 3,
    code: 2,
  },
  recall_distribution: {
    '0': 20,
    '1-5': 45,
    '6-10': 35,
    '10+': 28,
  },
  value_distribution: {
    '0-0.2': 8,
    '0.2-0.4': 15,
    '0.4-0.6': 45,
    '0.6-0.8': 40,
    '0.8-1.0': 20,
  },
  recent_7days: 18,
  semantic_status: {
    valid: 120,
    invalid: 5,
    expired: 3,
  },
  top_recalled: [
    {
      fingerprint: 'fp001',
      key: 'study',
      tag: '考研计划启动',
      recall_count: 12,
      value_score: 0.95,
      last_recall_at: '2026-04-06T09:30:00',
    },
    {
      fingerprint: 'fp002',
      key: 'preference',
      tag: '喜欢吃苹果',
      recall_count: 8,
      value_score: 0.88,
      last_recall_at: '2026-04-06T08:15:00',
    },
    {
      fingerprint: 'fp003',
      key: 'health',
      tag: '每天跑步30分钟',
      recall_count: 6,
      value_score: 0.82,
      last_recall_at: '2026-04-05T19:00:00',
    },
    {
      fingerprint: 'fp004',
      key: 'work',
      tag: '项目截止日期',
      recall_count: 5,
      value_score: 0.79,
      last_recall_at: '2026-04-05T14:00:00',
    },
    {
      fingerprint: 'fp005',
      key: 'schedule',
      tag: '每周会议',
      recall_count: 4,
      value_score: 0.75,
      last_recall_at: '2026-04-04T10:00:00',
    },
  ],
};

export const mockEdgeStats = {
  total: 356,
  clusters_count: 45,
  by_strength: {
    '0.9': 107,
    '0.6': 160,
    '0.3': 89,
  },
  avg_effective_strength: 0.62,
};

// Key颜色池（与SPEC一致）
export const KEY_COLOR_POOL: string[] = [
  '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7',
  '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#F093FB',
  '#00D9FF', '#FF9A9E', '#A8EDEA', '#FFECD2', '#D299C2',
  '#89F7FE', '#FDCBF1', '#E0C3FC', '#FDBB2D', '#5FC3E4',
];

export const getKeyColor = (keyName: string): string => {
  const hash = keyName.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
  return KEY_COLOR_POOL[hash % KEY_COLOR_POOL.length];
};
