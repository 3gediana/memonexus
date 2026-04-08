// 模拟对话数据

export interface RecallBlock {
  fingerprint: string;
  key: string;
  tag: string;
  memory: string;
  created_at: string;
  recall_count: number;
}

export interface StorageResult {
  action: 'added' | 'updated' | 'duplicate' | 'rejected';
  key: string;
  fingerprint: string;
  tag: string;
  memory?: string;
}

export interface DialogueTurn {
  turn: number;
  role: 'user' | 'assistant';
  content: string;
  recall_blocks?: RecallBlock[];
  storage_result?: StorageResult; // 只有存储了记忆才出现
}

// Agent事件类型
export interface AgentEvent {
  id: string;
  timestamp: string;
  agentLabel: string;
  agentColor: string;
  direction: 'call' | 'return' | 'error';
  toolName: string;
  params?: string;
  result?: string;
  duration?: number;
}

// 对话历史 - 只有第1轮触发了存储，第2轮没有
export const mockDialogueHistory: DialogueTurn[] = [
  {
    turn: 1,
    role: 'user',
    content: '我最近开始准备考研了，目标北大计算机',
  },
  {
    turn: 1,
    role: 'assistant',
    content: '好的，我已经记下了你的考研计划。目标北大计算机专业，这是一个很有挑战性的目标，加油！不过我注意到你之前提到的项目截止日期，别忘了时间管理哦。',
    recall_blocks: [
      {
        fingerprint: 'fp001',
        key: 'study',
        tag: '考研计划启动',
        memory: '2026-04-01开始准备考研，目标北大计算机，每天学习8小时',
        created_at: '2026-04-01T10:00:00',
        recall_count: 12,
      },
      {
        fingerprint: 'fp004',
        key: 'health',
        tag: '晨跑习惯',
        memory: '每天早上跑步30分钟，保持身体健康',
        created_at: '2026-04-03T06:30:00',
        recall_count: 6,
      },
    ],
    // 第1轮对话触发了存储：用户提到了"考研"这个新主题
  },
  {
    turn: 2,
    role: 'user',
    content: '今天心情不错',
  },
  {
    turn: 2,
    role: 'assistant',
    content: '太好了！保持好心情对学习效率很重要。有什么开心的事吗？',
    recall_blocks: [
      {
        fingerprint: 'fp013',
        key: 'emotion',
        tag: '心情愉悦',
        memory: '今天心情很好，学习效率很高',
        created_at: '2026-04-05T20:00:00',
        recall_count: 2,
      },
    ],
    // 第2轮对话没有触发存储，只是情绪表达
  },
];

// 第1轮触发存储时的事件流
export const mockAgentEventsTurn1: AgentEvent[] = [
  {
    id: '1',
    timestamp: '14:32:01',
    agentLabel: 'RoutingAgent',
    agentColor: '#3B82F6',
    direction: 'call',
    toolName: 'get_key_summaries',
    params: '{}',
  },
  {
    id: '2',
    timestamp: '14:32:01',
    agentLabel: 'RoutingAgent',
    agentColor: '#3B82F6',
    direction: 'return',
    toolName: 'get_key_summaries',
    result: '返回9个Key摘要',
    duration: 234,
  },
  {
    id: '3',
    timestamp: '14:32:02',
    agentLabel: 'RoutingAgent',
    agentColor: '#3B82F6',
    direction: 'call',
    toolName: 'assign_memory_to_keys',
    params: '{"candidates":[{"content":"考研目标北大计算机","key":"study","importance":0.9}]}',
  },
  {
    id: '4',
    timestamp: '14:32:02',
    agentLabel: 'RoutingAgent',
    agentColor: '#3B82F6',
    direction: 'return',
    toolName: 'assign_memory_to_keys',
    result: '分配1条待审核记忆 → study',
    duration: 456,
  },
  {
    id: '5',
    timestamp: '14:32:03',
    agentLabel: 'KeyAgent',
    agentColor: '#22C55E',
    direction: 'call',
    toolName: 'add_memory_to_key',
    params: '{"key":"study","content":"考研目标北大计算机","importance_score":0.85}',
  },
  {
    id: '6',
    timestamp: '14:32:03',
    agentLabel: 'KeyAgent',
    agentColor: '#22C55E',
    direction: 'return',
    toolName: 'add_memory_to_key',
    result: '✓ 新增 fingerprint=fp021',
    duration: 789,
  },
  {
    id: '7',
    timestamp: '14:32:04',
    agentLabel: 'KeyAgent',
    agentColor: '#22C55E',
    direction: 'call',
    toolName: 'build_edges',
    params: '{"fingerprint":"fp021","key":"study"}',
  },
  {
    id: '8',
    timestamp: '14:32:04',
    agentLabel: 'KeyAgent',
    agentColor: '#22C55E',
    direction: 'return',
    toolName: 'build_edges',
    result: '创建3条同Key边 (fp001,fp002,fp011)',
    duration: 189,
  },
  {
    id: '9',
    timestamp: '14:32:05',
    agentLabel: 'AssociationAgent',
    agentColor: '#A855F7',
    direction: 'call',
    toolName: 'create_cross_key_edges',
    params: '{"fingerprint":"fp021"}',
  },
  {
    id: '10',
    timestamp: '14:32:05',
    agentLabel: 'AssociationAgent',
    agentColor: '#A855F7',
    direction: 'return',
    toolName: 'create_cross_key_edges',
    result: '创建1条跨Key边 → fp006(项目截止)',
    duration: 234,
  },
];

// 第2轮没有触发存储的事件流（只是对话召回）
export const mockAgentEventsTurn2: AgentEvent[] = [
  {
    id: '1',
    timestamp: '14:35:01',
    agentLabel: 'DialogueAgent',
    agentColor: '#06B6D4',
    direction: 'call',
    toolName: 'recall_from_key',
    params: '{"query":"心情 情绪","top_n":5}',
  },
  {
    id: '2',
    timestamp: '14:35:01',
    agentLabel: 'DialogueAgent',
    agentColor: '#06B6D4',
    direction: 'return',
    toolName: 'recall_from_key',
    result: '召回2条: [fp013,fp001]',
    duration: 156,
  },
  {
    id: '3',
    timestamp: '14:35:02',
    agentLabel: 'DialogueAgent',
    agentColor: '#06B6D4',
    direction: 'call',
    toolName: 'report_hits',
    params: '{"fingerprints":["fp013","fp001"],"query":"心情"}',
  },
  {
    id: '4',
    timestamp: '14:35:02',
    agentLabel: 'DialogueAgent',
    agentColor: '#06B6D4',
    direction: 'return',
    toolName: 'report_hits',
    result: '命中计分完成',
    duration: 45,
  },
  // 第2轮 RoutingAgent 判断：无需存储
  {
    id: '5',
    timestamp: '14:35:03',
    agentLabel: 'RoutingAgent',
    agentColor: '#3B82F6',
    direction: 'call',
    toolName: 'analyze_for_storage',
    params: '{"content":"今天心情不错"}',
  },
  {
    id: '6',
    timestamp: '14:35:03',
    agentLabel: 'RoutingAgent',
    agentColor: '#3B82F6',
    direction: 'return',
    toolName: 'analyze_for_storage',
    result: '✗ 无需存储 (仅情绪表达)',
    duration: 123,
  },
];

// 预设回复模板
export const mockResponses: Array<{
  user: string;
  assistant: string;
  recall_blocks: RecallBlock[];
  storage_event?: AgentEvent[]; // 如果有存储，会附带事件流
  storage_result?: StorageResult; // 存储结果
}> = [
  {
    user: '今天早上跑了步',
    assistant: '很好！坚持运动对保持精力很重要。晨跑是个好习惯，坚持下去会有好效果的。',
    recall_blocks: [
      {
        fingerprint: 'fp004',
        key: 'health',
        tag: '晨跑习惯',
        memory: '每天早上跑步30分钟，保持身体健康',
        created_at: '2026-04-03T06:30:00',
        recall_count: 7,
      },
    ],
    storage_event: [
      {
        id: '1',
        timestamp: '14:38:01',
        agentLabel: 'RoutingAgent',
        agentColor: '#3B82F6',
        direction: 'call',
        toolName: 'analyze_for_storage',
        params: '{"content":"今天早上跑了步"}',
      },
      {
        id: '2',
        timestamp: '14:38:01',
        agentLabel: 'RoutingAgent',
        agentColor: '#3B82F6',
        direction: 'return',
        toolName: 'analyze_for_storage',
        result: '→ 分配至 health',
        duration: 89,
      },
      {
        id: '3',
        timestamp: '14:38:02',
        agentLabel: 'KeyAgent',
        agentColor: '#22C55E',
        direction: 'call',
        toolName: 'add_memory_to_key',
        params: '{"key":"health","content":"今天早上跑步","importance_score":0.7}',
      },
      {
        id: '4',
        timestamp: '14:38:02',
        agentLabel: 'KeyAgent',
        agentColor: '#22C55E',
        direction: 'return',
        toolName: 'add_memory_to_key',
        result: '✓ 新增 fingerprint=fp023',
        duration: 567,
      },
    ],
    storage_result: {
      action: 'added',
      key: 'health',
      fingerprint: 'fp023',
      tag: '晨跑记录',
      memory: '2026-04-06早上跑步',
    },
  },
  {
    user: '我最喜欢吃苹果',
    assistant: '记住了！苹果是很健康的水果。你喜欢吃苹果这个偏好我会帮你记住。',
    recall_blocks: [
      {
        fingerprint: 'fp005',
        key: 'preference',
        tag: '喜欢吃苹果',
        memory: '水果里最喜欢苹果，每天都要吃一个',
        created_at: '2026-04-02T08:00:00',
        recall_count: 9,
      },
    ],
    // 这次是重复记忆，RoutingAgent直接判定duplicate
    storage_event: [
      {
        id: '1',
        timestamp: '14:40:01',
        agentLabel: 'RoutingAgent',
        agentColor: '#3B82F6',
        direction: 'call',
        toolName: 'analyze_for_storage',
        params: '{"content":"我最喜欢吃苹果"}',
      },
      {
        id: '2',
        timestamp: '14:40:01',
        agentLabel: 'RoutingAgent',
        agentColor: '#3B82F6',
        direction: 'return',
        toolName: 'analyze_for_storage',
        result: '→ 分配至 preference',
        duration: 95,
      },
      {
        id: '3',
        timestamp: '14:40:02',
        agentLabel: 'KeyAgent',
        agentColor: '#22C55E',
        direction: 'call',
        toolName: 'check_duplicate',
        params: '{"key":"preference","content":"最喜欢吃苹果"}',
      },
      {
        id: '4',
        timestamp: '14:40:02',
        agentLabel: 'KeyAgent',
        agentColor: '#22C55E',
        direction: 'return',
        toolName: 'check_duplicate',
        result: '⚠ duplicate → fp005',
        duration: 234,
      },
    ],
    storage_result: {
      action: 'duplicate',
      key: 'preference',
      fingerprint: 'fp005',
      tag: '喜欢吃苹果',
    },
  },
  {
    user: '学习好累啊',
    assistant: '学习确实需要劳逸结合。适当休息一下，效率会更高的。我来帮你记录一下这个感受。',
    recall_blocks: [
      {
        fingerprint: 'fp001',
        key: 'study',
        tag: '考研计划启动',
        memory: '2026-04-01开始准备考研，目标北大计算机，每天学习8小时',
        created_at: '2026-04-01T10:00:00',
        recall_count: 14,
      },
      {
        fingerprint: 'fp013',
        key: 'emotion',
        tag: '心情愉悦',
        memory: '今天心情很好，学习效率很高',
        created_at: '2026-04-05T20:00:00',
        recall_count: 2,
      },
    ],
    // 状态更新：学习疲惫更新了情绪记忆
    storage_event: [
      {
        id: '1',
        timestamp: '14:42:01',
        agentLabel: 'RoutingAgent',
        agentColor: '#3B82F6',
        direction: 'call',
        toolName: 'analyze_for_storage',
        params: '{"content":"学习好累啊"}',
      },
      {
        id: '2',
        timestamp: '14:42:01',
        agentLabel: 'RoutingAgent',
        agentColor: '#3B82F6',
        direction: 'return',
        toolName: 'analyze_for_storage',
        result: '→ 分配至 emotion',
        duration: 78,
      },
      {
        id: '3',
        timestamp: '14:42:02',
        agentLabel: 'KeyAgent',
        agentColor: '#22C55E',
        direction: 'call',
        toolName: 'replace_memory_in_key',
        params: '{"key":"emotion","old_fp":"fp013","new_content":"学习疲惫","importance_score":0.6}',
      },
      {
        id: '4',
        timestamp: '14:42:02',
        agentLabel: 'KeyAgent',
        agentColor: '#22C55E',
        direction: 'return',
        toolName: 'replace_memory_in_key',
        result: '🔄 更新 fingerprint=fp024',
        duration: 456,
      },
    ],
    storage_result: {
      action: 'updated',
      key: 'emotion',
      fingerprint: 'fp024',
      tag: '学习疲惫',
      memory: '2026-04-06学习感到疲惫',
    },
  },
  {
    user: '晚饭吃什么好',
    assistant: '考研期间要注意营养均衡。建议吃些蛋白质丰富的食物，比如鱼、肉、蛋类，再配些蔬菜水果。你平时有什么喜欢的健康食谱吗？',
    recall_blocks: [],
    // 晚饭建议不涉及记忆，无需存储
    storage_event: [],
  },
];

// Key颜色
const KEY_COLORS: Record<string, string> = {
  study: '#3B82F6',
  health: '#10B981',
  preference: '#F59E0B',
  work: '#EF4444',
  project: '#8B5CF6',
  code: '#06B6D4',
  schedule: '#EC4899',
  relationship: '#F97316',
  emotion: '#A855F7',
};

export const getKeyColor = (key: string): string => KEY_COLORS[key] || '#6B7280';
