"""统一LLM调用层"""

from openai import OpenAI
from src.system.config import load_config


_clients = {}


def get_llm_client(provider: str = "minimax") -> OpenAI:
    """获取LLM客户端（按provider缓存）"""
    global _clients
    if provider not in _clients:
        config = load_config()
        if provider == "deepseek":
            api_config = config["deepseek"]
            _clients[provider] = OpenAI(
                api_key=api_config["api_key"],
                base_url=api_config["base_url"],
            )
        elif provider == "siliconflow" or provider == "glm":
            api_config = config["glm" if provider == "glm" else "siliconflow"]
            _clients[provider] = OpenAI(
                api_key=api_config["api_key"],
                base_url=api_config["base_url"],
            )
        else:
            api_config = config["minimax"]
            _clients[provider] = OpenAI(
                api_key=api_config["api_key"],
                base_url=api_config["base_url"],
                default_headers={"MiniMax-API-Key": api_config["api_key"]},
            )
    return _clients[provider]


def get_model(provider: str = "minimax") -> str:
    """获取模型名称"""
    config = load_config()
    if provider == "deepseek":
        return config["deepseek"]["model"]
    elif provider == "siliconflow":
        return config["siliconflow"]["model"]
    elif provider == "glm":
        return config["glm"]["model"]
    return config["minimax"]["model"]


def chat_completion(
    messages: list,
    tools: list = None,
    tool_choice: str = "auto",
    provider: str = "minimax",
    system: str = None,
    stream: bool = False,
):
    """统一的chat completion调用，支持多provider和流式输出

    Args:
        messages: 消息列表
        tools: 工具定义列表
        tool_choice: 工具选择策略
        provider: 提供商 (minimax/deepseek)
        system: 系统提示词
        stream: 是否流式输出

    Returns:
        非流式: completion对象
        流式: 生成器，产生 (content片段, reasoning累积, 是否结束)
    """
    client = get_llm_client(provider)
    model = get_model(provider)

    # 如果传了system参数，插入到messages开头
    if system:
        messages = [{"role": "system", "content": system}] + list(messages)

    kwargs = {
        "model": model,
        "messages": messages,
        "stream": stream,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice

    response = client.chat.completions.create(**kwargs)

    if stream:
        return _parse_stream_response(response)
    return response


def _parse_stream_response(response):
    """解析MiniMax流式响应

    Yields:
        (content_delta: str, reasoning_buffer: str, is_final: bool, finish_reason: str, tool_call: dict or None)
    """
    reasoning_buffer = ""
    finish_reason = None
    tool_call = None

    for chunk in response:
        if not chunk.choices:
            continue

        choice = chunk.choices[0]
        delta = getattr(choice, "delta", None)
        if not delta:
            continue

        # 思考过程
        reasoning = getattr(delta, "reasoning_content", None) or ""
        if reasoning:
            reasoning_buffer += reasoning

        # 回复内容
        content = getattr(delta, "content", None) or ""

        # 判断是否结束
        finish_reason = getattr(choice, "finish_reason", None)
        is_final = (finish_reason == "stop") or (finish_reason == "tool_calls")

        # tool_call 信息（需要累积，因为arguments可能跨多个chunk）
        if hasattr(delta, "tool_calls") and delta.tool_calls:
            tc = delta.tool_calls[0]
            func = getattr(tc, "function", None)
            if func:
                if tool_call is None:
                    tool_call = {
                        "name": getattr(func, "name", ""),
                        "arguments": getattr(func, "arguments", ""),
                        "id": getattr(tc, "id", ""),
                    }
                else:
                    # 累积 arguments（保留已有的 name 和 id）
                    args = getattr(func, "arguments", "")
                    if args:
                        tool_call["arguments"] = (
                            tool_call.get("arguments") or ""
                        ) + args
                    # 更新 name 和 id（如果新值不为空）
                    name = getattr(func, "name", "")
                    if name:
                        tool_call["name"] = name
                    tid = getattr(tc, "id", "")
                    if tid:
                        tool_call["id"] = tid

        yield content, reasoning_buffer, is_final, finish_reason, tool_call
