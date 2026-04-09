// 记忆网络图的模拟数据

// 预设颜色池
export const KEY_COLOR_POOL: string[] = [
  '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7',
  '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#F093FB',
  '#00D9FF', '#FF9A9E', '#A8EDEA', '#FFECD2', '#D299C2',
  '#89F7FE', '#FDCBF1', '#E0C3FC', '#FDBB2D', '#5FC3E4',
];

// 根据Key名称获取颜色
export const getKeyColor = (keyName: string): string => {
  const hash = keyName.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
  return KEY_COLOR_POOL[hash % KEY_COLOR_POOL.length];
};

// 社区聚类颜色池
export const CLUSTER_COLOR_POOL = [
  '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7',
  '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#F093FB',
  '#00D9FF', '#FF9A9E', '#A8EDEA', '#FFECD2', '#D299C2',
  '#89F7FE', '#FDCBF1', '#E0C3FC', '#FDBB2D', '#5FC3E4',
  '#FF8A65', '#A1887F', '#90A4AE', '#80CBC4', '#B39DDB',
];

// 根据社区ID获取颜色
export const getClusterColor = (clusterId: string): string => {
  if (clusterId === 'unclustered') return '#666666';
  const hash = clusterId.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
  return CLUSTER_COLOR_POOL[hash % CLUSTER_COLOR_POOL.length];
};

// 获取节点大小
export const getNodeSize = (valueScore: number) => {
  // 范围: 0.45 -> 4, 0.95 -> 10
  return valueScore * 7 + 2;
};

// 获取边粗细
export const getLinkWidth = (effectiveStrength: number) => effectiveStrength * 3;

// 节点类型
export interface GraphNode {
  id: string;
  key: string;
  tag: string;
  summary_item: string;
  memory: string;
  value_score: number;
  recall_count: number;
  created_at?: string;
}

// 边类型
export interface GraphLink {
  source: string;
  target: string;
  strength: number;
  effective_strength: number;
  reason: string;
}

// 图数据
export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
  stats: {
    nodes_count: number;
    links_count: number;
    avg_connections: number;
  };
}

// 模拟数据
export const mockGraphData: GraphData = {
  nodes: [
    { id: 'fp001', key: 'study', tag: '考研计划启动', summary_item: '考研计划启动', memory: '2026-04-01开始准备考研，目标北大计算机，每天学习8小时', value_score: 0.95, recall_count: 12 },
    { id: 'fp002', key: 'study', tag: '作息计划', summary_item: '作息计划', memory: '每天早上7点起床学习，晚上11点休息', value_score: 0.80, recall_count: 8 },
    { id: 'fp003', key: 'study', tag: '考研资料购买', summary_item: '买了高数资料', memory: '买了高数辅导书和政治资料', value_score: 0.65, recall_count: 5 },
    { id: 'fp004', key: 'health', tag: '晨跑习惯', summary_item: '每天晨跑30分钟', memory: '每天早上跑步30分钟，保持身体健康', value_score: 0.75, recall_count: 6 },
    { id: 'fp005', key: 'preference', tag: '喜欢吃苹果', summary_item: '最喜欢吃苹果', memory: '水果里最喜欢苹果，每天都要吃一个', value_score: 0.60, recall_count: 4 },
    { id: 'fp006', key: 'work', tag: '项目截止日期', summary_item: '项目截止4月15日', memory: '项目截止日期是4月15日，必须在此之前完成', value_score: 0.85, recall_count: 7 },
    { id: 'fp007', key: 'project', tag: '记忆助手开发', summary_item: '记忆助手项目开发中', memory: '正在开发一个记忆助手项目，使用React前端', value_score: 0.72, recall_count: 5 },
    { id: 'fp008', key: 'code', tag: 'TypeScript学习', summary_item: 'TypeScript类型系统', memory: '最近在用TypeScript写项目，感觉类型系统很好用', value_score: 0.65, recall_count: 3 },
    { id: 'fp009', key: 'schedule', tag: '每周会议', summary_item: '周三下午会议', memory: '每周三下午2点有团队会议', value_score: 0.70, recall_count: 6 },
    { id: 'fp010', key: 'relationship', tag: '周末聚会', summary_item: '周末和朋友吃饭', memory: '和老朋友约好周末一起吃饭', value_score: 0.55, recall_count: 2 },
    { id: 'fp011', key: 'study', tag: '英语复习', summary_item: '英语单词背诵', memory: '每天背诵50个英语单词', value_score: 0.60, recall_count: 4 },
    { id: 'fp012', key: 'study', tag: '数学进度', summary_item: '高数复习到第三章', memory: '高数已经复习到第三章了', value_score: 0.58, recall_count: 3 },
    { id: 'fp013', key: 'emotion', tag: '心情愉悦', summary_item: '今天心情好', memory: '今天心情很好，学习效率很高', value_score: 0.45, recall_count: 1 },
    { id: 'fp014', key: 'work', tag: '代码审查', summary_item: '周五代码审查', memory: '周五要进行代码审查会议', value_score: 0.50, recall_count: 2 },
    { id: 'fp015', key: 'health', tag: '午休习惯', summary_item: '每天午休30分钟', memory: '每天中午休息30分钟保持精力', value_score: 0.52, recall_count: 2 },
    { id: 'fp016', key: 'preference', tag: '咖啡爱好者', summary_item: '喜欢喝咖啡', memory: '每天早上都要喝一杯咖啡', value_score: 0.48, recall_count: 3 },
    { id: 'fp017', key: 'study', tag: '政治复习', summary_item: '政治开始复习', memory: '政治复习开始了，看马哲部分', value_score: 0.55, recall_count: 2 },
    { id: 'fp018', key: 'project', tag: '前端架构', summary_item: '前端技术选型', memory: '前端使用React+TypeScript架构', value_score: 0.68, recall_count: 4 },
    { id: 'fp019', key: 'code', tag: 'Git使用', summary_item: 'Git工作流', memory: '项目使用Git进行版本控制', value_score: 0.55, recall_count: 3 },
    { id: 'fp020', key: 'schedule', tag: '清明假期', summary_item: '清明节计划', memory: '清明节假期准备回家', value_score: 0.50, recall_count: 1 },
  ],

  links: [
    { source: 'fp001', target: 'fp002', strength: 0.9, effective_strength: 0.88, reason: '同一考研计划' },
    { source: 'fp001', target: 'fp003', strength: 0.9, effective_strength: 0.85, reason: '考研准备' },
    { source: 'fp002', target: 'fp003', strength: 0.6, effective_strength: 0.58, reason: '相关复习' },
    { source: 'fp001', target: 'fp011', strength: 0.9, effective_strength: 0.82, reason: '考研英语' },
    { source: 'fp001', target: 'fp012', strength: 0.9, effective_strength: 0.80, reason: '考研数学' },
    { source: 'fp001', target: 'fp017', strength: 0.9, effective_strength: 0.78, reason: '考研政治' },
    { source: 'fp006', target: 'fp007', strength: 0.9, effective_strength: 0.85, reason: '项目开发' },
    { source: 'fp007', target: 'fp008', strength: 0.9, effective_strength: 0.88, reason: '技术栈相关' },
    { source: 'fp007', target: 'fp018', strength: 0.6, effective_strength: 0.55, reason: '项目前端' },
    { source: 'fp008', target: 'fp018', strength: 0.9, effective_strength: 0.86, reason: 'TypeScript' },
    { source: 'fp008', target: 'fp019', strength: 0.6, effective_strength: 0.58, reason: '开发实践' },
    { source: 'fp004', target: 'fp015', strength: 0.9, effective_strength: 0.82, reason: '健康习惯' },
    { source: 'fp005', target: 'fp016', strength: 0.9, effective_strength: 0.78, reason: '日常习惯' },
    { source: 'fp006', target: 'fp014', strength: 0.6, effective_strength: 0.55, reason: '工作安排' },
    { source: 'fp009', target: 'fp014', strength: 0.9, effective_strength: 0.80, reason: '会议相关' },
    { source: 'fp001', target: 'fp004', strength: 0.3, effective_strength: 0.28, reason: '考研期间保持健康' },
    { source: 'fp007', target: 'fp009', strength: 0.3, effective_strength: 0.25, reason: '时间管理' },
    { source: 'fp008', target: 'fp011', strength: 0.3, effective_strength: 0.22, reason: '英语编程' },
    { source: 'fp004', target: 'fp013', strength: 0.6, effective_strength: 0.52, reason: '健康影响心情' },
    { source: 'fp010', target: 'fp020', strength: 0.6, effective_strength: 0.50, reason: '假期安排' },
    { source: 'fp011', target: 'fp017', strength: 0.6, effective_strength: 0.55, reason: '英语政治' },
    { source: 'fp012', target: 'fp003', strength: 0.6, effective_strength: 0.52, reason: '高数资料' },
    { source: 'fp018', target: 'fp019', strength: 0.6, effective_strength: 0.58, reason: 'Git协作' },
    { source: 'fp013', target: 'fp002', strength: 0.3, effective_strength: 0.25, reason: '好心情提高效率' },
  ],

  stats: {
    nodes_count: 20,
    links_count: 24,
    avg_connections: 2.4,
  },
};

// 所有Key列表
export const mockKeys = [
  { name: 'study', label: '学习', count: 7 },
  { name: 'health', label: '健康', count: 2 },
  { name: 'preference', label: '偏好', count: 2 },
  { name: 'work', label: '工作', count: 2 },
  { name: 'project', label: '项目', count: 2 },
  { name: 'code', label: '代码', count: 2 },
  { name: 'schedule', label: '日程', count: 2 },
  { name: 'relationship', label: '关系', count: 1 },
  { name: 'emotion', label: '情绪', count: 1 },
];
