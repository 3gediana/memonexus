/**
 * Ollama API 适配器 - 为 CCR 提供 OpenAI 兼容接口
 * 功能：
 * 1. 接收 OpenAI 格式的 /v1/chat/completions 请求
 * 2. 转换为 Ollama 原生格式
 * 3. 维护对话历史（内存缓存）
 * 4. 返回 OpenAI 格式响应
 */

const http = require('http');

// 配置
const CONFIG = {
  port: 11435,  // 适配器监听端口
  ollamaBaseUrl: 'http://localhost:11434',
  defaultModel: 'qwen2.5',
  maxHistoryLength: 20,  // 每个会话最多保留多少条消息
  historyTTL: 30 * 60 * 1000,  // 会话过期时间（30 分钟）
};

// 会话历史存储：{ sessionId: { messages: [], lastAccess: timestamp } }
const sessions = new Map();

/**
 * 清理过期会话
 */
function cleanupSessions() {
  const now = Date.now();
  for (const [id, session] of sessions.entries()) {
    if (now - session.lastAccess > CONFIG.historyTTL) {
      sessions.delete(id);
      console.log(`[清理] 会话 ${id} 已过期`);
    }
  }
}

// 每 5 分钟清理一次
setInterval(cleanupSessions, 5 * 60 * 1000);

/**
 * 获取或创建会话历史
 */
function getSession(sessionId) {
  const session = sessions.get(sessionId);
  if (session) {
    session.lastAccess = Date.now();
    return session.messages;
  }
  // 创建新会话
  sessions.set(sessionId, {
    messages: [],
    lastAccess: Date.now(),
  });
  return [];
}

/**
 * 添加消息到会话历史
 */
function addMessage(sessionId, role, content) {
  const messages = getSession(sessionId);
  messages.push({ role, content });

  // 限制历史长度
  if (messages.length > CONFIG.maxHistoryLength) {
    // 保留 system 消息，删除最早的 user/assistant 消息
    const systemMsgs = messages.filter(m => m.role === 'system');
    const otherMsgs = messages.filter(m => m.role !== 'system');
    const trimmed = otherMsgs.slice(-CONFIG.maxHistoryLength + systemMsgs.length);
    sessions.get(sessionId).messages = [...systemMsgs, ...trimmed];
  }
}

/**
 * 解析请求体
 */
function parseBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      try {
        resolve(body ? JSON.parse(body) : {});
      } catch (e) {
        reject(new Error('无效的 JSON'));
      }
    });
    req.on('error', reject);
  });
}

/**
 * 发送 JSON 响应
 */
function sendJson(res, status, data) {
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(data));
}

/**
 * 将 OpenAI 消息格式转换为 Ollama 格式
 * Ollama 期望 content 是字符串，不是数组
 */
function toOllamaMessages(openaiMessages) {
  return openaiMessages.map(msg => {
    let content = msg.content;
    // 处理 content 是数组的情况（多模态格式）
    if (Array.isArray(content)) {
      content = content
        .filter(part => part.type === 'text')
        .map(part => part.text || '')
        .join('');
    }
    return {
      role: msg.role,
      content: String(content || ''),
    };
  });
}

/**
 * 调用 Ollama API
 */
async function callOllama(messages, model, options = {}) {
  const url = `${CONFIG.ollamaBaseUrl}/api/chat`;

  const payload = {
    model: model || CONFIG.defaultModel,
    messages: messages,
    stream: false,
    options: {
      temperature: options.temperature ?? 0.7,
      max_tokens: options.maxTokens ?? 2048,
      top_p: options.topP ?? 0.9,
    },
  };

  console.log(`[Ollama] 调用 ${url}, 模型：${payload.model}`);

  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(60000),
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`Ollama API 错误 (${response.status}): ${error}`);
  }

  const data = await response.json();
  return {
    content: data.message?.content || '',
    model: data.model,
    usage: {
      prompt_tokens: data.prompt_eval_count || 0,
      completion_tokens: data.eval_count || 0,
      total_tokens: (data.prompt_eval_count || 0) + (data.eval_count || 0),
    },
  };
}

/**
 * 处理 /v1/chat/completions 请求
 */
async function handleChatCompletions(req, res) {
  try {
    const body = await parseBody(req);

    const {
      messages = [],
      model = CONFIG.defaultModel,
      stream = false,
      temperature,
      max_tokens,
      top_p,
    } = body;

    if (!messages.length) {
      return sendJson(res, 400, { error: 'messages 不能为空' });
    }

    // 提取会话 ID（从 user 消息中找，或者用 IP）
    const sessionId = req.headers['x-session-id']
      || req.headers['x-request-id']
      || req.socket.remoteAddress
      || 'default';

    // 获取历史消息
    const history = getSession(sessionId);

    // 合并历史消息和当前消息
    const allMessages = [...history, ...messages];

    console.log(`[请求] 会话：${sessionId}, 消息数：${allMessages.length}`);

    // 调用 Ollama
    const result = await callOllama(
      toOllamaMessages(allMessages),
      model,
      { temperature, maxTokens: max_tokens, topP: top_p }
    );

    // 保存 assistant 回复到历史
    const lastUserMessage = messages[messages.length - 1];
    if (lastUserMessage?.role === 'user') {
      addMessage(sessionId, 'user', lastUserMessage.content);
      addMessage(sessionId, 'assistant', result.content);
    }

    // 返回 OpenAI 格式响应
    const response = {
      id: `chatcmpl-${Date.now()}`,
      object: 'chat.completion',
      created: Math.floor(Date.now() / 1000),
      model: result.model,
      choices: [{
        index: 0,
        message: {
          role: 'assistant',
          content: result.content,
        },
        finish_reason: 'stop',
      }],
      usage: result.usage,
    };

    sendJson(res, 200, response);

  } catch (error) {
    console.error('[错误]', error);
    sendJson(res, 500, {
      error: {
        message: error.message,
        type: 'api_error',
      },
    });
  }
}

/**
 * 处理 /v1/models 请求
 */
async function handleModels(req, res) {
  try {
    const response = await fetch(`${CONFIG.ollamaBaseUrl}/api/tags`);
    const data = await response.json();

    const models = (data.models || []).map(m => ({
      id: m.name,
      object: 'model',
      created: Math.floor(Date.now() / 1000),
      owned_by: 'ollama',
    }));

    sendJson(res, 200, {
      object: 'list',
      data: models,
    });
  } catch (error) {
    sendJson(res, 500, { error: error.message });
  }
}

/**
 * 健康检查
 */
function handleHealth(res) {
  sendJson(res, 200, {
    status: 'ok',
    ollama: CONFIG.ollamaBaseUrl,
    sessions: sessions.size,
  });
}

// 创建 HTTP 服务器
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${CONFIG.port}`);
  const path = url.pathname;

  console.log(`[${new Date().toISOString()}] ${req.method} ${path}`);

  // CORS
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Session-ID');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  try {
    if (path === '/v1/chat/completions') {
      await handleChatCompletions(req, res);
    } else if (path === '/v1/models') {
      await handleModels(req, res);
    } else if (path === '/health') {
      handleHealth(res);
    } else {
      sendJson(res, 404, { error: `未知路径：${path}` });
    }
  } catch (error) {
    console.error('[服务器错误]', error);
    sendJson(res, 500, { error: error.message });
  }
});

// 启动服务器
server.listen(CONFIG.port, () => {
  console.log(`
╔══════════════════════════════════════════════════════════╗
║       Ollama API 适配器已启动                             ║
╠══════════════════════════════════════════════════════════╣
║  监听地址：http://localhost:${CONFIG.port}                  ║
║  Ollama 地址：${CONFIG.ollamaBaseUrl}                        ║
║  默认模型：${CONFIG.defaultModel}                           ║
╠══════════════════════════════════════════════════════════╣
║  CCR 配置示例：                                           ║
║  {                                                       ║
║    "name": "ollama-local",                               ║
║    "api_base_url": "http://localhost:${CONFIG.port}/v1/chat/completions", ║
║    "api_key": "ollama",                                  ║
║    "models": ["${CONFIG.defaultModel}"],                     ║
║    "transformer": { "use": ["OpenAI"] }                  ║
║  }                                                       ║
╚══════════════════════════════════════════════════════════╝
  `);
});

server.on('error', (err) => {
  if (err.code === 'EADDRINUSE') {
    console.error(`端口 ${CONFIG.port} 已被占用`);
  } else {
    console.error('服务器错误:', err);
  }
  process.exit(1);
});
