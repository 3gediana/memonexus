import json
from src.system.llm_client import chat_completion
from src.system.retry import call_with_retry
from src.system.debug import debug_print, debug_tool_call, DEBUG_MODE


ASSOCIATION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_memory_by_fingerprint",
            "description": "根据指纹获取记忆详情，必须看原文才能判断关联强度",
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
            "name": "create_edges",
            "description": "创建记忆关联边",
            "parameters": {
                "type": "object",
                "properties": {
                    "edges": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "target_fingerprint": {"type": "string"},
                                "strength": {"type": "number", "enum": [0.3, 0.6, 0.9]},
                                "reason": {"type": "string"},
                            },
                            "required": ["target_fingerprint", "strength", "reason"],
                        },
                    }
                },
                "required": ["edges"],
            },
        },
    },
]


def _get_memory_by_fingerprint_impl(fingerprints: list):
    from src.tools.query_tools import get_memory_by_fingerprint

    return get_memory_by_fingerprint(fingerprints)


class AssociationAgent:
    def __init__(self):
        self.system_prompt = self._build_prompt()
        self.tools = ASSOCIATION_TOOLS
        self.tool_handlers = {
            "get_memory_by_fingerprint": _get_memory_by_fingerprint_impl,
        }

    def _build_prompt(self) -> str:
        return """## 你的角色
你是跨领域关联引擎。你的唯一职责：判断新记忆与其他 key 下已有记忆之间是否有关联，并建边。

## 你必须做的事情
收到候选记忆列表后，你必须调用 create_edges 工具：
- 有关联 → 传入 edges 数组
- 无关联 → 传入空数组 edges: []

## 工作流程
1. 系统给你传入一批候选记忆（最多8条），每条包含 fingerprint、tag、memory 内容
2. 直接根据记忆原文判断关联强度，不需要额外查询
3. 调用 create_edges 工具建边

## 关联强度标准
- 0.9（强关联）：明显围绕同一件事
- 0.6（中关联）：同一任务背景或同一时期的相关活动
- 0.3（弱关联）：有一定联系（因果、时间相邻、主题相关）
- 不建立：完全无关

## 判断原则
- 召回导向：考虑"A被召回时，B是否也需要一起出现"
- 跨领域思维：不同 key 的记忆可能有隐含联系（学习→健康、购物→编程）
- 宁建多不建少：弱关联也比没有强

## 输出格式
直接调用 create_edges 工具，不要输出任何解释文字。

## 示例
主记忆：{"tag": "考研计划", "memory": "正在准备考研，计划报考计算机专业"}
候选：[{"fingerprint": "fp_1", "tag": "失眠", "algo_score": 0.45}]
→ 调用：create_edges([{"target_fingerprint": "fp_1", "strength": 0.6, "reason": "考研压力导致失眠"}])

主记忆：{"tag": "买键盘", "memory": "买了个机械键盘，红轴的"}
候选：[{"fingerprint": "fp_2", "tag": "晚餐", "algo_score": 0.08}]
→ 调用：create_edges([])
"""

    def process(
        self, main_memory: dict, candidates: list, event_bus=None
    ) -> list[dict]:
        context = f"主记忆：{json.dumps(main_memory, ensure_ascii=False)}\n候选记忆：{json.dumps(candidates, ensure_ascii=False)}"

        # 只给 create_edges 工具，防止模型调用 get_memory_by_fingerprint
        EDGES_ONLY = [t for t in self.tools if t["function"]["name"] == "create_edges"]

        def _call():
            if DEBUG_MODE:
                debug_print(
                    "AssociationAgent 输入",
                    {
                        "main_memory": main_memory,
                        "candidates_count": len(candidates),
                    },
                )

            if event_bus:
                event_bus.emit_thinking("AssociationAgent", "judging_associations")

            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": context},
            ]

            response = chat_completion(
                messages=messages,
                tools=EDGES_ONLY,
                provider="deepseek",
            )

            msg = response.choices[0].message if response.choices else None
            if msg and getattr(msg, "tool_calls", None):
                tool_call = msg.tool_calls[0]
                args = json.loads(tool_call.function.arguments)
                return args.get("edges", [])
            return []

        result = call_with_retry(_call)
        return result
