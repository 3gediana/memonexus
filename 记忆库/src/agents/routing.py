import json
from datetime import datetime, timezone, timedelta
from src.system.llm_client import chat_completion
from src.system.retry import call_with_retry
from src.system.debug import debug_print, debug_tool_call, DEBUG_MODE


ROUTING_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_key_summaries",
            "description": "获取所有key的摘要信息，了解各key的领域范围和已有内容",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "assign_memory_to_keys",
            "description": "提交候选记忆的key归属分配结果",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "memory": {
                                    "type": "string",
                                    "description": "提炼后的记忆文本",
                                },
                                "target_key": {
                                    "type": "string",
                                    "description": "目标key名",
                                },
                            },
                            "required": ["memory", "target_key"],
                        },
                    }
                },
                "required": ["items"],
            },
        },
    },
]


def _get_key_summaries_impl():
    """实现：获取所有key的摘要"""
    from src.tools.key_tools import get_key_overview

    overview = get_key_overview()
    if not overview["success"]:
        return {"success": False, "error": overview.get("error")}

    summaries = {}
    for k in overview["keys"]:
        key_name = k["key"]
        summary = k.get("summary", "")
        count = k.get("memory_count", 0)
        summaries[key_name] = {"summary": summary, "memory_count": count}

    return {"success": True, "key_summaries": summaries}


class RoutingAgent:
    def __init__(self, available_keys: list[str]):
        self.available_keys = available_keys
        self.system_prompt = self._build_prompt()
        self.tools = ROUTING_TOOLS
        self.tool_handlers = {
            "get_key_summaries": lambda: _get_key_summaries_impl(),
            "assign_memory_to_keys": lambda items: {"items": items},
        }

    def _build_prompt(self) -> str:
        key_list = ", ".join(self.available_keys)
        now = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        last_week_start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        last_week_end = yesterday
        # 计算这个周末和下个周末
        today_weekday = datetime.now().weekday()  # 0=Monday
        days_to_saturday = (5 - today_weekday) % 7
        if days_to_saturday == 0:
            days_to_saturday = 7  # 如果今天是周六，算下个周六
        this_saturday = (datetime.now() + timedelta(days=days_to_saturday)).strftime(
            "%Y-%m-%d"
        )
        this_sunday = (datetime.now() + timedelta(days=days_to_saturday + 1)).strftime(
            "%Y-%m-%d"
        )
        next_saturday = (
            datetime.now() + timedelta(days=days_to_saturday + 7)
        ).strftime("%Y-%m-%d")
        next_sunday = (datetime.now() + timedelta(days=days_to_saturday + 8)).strftime(
            "%Y-%m-%d"
        )
        # 这周和下周
        this_week_start = (datetime.now() - timedelta(days=today_weekday)).strftime(
            "%Y-%m-%d"
        )
        next_week_start = (datetime.now() + timedelta(days=7 - today_weekday)).strftime(
            "%Y-%m-%d"
        )
        next_week_end = (datetime.now() + timedelta(days=13 - today_weekday)).strftime(
            "%Y-%m-%d"
        )
        return f"""你是一个记忆路由Agent。

## 当前时间信息
- 今天：{now}（星期{"一二三四五六日"[today_weekday]}）
- 昨天：{yesterday}
- 上周：{last_week_start} 至 {last_week_end}
- 这个周末：{this_saturday} 至 {this_sunday}
- 下个周末：{next_saturday} 至 {next_sunday}
- 下周：{next_week_start} 至 {next_week_end}

## 时间处理规则
- 用户说的"今天"、"明天"、"昨天"等相对时间，必须转换为绝对日期写入记忆
- 例如："明天要去医院" → "{(datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")}要去医院"
- 例如："昨天复习了数学" → "{yesterday}复习了数学"
- 例如："上周去了图书馆" → "{last_week_start}至{last_week_end}期间去了图书馆"
- 例如："这个周末去看电影" → "{this_saturday}至{this_sunday}去看电影"
- 例如："下周末要考试" → "{next_saturday}至{next_sunday}要考试"
- 例如："下周一交作业" → "{next_week_start}交作业"
- **重要**：用户说的"最近"、"最近开始"、"这段时间"等模糊时间词，必须加上今天的日期作为参照点
- 例如："我最近开始准备考研" → "{now}开始准备考研"
- 例如："我这段时间在学英语" → "{now}表示这段时间在学英语"

## 可用的记忆分类（key）
{key_list}

## 你的任务
1. 先调用get_key_summaries了解各key的领域范围和已有内容
2. 判断用户消息中是否包含值得记忆的内容
3. 如果有，提炼为规范化的记忆文本（将相对时间转换为绝对日期）
4. 判断归属哪个key
5. 调用assign_memory_to_keys提交结果

## 判断规则
- 值得记忆：事实性信息、偏好、状态、承诺、计划、重要观点
- 不值得记忆：纯寒暄（你好/谢谢/再见）、纯情绪表达（哈哈/唉）、纯问题（没有透露个人信息）、重复啰嗦的同一件事
- 【严格过滤】用户消息内部如果有重复表达同一件事，只提炼一条核心记忆，不要逐句拆分
- 【严格过滤】用户消息如果主要是寒暄+少量信息，只提取信息部分，忽略寒暄

## 提炼和去重规则（重要）
- 用户经常用多句话反复说同一件事，你必须合并提炼为一条精炼记忆
- 例如："我最近开始考研了，对就是准备考研，考研复习中" → 提炼为一条："{now}开始准备考研"
- 例如："我喜欢吃苹果，苹果是我的最爱，水果里最喜欢苹果" → 提炼为一条："最喜欢吃苹果"
- 不要将同一件事的不同表述拆分为多条记忆

## 拆分原则
- 多个独立事实 → 拆分
- 同一主题的不同表述 → 合并为一条
- 同一主题的不同方面 → 保持一条，但涵盖所有方面

## 重要
你必须调用工具（get_key_summaries 或 assign_memory_to_keys），不要直接回复文字。
"""

    def analyze_message(self, message: str) -> list[dict]:
        def _call():
            if DEBUG_MODE:
                debug_print("RoutingAgent 输入", {"message": message})

            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": message},
            ]

            # 支持多轮工具调用
            last_tool_name = None
            same_tool_count = 0

            for _ in range(3):
                response = chat_completion(
                    messages=messages,
                    tools=self.tools,
                    provider="deepseek",
                )

                msg = response.choices[0].message if response.choices else None
                if not msg or not getattr(msg, "tool_calls", None):
                    # 模型没有调用工具，说明它认为没有值得记忆的内容
                    # 但如果这是第一轮（还没查过 summaries），至少让它查一下
                    if last_tool_name is None:
                        # 强制调用 get_key_summaries
                        messages.append(
                            {
                                "role": "user",
                                "content": "请先调用get_key_summaries了解各key的情况",
                            }
                        )
                        continue
                    return []

                tool_call = response.choices[0].message.tool_calls[0]
                func_name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)

                if DEBUG_MODE:
                    debug_print(
                        "RoutingAgent 工具调用",
                        {"tool": func_name, "args": args},
                    )

                if func_name == "assign_memory_to_keys":
                    return args.get("items", [])

                # 去重检测：连续调用相同非决策工具2次，强制结束
                if func_name == last_tool_name:
                    same_tool_count += 1
                    if same_tool_count >= 2:
                        return []
                else:
                    last_tool_name = func_name
                    same_tool_count = 1

                # 执行工具
                handler = self.tool_handlers.get(func_name)
                if handler:
                    result = handler(**args) if args else handler()

                    if DEBUG_MODE:
                        debug_tool_call(func_name, args, result)

                    messages.append(
                        {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": response.choices[0].message.tool_calls,
                        }
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "content": json.dumps(result, ensure_ascii=False),
                            "tool_call_id": tool_call.id,
                        }
                    )

            return []

        return call_with_retry(_call)
