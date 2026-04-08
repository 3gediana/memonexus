import json
from src.system.llm_client import chat_completion
from src.system.retry import call_with_retry
from src.system.debug import debug_print, debug_tool_call, DEBUG_MODE


KEY_AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_memory_by_fingerprint",
            "description": "根据指纹获取记忆详情，用于判断冲突或重复时查看详情",
            "parameters": {
                "type": "object",
                "properties": {
                    "fingerprints": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要查询的记忆指纹列表",
                    },
                },
                "required": ["fingerprints"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_memory_to_key",
            "description": "新增memory，并指定与同key下其他记忆的关联边",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "memory": {"type": "string"},
                    "tag": {
                        "type": "string",
                        "description": "记忆≤20字时用原文，>20字时缩写涵盖所有关键信息，长度不超过原文",
                    },
                    "summary_item": {"type": "string"},
                    "importance_score": {
                        "type": "number",
                        "description": "重要性评分(0.1-0.9)：0.9=关键事实/长期偏好/重要计划，0.5=普通信息，0.1=临时状态/琐碎细节",
                    },
                    "edges": {
                        "type": "array",
                        "description": "与同key下其他记忆的关联边（可选，不传则由系统分批处理）",
                        "items": {
                            "type": "object",
                            "properties": {
                                "target_fingerprint": {"type": "string"},
                                "strength": {"type": "number", "enum": [0.3, 0.6, 0.9]},
                                "reason": {"type": "string"},
                            },
                            "required": ["target_fingerprint", "strength", "reason"],
                        },
                    },
                },
                "required": [
                    "key",
                    "memory",
                    "tag",
                    "summary_item",
                    "importance_score",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "replace_memory_in_key",
            "description": "替换已有memory，并指定与同key下其他记忆的关联边",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "old_fingerprint": {"type": "string"},
                    "new_memory": {"type": "string"},
                    "new_tag": {"type": "string"},
                    "new_summary_item": {"type": "string"},
                    "edges": {
                        "type": "array",
                        "description": "与同key下其他记忆的关联边",
                        "items": {
                            "type": "object",
                            "properties": {
                                "target_fingerprint": {"type": "string"},
                                "strength": {"type": "number", "enum": [0.3, 0.6, 0.9]},
                                "reason": {"type": "string"},
                            },
                            "required": ["target_fingerprint", "strength", "reason"],
                        },
                    },
                },
                "required": [
                    "key",
                    "old_fingerprint",
                    "new_memory",
                    "new_tag",
                    "new_summary_item",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reject_candidate",
            "description": "驳回候选memory（不属于本key）",
            "parameters": {
                "type": "object",
                "properties": {"reason": {"type": "string"}},
                "required": ["reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mark_duplicate",
            "description": "标记为重复记忆",
            "parameters": {
                "type": "object",
                "properties": {"existing_fingerprint": {"type": "string"}},
                "required": ["existing_fingerprint"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "build_edges",
            "description": "为指定指纹与一批已有记忆建立关联边",
            "parameters": {
                "type": "object",
                "properties": {
                    "edges": {
                        "type": "array",
                        "description": "与当前批次记忆的关联边",
                        "items": {
                            "type": "object",
                            "properties": {
                                "target_fingerprint": {"type": "string"},
                                "strength": {"type": "number", "enum": [0.3, 0.6, 0.9]},
                                "reason": {"type": "string"},
                            },
                            "required": ["target_fingerprint", "strength", "reason"],
                        },
                    },
                },
                "required": ["edges"],
            },
        },
    },
]


def _get_memory_by_fingerprint_impl(fingerprints: list):
    from src.tools.query_tools import format_memory_for_agent

    text = format_memory_for_agent(fingerprints)
    return {"success": True, "text": text}


class KeyAgent:
    def __init__(self, key: str):
        self.key = key
        self.system_prompt = self._build_decision_prompt()
        self.tools = KEY_AGENT_TOOLS
        self.tool_handlers = {
            "get_memory_by_fingerprint": _get_memory_by_fingerprint_impl,
        }

    def _build_decision_prompt(self) -> str:
        """存储决策阶段：判断add/replace/reject/duplicate"""
        return f"""## 你的角色
你是"{self.key}"分类的记忆审核员。RoutingAgent 已经判断这条候选记忆属于本分类，现在由你最终确认并存储。

## 你的输入
- 候选memory：待存储的记忆内容
- tag：如果为空，你需要生成tag
- 已有记忆列表：格式为 tag-指纹（如"考研计划-fp_xxx"）

## 你必须做的事情
收到候选记忆后，你必须且只能做以下四件事之一（调用对应工具）：
1. **add** → 调用 add_memory_to_key：确认属于本分类，直接存储
2. **reject** → 调用 reject_candidate：明显不属于本分类，驳回
3. **duplicate** → 调用 mark_duplicate：与已有记忆语义高度重复
4. **replace** → 调用 replace_memory_in_key：与已有记忆在同一对象+属性上冲突

## 去重检查（必须执行）
在决定 add 之前，你必须先检查是否与已有记忆重复：
1. 对比候选记忆与已有记忆的 tag-指纹列表
2. 如果 tag 看起来相似（如时间格式不同但内容相同），**必须调用 get_memory_by_fingerprint 查原文对比**
3. 重复判断标准：
   - **高度重复**（mark_duplicate）：描述同一件事，只是措辞/时间格式不同，如"2026-04-04开始准备考研" vs "2026.4.4开始准备考研"
   - **状态更新**（replace）：同一对象的新状态替代旧状态，如"Python基础好" vs "Python基础差，正在从头学"
   - **不是重复**：描述同一大主题但不同方面，如"考研计划"和"买了考研资料"
4. 如果 tag 中有相似的日期表达（如"2026-04-04" vs "2026.4.4"、"今天" vs 具体日期），**必须查原文确认**

## 查询原文
已有记忆列表只提供 tag-指纹，如果你需要查看某条记忆的原文来判断是否重复或冲突：
→ 调用 get_memory_by_fingerprint(fingerprints=["fp_xxx", "fp_yyy"])
→ 返回格式：每行一个 tag-指纹:记忆

## 重要警告
- 如果你不调用任何工具，这条记忆就会丢失，用户告诉你的信息就白说了
- RoutingAgent 已经判断过分类，你只需要确认即可，不要过度犹豫
- **重复是浪费存储空间的大问题：宁可标记为 duplicate，也不要存一条跟已有记忆一样的东西**
- 只有确认跟已有记忆都不同之后，才能 add

## Tag 生成规则
- 如果传入的 tag 与原文相同（记忆≤20字），直接使用该 tag
- 如果传入的 tag 为空（记忆>20字），你必须生成 tag：
  - **必须包含时间信息**（日期、时间段、状态起始时间等）
  - 涵盖时间、地点、人物、事件、对象等所有关键信息
  - 长度不超过原文
  - 示例："今天下午3点在图书馆复习数据结构，看到二叉树部分" → tag="2026-04-04_15:00图书馆数据结构复习二叉树"
  - 示例："最近开始准备考研" → tag="2026-04-04开始准备考研"
  - 示例："每天早上7点起床背单词" → tag="每日7点起床背单词_2026-04-04记录"
  - **时间格式统一使用 YYYY-MM-DD 或明确时间描述**

## 重要性评分规则（importance_score）
每条记忆必须评估重要性，传入 importance_score 参数（0.1-0.9）：
- **0.9（关键）**：不可丢失的核心事实，如密码、截止日期、长期目标、重要偏好
  - 示例："考研报名截止10月31日" → 0.9
  - 示例："我对花生过敏" → 0.9
- **0.7（重要）**：需要长期记住的计划、偏好、状态
  - 示例："每天早上7点起床背单词" → 0.7
  - 示例："开始准备考研，目标北大计算机" → 0.7
- **0.5（普通）**：一般性信息，有一定价值但不是核心
  - 示例："今天买了本高数辅导书" → 0.5
  - 示例："周末看了场电影" → 0.5
- **0.3（次要）**：临时状态、细节补充、可能很快过时的信息
  - 示例："今天心情不太好" → 0.3
  - 示例："复习到第三章第二节" → 0.3
- **0.1（琐碎）**：纯闲聊、即时状态、几乎无长期价值
  - 示例："今天天气不错" → 0.1
  - 示例："刚吃完午饭" → 0.1

## 输出格式
直接调用工具，不要输出任何解释文字。

## 示例
候选：每天早上7点起床背单词（已有记忆：无）
→ 调用 add_memory_to_key(key="study", memory="每天早上7点起床背单词", tag="考研作息", summary_item="每天7点起床背单词", importance_score=0.7, edges=[])

候选：周末要去医院复查一下胃（health key，无已有记忆）
→ 调用 add_memory_to_key(key="health", memory="周末要去医院复查一下胃", tag="就医计划", summary_item="周末去医院复查胃", importance_score=0.7, edges=[])

候选：2026.4.4开始准备考研每天8小时（已有记忆：2026-04-04开始准备考研-目标北大-每天8小时-fp_xxx）
→ tag 看起来相似，先查原文：get_memory_by_fingerprint(["fp_xxx"])
→ 确认是同一件事 → 调用 mark_duplicate(fingerprint="fp_xxx", reason="同一考研准备记录，只是日期格式不同")

候选：用户Python编程基础很差，正在从头学（已有记忆：Python基础_编程能力-fp_yyy）
→ 查原文：get_memory_by_fingerprint(["fp_yyy"])
→ 确认是同一对象的新状态（好→差）→ 调用 replace_memory_in_key(key="study", old_fingerprint="fp_yyy", new_memory="用户Python编程基础很差，正在从头学", new_tag="Python基础_从零开始", new_summary_item="Python基础差从头学")
"""

    def process_candidate(
        self, candidate: str, tag: str, existing_memories: list = None
    ) -> dict:
        if existing_memories is None:
            existing_memories = []

        # 格式化为 tag-指纹 列表
        existing_lines = []
        for m in existing_memories:
            fp = m.get("fingerprint", "")
            t = m.get("tag", "")
            existing_lines.append(f"{t}-{fp}")
        existing_str = "\n".join(existing_lines) if existing_lines else "无已有记忆"

        context = f"候选memory：{candidate}\ntag：{tag}\n已有记忆：\n{existing_str}"

        def _call():
            if DEBUG_MODE:
                debug_print(
                    "KeyAgent 输入",
                    {
                        "key": self.key,
                        "candidate": candidate,
                        "tag": tag,
                        "existing_memories": existing_memories,
                    },
                )

            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": context},
            ]

            last_tool_name = None
            same_tool_count = 0

            for attempt in range(3):
                response = chat_completion(
                    messages=messages,
                    tools=self.tools,
                    provider="deepseek",
                )

                # 无工具调用或响应异常：追加警告后重试
                msg = getattr(response.choices[0], "message", None)
                if not msg or not getattr(msg, "tool_calls", None):
                    messages.append(
                        {
                            "role": "assistant",
                            "content": "你必须调用一个工具来完成任务。",
                        }
                    )
                    continue

                tool_call = response.choices[0].message.tool_calls[0]
                func_name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)

                if DEBUG_MODE:
                    debug_print(
                        "KeyAgent 工具调用",
                        {"tool": func_name, "args": args},
                    )

                # 最终决策工具
                if func_name in (
                    "add_memory_to_key",
                    "replace_memory_in_key",
                    "reject_candidate",
                    "mark_duplicate",
                ):
                    return {"action": func_name, "args": args}

                # 去重检测：连续调用相同非决策工具2次，强制结束
                if func_name == last_tool_name:
                    same_tool_count += 1
                    if same_tool_count >= 2:
                        return {"action": "none", "args": {}}
                else:
                    last_tool_name = func_name
                    same_tool_count = 1

                # 中间查询工具
                handler = self.tool_handlers.get(func_name)
                if handler:
                    result = handler(**args)

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

            return {"action": "none", "args": {}}

        return call_with_retry(_call)

    def _build_edges_for_batch(self, new_fp: str, new_memory: str, batch: list) -> dict:
        """
        为单个批次建立边。系统传入一批已有记忆，模型判断与当前批次的关联。
        注意：只提供 build_edges 工具，禁止模型调用 get_memory_by_fingerprint。
        """
        if not batch:
            return {"success": True, "edges": []}

        context = f"新记忆指纹：{new_fp}\n新记忆内容：{new_memory}\n当前批次已有记忆：{json.dumps(batch, ensure_ascii=False)}"

        # 只给 build_edges 工具，防止模型调用 get_memory_by_fingerprint
        BUILD_EDGES_ONLY = [
            t for t in KEY_AGENT_TOOLS if t["function"]["name"] == "build_edges"
        ]

        def _call():
            if DEBUG_MODE:
                debug_print(
                    "KeyAgent 分批建边",
                    {"new_fp": new_fp, "batch_size": len(batch)},
                )

            messages = [
                {"role": "system", "content": self._build_batch_edge_prompt()},
                {"role": "user", "content": context},
            ]

            response = chat_completion(
                messages=messages,
                tools=BUILD_EDGES_ONLY,
                provider="deepseek",
            )

            if response.choices[0].message.tool_calls:
                tool_call = response.choices[0].message.tool_calls[0]
                args = json.loads(tool_call.function.arguments)
                return {"success": True, "edges": args.get("edges", [])}
            return {"success": True, "edges": []}

        return call_with_retry(_call)

    def _build_batch_edge_prompt(self) -> str:
        return f"""## 你的角色
你是"{self.key}"分类的记忆关联分析器。当前你处于**建边阶段**。

## 你的任务
判断新记忆与当前批次中每条记忆的关联强度，调用 build_edges 建边。

## 关联强度标准
- 0.9（强关联）：明显围绕同一件事
- 0.6（中关联）：同一任务背景
- 0.3（弱关联）：有一定联系，比如同一主题的不同方面
- 不建立：完全无关

## 输出要求
你必须调用 build_edges 工具，传入 edges 数组。
如果没有值得建边的记忆，传入空数组 edges: []。
"""
