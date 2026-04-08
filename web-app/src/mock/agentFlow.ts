// AgentFlow 模拟数据

export type AgentType =
  | 'RoutingAgent'
  | 'KeyDecisionAgent'
  | 'KeyEdgeBuilderAgent'
  | 'CrossKeyAssocAgent'
  | 'CompressionAgent'
  | 'DialogueAgent';

export type AgentStatus = 'idle' | 'working' | 'completed' | 'error';

export interface AgentConfig {
  type: AgentType;
  color: string;
  label: string;
  description: string;
  tools: string[];
}

export interface AgentEvent {
  id: string;
  timestamp: string;
  agentType: AgentType;
  agentLabel: string;
  agentColor: string;
  direction: 'call' | 'return' | 'error';
  toolName: string;
  params?: string;
  result?: string;
  duration?: number;
}

export const AGENTS: AgentConfig[] = [
  {
    type: 'RoutingAgent',
    color: '#3B82F6',
    label: '路由Agent',
    description: '判断消息是否值得记忆，分配到哪个Key',
    tools: ['get_key_summaries', 'assign_memory_to_keys'],
  },
  {
    type: 'KeyDecisionAgent',
    color: '#22C55E',
    label: '记忆审核',
    description: '新增 / 替换 / 驳回 / 标记重复',
    tools: ['add_memory_to_key', 'replace_memory_in_key', 'reject_candidate', 'mark_duplicate'],
  },
  {
    type: 'KeyEdgeBuilderAgent',
    color: '#F97316',
    label: '同Key建边',
    description: '与同Key已有记忆建立关联边',
    tools: ['build_edges'],
  },
  {
    type: 'CrossKeyAssocAgent',
    color: '#A855F7',
    label: '跨Key关联',
    description: '与其他Key下的记忆建立跨域关联',
    tools: ['create_edges'],
  },
  {
    type: 'CompressionAgent',
    color: '#6B7280',
    label: '对话压缩',
    description: '上下文超阈值时压缩对话历史',
    tools: [],
  },
  {
    type: 'DialogueAgent',
    color: '#06B6D4',
    label: '对话管理',
    description: '召回记忆、生成回复、引用上报',
    tools: ['recall_from_key', 'add_to_memory_space', 'remove_from_memory_space', 'update_memory_space', 'report_hits'],
  },
];

// 完整的Agent事件流
export const mockAgentEvents: AgentEvent[] = [
  {
    id: '1',
    timestamp: '14:32:01',
    agentType: 'RoutingAgent',
    agentLabel: '路由Agent',
    agentColor: '#3B82F6',
    direction: 'call',
    toolName: 'get_key_summaries',
    params: '{}',
  },
  {
    id: '2',
    timestamp: '14:32:01',
    agentType: 'RoutingAgent',
    agentLabel: '路由Agent',
    agentColor: '#3B82F6',
    direction: 'return',
    toolName: 'get_key_summaries',
    result: '返回9个Key的摘要',
    duration: 234,
  },
  {
    id: '3',
    timestamp: '14:32:02',
    agentType: 'RoutingAgent',
    agentLabel: '路由Agent',
    agentColor: '#3B82F6',
    direction: 'call',
    toolName: 'assign_memory_to_keys',
    params: '{"candidates":[{"content":"考研目标北大计算机","key":"study","importance":0.9}]}',
  },
  {
    id: '4',
    timestamp: '14:32:02',
    agentType: 'RoutingAgent',
    agentLabel: '路由Agent',
    agentColor: '#3B82F6',
    direction: 'return',
    toolName: 'assign_memory_to_keys',
    result: '分配1条待审核记忆 → study',
    duration: 456,
  },
  {
    id: '5',
    timestamp: '14:32:03',
    agentType: 'KeyDecisionAgent',
    agentLabel: '记忆审核',
    agentColor: '#22C55E',
    direction: 'call',
    toolName: 'add_memory_to_key',
    params: '{"key":"study","content":"考研目标北大计算机","importance_score":0.85}',
  },
  {
    id: '6',
    timestamp: '14:32:03',
    agentType: 'KeyDecisionAgent',
    agentLabel: '记忆审核',
    agentColor: '#22C55E',
    direction: 'return',
    toolName: 'add_memory_to_key',
    result: '✓ 新增 fingerprint=fp021',
    duration: 789,
  },
  {
    id: '7',
    timestamp: '14:32:04',
    agentType: 'KeyDecisionAgent',
    agentLabel: '记忆审核',
    agentColor: '#22C55E',
    direction: 'call',
    toolName: 'build_edges',
    params: '{"fingerprint":"fp021","key":"study"}',
  },
  {
    id: '8',
    timestamp: '14:32:04',
    agentType: 'KeyDecisionAgent',
    agentLabel: '记忆审核',
    agentColor: '#22C55E',
    direction: 'return',
    toolName: 'build_edges',
    result: '创建3条同Key边 (fp001,fp002,fp011)',
    duration: 189,
  },
  {
    id: '9',
    timestamp: '14:32:05',
    agentType: 'CrossKeyAssocAgent',
    agentLabel: '跨Key关联',
    agentColor: '#A855F7',
    direction: 'call',
    toolName: 'create_cross_key_edges',
    params: '{"fingerprint":"fp021"}',
  },
  {
    id: '10',
    timestamp: '14:32:05',
    agentType: 'CrossKeyAssocAgent',
    agentLabel: '跨Key关联',
    agentColor: '#A855F7',
    direction: 'return',
    toolName: 'create_cross_key_edges',
    result: '创建1条跨Key边 → fp006(项目截止)',
    duration: 234,
  },
];

// Agent状态序列（用于动画）
export const agentStateSequence = [
  { RoutingAgent: 'completed', KeyDecisionAgent: 'completed', KeyEdgeBuilderAgent: 'completed', CrossKeyAssocAgent: 'completed', CompressionAgent: 'idle', DialogueAgent: 'idle' },
];

// 初始状态
export const initialAgentStates: Record<AgentType, AgentStatus> = {
  RoutingAgent: 'idle',
  KeyDecisionAgent: 'idle',
  KeyEdgeBuilderAgent: 'idle',
  CrossKeyAssocAgent: 'idle',
  CompressionAgent: 'idle',
  DialogueAgent: 'idle',
};
