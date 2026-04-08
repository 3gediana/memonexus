#!/usr/bin/env node
/**
 * 日志工具模块
 * 提供统一的日志输出格式和错误处理
 */

// 日志级别
export enum LogLevel {
  DEBUG = 0,
  INFO = 1,
  WARN = 2,
  ERROR = 3,
}

// 当前日志级别（从环境变量读取，默认为 INFO）
const currentLevel = parseInt(process.env.LOG_LEVEL || '1', 10) as LogLevel;

// 日志颜色（终端输出）
const colors = {
  reset: '\x1b[0m',
  debug: '\x1b[36m',  // 青色
  info: '\x1b[32m',   // 绿色
  warn: '\x1b[33m',   // 黄色
  error: '\x1b[31m',  // 红色
};

// 格式化时间
function formatTime(): string {
  const now = new Date();
  return now.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' });
}

// 格式化日志前缀
function formatPrefix(level: LogLevel, module?: string): string {
  const levelStr = LogLevel[level].toLowerCase();
  const moduleStr = module ? `[${module}]` : '';
  return `\x1b[2m${formatTime()}\x1b[0m ${colors[levelStr as keyof typeof colors]}[${LogLevel[level].toUpperCase()}]${colors.reset}${moduleStr ? ` \x1b[90m${moduleStr}\x1b[0m` : ''}`;
}

// 日志输出函数
function log(level: LogLevel, message: string, module?: string, ...args: any[]): void {
  if (level < currentLevel) return;

  const prefix = formatPrefix(level, module);
  const output = [prefix, message, ...args].join(' ');

  switch (level) {
    case LogLevel.DEBUG:
      console.debug(output);
      break;
    case LogLevel.INFO:
      console.info(output);
      break;
    case LogLevel.WARN:
      console.warn(output);
      break;
    case LogLevel.ERROR:
      console.error(output);
      break;
  }
}

// 导出便捷函数
export const logger = {
  debug: (message: string, module?: string, ...args: any[]) => log(LogLevel.DEBUG, message, module, ...args),
  info: (message: string, module?: string, ...args: any[]) => log(LogLevel.INFO, message, module, ...args),
  warn: (message: string, module?: string, ...args: any[]) => log(LogLevel.WARN, message, module, ...args),
  error: (message: string, module?: string, ...args: any[]) => log(LogLevel.ERROR, message, module, ...args),
};

// 知识库专用日志
export const kbLogger = {
  ocr: (message: string, ...args: any[]) => logger.info(`[OCR] ${message}`, 'KB', ...args),
  extract: (message: string, ...args: any[]) => logger.info(`[提取] ${message}`, 'KB', ...args),
  index: (message: string, ...args: any[]) => logger.info(`[索引] ${message}`, 'KB', ...args),
  search: (message: string, ...args: any[]) => logger.info(`[搜索] ${message}`, 'KB', ...args),
  warn: (message: string, ...args: any[]) => logger.warn(message, 'KB', ...args),
  info: (message: string, ...args: any[]) => logger.info(message, 'KB', ...args),
  error: (message: string, ...args: any[]) => logger.error(message, 'KB', ...args),
};

// 错误类型定义
export class KnowledgeBaseError extends Error {
  constructor(
    public code: string,
    message: string,
    public cause?: Error
  ) {
    super(message);
    this.name = 'KnowledgeBaseError';
  }
}

// 常见错误代码
export const ErrorCodes = {
  FILE_NOT_FOUND: 'FILE_NOT_FOUND',
  FILE_READ_ERROR: 'FILE_READ_ERROR',
  EXTRACT_ERROR: 'EXTRACT_ERROR',
  OCR_ERROR: 'OCR_ERROR',
  INDEX_ERROR: 'INDEX_ERROR',
  SEARCH_ERROR: 'SEARCH_ERROR',
  MODEL_ERROR: 'MODEL_ERROR',
} as const;
