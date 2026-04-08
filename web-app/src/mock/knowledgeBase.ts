// 知识库的模拟数据

export interface KbDocument {
  fingerprint: string;
  path: string;
  size: number;
  indexed_at: string;
  chunks_count: number;
  status: 'pending' | 'indexed';
}

export interface KbChunk {
  id: string;
  text: string;
  index: number;
  start_pos: number;
  end_pos: number;
  block_type: 'paragraph' | 'code' | 'table' | 'formula' | 'heading' | 'mixed';
  heading_level: number;
  heading_text: string;
}

export const mockDocuments: KbDocument[] = [
  {
    fingerprint: 'doc001',
    path: 'D:/资料/考研资料.pdf',
    size: 2621440,
    indexed_at: '2026-04-05T10:00:00',
    chunks_count: 15,
    status: 'indexed',
  },
  {
    fingerprint: 'doc002',
    path: 'D:/资料/项目文档.md',
    size: 131072,
    indexed_at: '2026-04-04T15:30:00',
    chunks_count: 8,
    status: 'indexed',
  },
  {
    fingerprint: 'doc003',
    path: 'D:/资料/技术笔记.txt',
    size: 65536,
    indexed_at: '2026-04-03T09:00:00',
    chunks_count: 12,
    status: 'indexed',
  },
];

export const mockChunks: Record<string, KbChunk[]> = {
  'doc001': [
    {
      id: 'doc001-001',
      text: '第一章：数据结构概述\n\n数据结构是计算机存储、组织数据的方式。良好的数据结构能够提高算法的效率，是计算机科学的基础之一。',
      index: 1,
      start_pos: 0,
      end_pos: 856,
      block_type: 'paragraph',
      heading_level: 1,
      heading_text: '第一章：数据结构概述',
    },
    {
      id: 'doc001-002',
      text: '1.1 算法基础',
      index: 2,
      start_pos: 857,
      end_pos: 870,
      block_type: 'heading',
      heading_level: 2,
      heading_text: '1.1 算法基础',
    },
    {
      id: 'doc001-003',
      text: `int binary_search(int arr[], int n, int target) {
    int left = 0, right = n - 1;
    while (left <= right) {
        int mid = left + (right - left) / 2;
        if (arr[mid] == target) return mid;
        if (arr[mid] < target) left = mid + 1;
        else right = mid - 1;
    }
    return -1;
}`,
      index: 3,
      start_pos: 871,
      end_pos: 1100,
      block_type: 'code',
      heading_level: 0,
      heading_text: '',
    },
    {
      id: 'doc001-004',
      text: '| 算法 | 时间复杂度 | 空间复杂度 |\n|-------------|-------------|\n| 二分查找 | O(log n) | O(1) |\n| 冒泡排序 | O(n²) | O(1) |\n| 快速排序 | O(n log n) | O(log n) |',
      index: 4,
      start_pos: 1101,
      end_pos: 1300,
      block_type: 'table',
      heading_level: 0,
      heading_text: '',
    },
    {
      id: 'doc001-005',
      text: '二分查找是一种在有序数组中查找特定元素的搜索算法。',
      index: 5,
      start_pos: 1301,
      end_pos: 1450,
      block_type: 'paragraph',
      heading_level: 0,
      heading_text: '',
    },
    {
      id: 'doc001-006',
      text: 'E = mc²',
      index: 6,
      start_pos: 1451,
      end_pos: 1460,
      block_type: 'formula',
      heading_level: 0,
      heading_text: '',
    },
    {
      id: 'doc001-007',
      text: '第一章完结，下一章将介绍线性结构和非线性结构。',
      index: 7,
      start_pos: 1461,
      end_pos: 1520,
      block_type: 'paragraph',
      heading_level: 0,
      heading_text: '',
    },
  ],
  'doc002': [
    {
      id: 'doc002-001',
      text: '# 记忆助手项目文档\n\n## 项目概述\n\n记忆助手是一个基于LLM的智能记忆管理系统。',
      index: 1,
      start_pos: 0,
      end_pos: 200,
      block_type: 'heading',
      heading_level: 1,
      heading_text: '项目概述',
    },
    {
      id: 'doc002-002',
      text: '## 核心功能\n\n- 多Agent协作架构\n- 记忆网状存储\n- 智能召回机制\n- 价值评估体系',
      index: 2,
      start_pos: 201,
      end_pos: 400,
      block_type: 'paragraph',
      heading_level: 0,
      heading_text: '核心功能',
    },
    {
      id: 'doc002-003',
      text: `class MemoryNode:
    def __init__(self, fingerprint: str, content: str):
        self.fingerprint = fingerprint
        self.content = content
        self.edges = []
        self.value_score = 0.0
        self.recall_count = 0`,
      index: 3,
      start_pos: 401,
      end_pos: 600,
      block_type: 'code',
      heading_level: 0,
      heading_text: '',
    },
  ],
  'doc003': [
    {
      id: 'doc003-001',
      text: '## React 最佳实践\n\n### 组件设计\n\n1. 单一职责原则\n2. 复用性优先\n3. 性能优化',
      index: 1,
      start_pos: 0,
      end_pos: 300,
      block_type: 'heading',
      heading_level: 1,
      heading_text: 'React 最佳实践',
    },
    {
      id: 'doc003-002',
      text: 'useEffect(() => {\n  document.title = count + " 条消息";\n}, [count]);',
      index: 2,
      start_pos: 301,
      end_pos: 400,
      block_type: 'code',
      heading_level: 0,
      heading_text: '',
    },
    {
      id: 'doc003-003',
      text: 'React Hooks 使用指南',
      index: 3,
      start_pos: 401,
      end_pos: 420,
      block_type: 'heading',
      heading_level: 2,
      heading_text: 'Hooks 使用指南',
    },
  ],
};

// 格式化文件大小
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// 获取文件名
export function getFileName(path: string): string {
  return path.split('/').pop() || path.split('\\').pop() || path;
}

// 获取文件扩展名
export function getFileExtension(path: string): string {
  const name = getFileName(path);
  const parts = name.split('.');
  return parts.length > 1 ? parts.pop()!.toLowerCase() : '';
}
