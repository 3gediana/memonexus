"""
模拟用户 Agent - 扮演测试框架，自主决策测试记忆系统
使用 MiniMax 模型，自主维护测试记忆
"""

import json
from src.system.llm_client import chat_completion
from src.system.retry import call_with_retry


SIM_USER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "chat",
            "description": "向AI助手发送一条消息，等待回复",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "要发送的消息内容"},
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "new_session",
            "description": "开启一段新的对话，清空当前会话历史",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "store_memories",
            "description": "手动触发记忆存储，将当前会话中的信息保存到记忆库",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sleep",
            "description": "模拟用户离开/等待，休眠指定秒数。超过45秒会自动触发记忆存储",
            "parameters": {
                "type": "object",
                "properties": {
                    "seconds": {
                        "type": "integer",
                        "description": "休眠秒数，建议设50触发自动存储",
                    },
                },
                "required": ["seconds"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "view_key_overview",
            "description": "查看记忆分类概览，了解每个分类下有多少条记忆",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "view_memories",
            "description": "查看某个分类下的具体记忆内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "分类名称，如 study, health, preference 等",
                    },
                },
                "required": ["key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "switch_instance",
            "description": "切换到另一个实例（数据空间），不同实例的数据完全隔离",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "实例名称"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_instance",
            "description": "创建一个新的实例（数据空间）",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "新实例名称"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_instances",
            "description": "查看当前所有可用的实例列表",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish_demo",
            "description": "结束演示",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_memory",
            "description": "更新你自己的测试记忆，记录已透露的信息、已测试的功能等",
            "parameters": {
                "type": "object",
                "properties": {
                    "revealed_info": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "已透露的信息类别",
                    },
                    "tested_features": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "已测试的系统功能",
                    },
                    "test_questions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "已问过的测试问题",
                    },
                },
            },
        },
    },
]

SYSTEM_PROMPT = """你是一个自动化测试框架，正在通过扮演用户来测试一个记忆助手系统的完整功能。

## 你的角色
你扮演一个真实用户（大三学生），与记忆系统进行自然对话。你的目标是全面测试系统的各项功能。

## 你需要测试的功能
1. 实例管理：创建实例、切换实例、实例间数据隔离
2. 会话管理：开启新会话、会话消息积累
3. 记忆存储：
   - 自然对话中透露信息，让系统自动提取
   - 使用 sleep(50) 触发45秒自动存储机制
   - 使用 store_memories() 手动触发存储
   - 验证存储结果（view_key_overview, view_memories）
4. 记忆召回：
   - 问关于自己的问题，测试系统能否准确回忆
   - 测试不同类别的记忆召回（学习、健康、娱乐、感情等）
   - 验证召回的相关性和准确性
5. 多轮对话：测试系统是否能记住上下文

## 你的人设（用于生成对话内容）
- 大三学生，计算机相关专业
- 正在准备考研，有女朋友
- 喜欢追剧、编程、偶尔健身
- 最近学习压力大，有些失眠
- 有一些具体的生活细节（作息时间、学习安排、购物记录等）

## 你的自主记忆
你需要自己记住以下信息（用 JSON 格式维护）：
- revealed_info: 你已经在对话中透露的信息类别列表
- tested_features: 你已经测试过的系统功能列表
- test_questions: 你已经问过的测试问题列表

每次决策时，你需要：
1. 回顾自己的记忆，知道哪些已经做了、哪些还没做
2. 根据对话历史决定下一步
3. 当你完成了一个有意义的操作（如透露了新信息、测试了新功能、问了一个测试问题）后，调用 update_memory 工具更新你的记忆
4. 【重要】不要在没有做任何新操作的情况下调用 update_memory

## 行为规则
1. 你是测试框架，不是真正的用户。你的目标是覆盖所有功能
2. 根据对方的回复自然接话，像真实聊天一样
3. 每次只调用一个工具
4. 信息透露要分散在不同轮次
5. 测试完一个功能后记录到 tested_features
6. 当所有功能都测试完毕后，调用 finish_demo
7. 【重要】不要一开始就调用 update_memory，先做实际的操作（发消息、创建实例等）

## 可用工具
- chat(message): 发消息给AI
- new_session(): 开启新对话
- store_memories(): 手动保存记忆
- sleep(seconds): 等待/离开（超过45秒会自动触发存储）
- view_key_overview(): 查看记忆分类
- view_memories(key): 查看某类记忆
- switch_instance(name): 切换实例
- create_instance(name): 创建新实例
- list_instances(): 查看实例列表
- finish_demo(): 结束演示

## 结束条件
当你认为已经充分测试了所有核心功能时，调用 finish_demo。
建议至少完成：实例创建→对话存储→自动存储→手动存储→召回测试→实例切换验证隔离。"""


class SimUserAgent:
    def __init__(self):
        self.tools = SIM_USER_TOOLS
        self.round = 0

        # 自主记忆（由 LLM 自己维护，这里只是存储容器）
        self.agent_memory = {
            "revealed_info": [],
            "tested_features": [],
            "test_questions": [],
        }

        # 对话记忆（最近 N 轮）
        self.conversation_memory = []
        self.max_memory_length = 20

    def decide_next(self) -> dict:
        """决定下一步操作"""
        self.round += 1

        prompt = self._build_prompt()

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": self._build_user_message()},
        ]

        def _call():
            response = chat_completion(
                messages=messages,
                tools=self.tools,
                provider="minimax",
            )

            if not response.choices[0].message.tool_calls:
                return {"action": "none", "args": {}}

            tool_call = response.choices[0].message.tool_calls[0]
            func_name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)

            return {
                "action": func_name,
                "args": args,
                "thought": response.choices[0].message.content or "",
            }

        return call_with_retry(_call)

    def update_memory(self, memory_json: str):
        """更新 Agent 自主记忆（由 LLM 在工具调用中返回）"""
        try:
            self.agent_memory = json.loads(memory_json)
        except Exception:
            pass

    def observe_result(self, tool_name: str, args: dict, result: dict):
        """观察工具执行结果"""
        if tool_name == "update_memory":
            if args.get("revealed_info"):
                self.agent_memory["revealed_info"] = args["revealed_info"]
            if args.get("tested_features"):
                self.agent_memory["tested_features"] = args["tested_features"]
            if args.get("test_questions"):
                self.agent_memory["test_questions"] = args["test_questions"]

        if tool_name == "new_session":
            self.conversation_memory = []

        # 所有工具调用结果都记录到对话记忆，让 LLM 知道自己做了什么
        if tool_name == "chat":
            self.conversation_memory.append(
                {
                    "role": "user",
                    "content": args.get("message", ""),
                }
            )
            if result.get("success"):
                reply = result.get("reply", "")
                self.conversation_memory.append(
                    {
                        "role": "assistant",
                        "content": reply[:500],
                    }
                )
                if len(self.conversation_memory) > self.max_memory_length:
                    self.conversation_memory = self.conversation_memory[
                        -self.max_memory_length :
                    ]
        else:
            # 非 chat 工具也记录，让 LLM 知道自己执行了什么操作
            result_preview = json.dumps(result, ensure_ascii=False)[:200]
            self.conversation_memory.append(
                {
                    "role": "system_result",
                    "content": f"[执行 {tool_name}] 结果: {result_preview}",
                }
            )
            if len(self.conversation_memory) > self.max_memory_length:
                self.conversation_memory = self.conversation_memory[
                    -self.max_memory_length :
                ]

    def _build_prompt(self) -> str:
        memory_str = json.dumps(self.agent_memory, ensure_ascii=False, indent=2)
        return SYSTEM_PROMPT + f"\n\n## 你当前的记忆\n```json\n{memory_str}\n```"

    def _build_user_message(self) -> str:
        history_str = ""
        if self.conversation_memory:
            for h in self.conversation_memory:
                role = h.get("role", "unknown")
                content = h.get("content", "")
                if role == "user":
                    history_str += f"\n你发消息: {content}"
                elif role == "assistant":
                    history_str += f"\nAI回复: {content}"
                elif role == "system_result":
                    history_str += f"\n{content}"

        return f"""当前轮次: {self.round}

## 你之前的操作和对话（按时间顺序）
{history_str or "（这是第一轮，你还没做任何操作）"}

请根据上面的历史记录决定下一步。不要重复已经做过的操作。"""

    def get_status(self) -> dict:
        return {
            "round": self.round,
            "agent_memory": self.agent_memory,
        }
