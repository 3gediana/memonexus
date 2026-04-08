"""DialogueAgent - 对话代理

负责与用户对话，决定是直接回复还是召回记忆。
支持多轮tool-use循环。
"""

import json
import time
from src.system.llm_client import chat_completion
from src.system.retry import call_with_retry
from src.system.context import assemble_context
from src.tools.memory_space_tools import get_memory_context_block
from src.system.logger import get_module_logger

logger = get_module_logger("dialogue")


class DialogueAgent:
    def __init__(self, all_keys: list):
        self.all_keys = all_keys
        self.conversation_history = []
        self.pending_hits = []
        self.has_recalled_flag = False
        self.current_recall_fps = []
        self.recall_blocks = []
        self._last_tool_call_id = None
        self._just_finished_recall = False
        self._compression_agent = None

    def _get_compression_agent(self):
        if self._compression_agent is None:
            from src.agents.compression import CompressionAgent

            self._compression_agent = CompressionAgent()
        return self._compression_agent

    def _maybe_compress(self):
        """检查并压缩对话历史"""
        agent = self._get_compression_agent()
        if agent.should_compress(self.conversation_history):
            old_len = len(self.conversation_history)
            self.conversation_history = agent.compress(self.conversation_history)
            logger.info(
                f"[Compression] 压缩对话历史: {old_len} -> {len(self.conversation_history)} 条"
            )

    def receive_message(
        self, message: str = None, conversation_history: list = None
    ) -> dict:
        """接收用户消息，决定回复还是召回"""
        if conversation_history is not None:
            self.conversation_history = list(conversation_history)
        if message:
            self.conversation_history.append({"role": "user", "content": message})
            self._maybe_compress()

        tools = self._get_tools()
        system_prompt = self._get_system_prompt()

        response = chat_completion(
            messages=self.conversation_history,
            system=system_prompt,
            tools=tools,
            provider="deepseek",
        )

        choice = response.choices[0].message

        if choice.tool_calls:
            tool_call = choice.tool_calls[0]
            self._last_tool_call_id = tool_call.id
            args = json.loads(tool_call.function.arguments)
            return {
                "action": "tool_call",
                "tool_name": tool_call.function.name,
                "params": args,
                "tool_call_id": tool_call.id,
            }

        content = choice.content or ""
        self.conversation_history.append({"role": "assistant", "content": content})
        return {"action": "reply", "content": content}

    def generate_reply_with_context(self, context: str) -> str:
        """基于完整上下文生成回复"""
        response = chat_completion(
            messages=[{"role": "user", "content": context}],
            provider="glm",
        )
        return response.choices[0].message.content or ""

    def receive_message_streaming(
        self, message: str = None, conversation_history: list = None
    ):
        """流式接收消息，支持文本格式工具调用

        conversation_history: 外部注入的对话历史（格式 [{"role": "user"/"assistant", "content": "..."}]）。
                              如果传入，self.conversation_history 会被设置为它（不含当前 message），
                              然后当前 message 会正常 append 进去传给 LLM。
        Yields:
            {"type": "reasoning", "content": str} - 思考过程
            {"type": "content", "delta": str} - 回复片段
            {"type": "tool_call", "tool_name": str, "params": dict} - 工具调用
            {"type": "reply", "content": str} - 最终回复
        """
        import re

        # 如果外部注入了历史，先设置进去（这样 LLM 能感知完整上下文）
        if conversation_history is not None:
            self.conversation_history = list(conversation_history)

        if message:
            self.conversation_history.append({"role": "user", "content": message})
            self._maybe_compress()

        system_prompt = self._get_system_prompt(self.recall_blocks)
        memory_space_block = self._get_memory_space_block()

        # 如果刚刚完成召回（第二轮），禁用 tools 强制输出文本
        # reset_round_state() 会在 done 后清除 _just_finished_recall
        if self._just_finished_recall and self.recall_blocks:
            tools = None
        else:
            tools = self._get_tools()

        stream = chat_completion(
            messages=self.conversation_history,
            system=memory_space_block + system_prompt,
            tools=tools,
            provider="glm",
            stream=True,
        )

        reasoning_buffer = ""
        content_buffer = ""
        reasoning_phase = False
        self._last_content_end = 0
        search_start = 0

        # 用于检测工具块的模式
        tool_pattern = re.compile(r"\[TOOL:(\w+)\]")

        for content_delta, reasoning, is_final, finish_reason, tc in stream:
            # 处理reasoning
            if reasoning and reasoning != reasoning_buffer:
                reasoning_phase = True
                new_reasoning = reasoning[len(reasoning_buffer) :]
                reasoning_buffer = reasoning
                if new_reasoning:
                    yield {"type": "reasoning", "delta": new_reasoning}
            elif reasoning_phase and (not reasoning or reasoning == reasoning_buffer):
                reasoning_phase = False

            # 处理content（跳过 reasoning 阶段的内容）
            if content_delta and not reasoning_phase:
                content_buffer += content_delta
                search_start = self._last_content_end

                # 用正则查找工具块（从上次结束位置继续）
                for m in tool_pattern.finditer(content_buffer, search_start):
                    # 查找 [/TOOL] 结束标签
                    end_tag = content_buffer.find("[/TOOL]", m.end())
                    if end_tag < 0:
                        # [/TOOL] 还没收到，更新位置并等待下一轮
                        self._last_content_end = m.start()
                        break

                    # 输出工具块之前的文本
                    if m.start() > search_start:
                        yield {
                            "type": "content",
                            "delta": content_buffer[search_start : m.start()],
                        }

                    tool_name = m.group(1)
                    json_start = m.end()
                    json_end = end_tag
                    args_text = content_buffer[json_start:json_end].strip()
                    try:
                        args = json.loads(args_text)
                    except:
                        args = args_text

                    # report_hits 也正常 yield tool_call 事件
                    yield {
                        "type": "tool_call",
                        "tool_name": tool_name,
                        "params": args,
                        "tool_call_id": f"text_call_{self._last_tool_call_id or 0}",
                    }
                    self._last_tool_call_id = (self._last_tool_call_id or 0) + 1
                    if tool_name == "report_hits":
                        fps = (
                            args.get("fingerprints", [])
                            if isinstance(args, dict)
                            else []
                        )
                        for fp in fps:
                            self.add_pending_hit(fp)
                    search_start = end_tag + len("[/TOOL]")
                    self._last_content_end = search_start
                else:
                    # for 循环正常结束（没有 break），说明没有未闭合的工具块
                    # 实时输出新增的内容
                    new_content = content_buffer[search_start:]
                    if new_content:
                        yield {
                            "type": "content",
                            "delta": new_content,
                        }
                        self._last_content_end = len(content_buffer)

            if is_final:
                # 只在有未闭合工具块时输出剩余内容（for循环break的情况）
                # 正常流程下 for-else 已输出所有内容，remaining 为空
                if self._last_content_end < len(content_buffer):
                    remaining = content_buffer[self._last_content_end :]
                    if remaining:
                        yield {"type": "content", "delta": remaining}
                break

        # 处理 function calling 结束（不是文本格式工具块）
        if finish_reason == "tool_calls" and tc:
            # 先输出剩余的文本内容
            if content_buffer:
                yield {"type": "content", "delta": content_buffer}
                content_buffer = ""

            args = tc.get("arguments", "{}")
            try:
                params = json.loads(args)
            except:
                params = args
            tool_name = tc.get("name", "")
            tool_call_id = tc.get("id", f"call_{self._last_tool_call_id or 0}")

            self._last_tool_call_id = (self._last_tool_call_id or 0) + 1
            if tool_name == "report_hits":
                fps = params.get("fingerprints", []) if isinstance(params, dict) else []
                for fp in fps:
                    self.add_pending_hit(fp)
                # report_hits 已处理，退出流式循环，由 main.py 执行工具后继续多轮对话
                return

            yield {
                "type": "tool_call",
                "tool_name": tool_name,
                "params": params,
                "tool_call_id": tool_call_id,
            }
            self._last_tool_call_id = (self._last_tool_call_id or 0) + 1
            return

        self.conversation_history.append(
            {"role": "assistant", "content": content_buffer}
        )
        yield {"type": "reply", "content": content_buffer}

    def add_pending_hit(self, fingerprint: str) -> bool:
        """添加待上报的命中指纹"""
        if fingerprint not in self.pending_hits:
            self.pending_hits.append(fingerprint)
            return True
        return False

    def get_pending_hits(self) -> list:
        """获取待上报的命中指纹"""
        return list(self.pending_hits)

    def has_recalled(self) -> bool:
        """是否已召回"""
        return self.has_recalled_flag

    def record_recall_happened(self):
        """记录召回发生"""
        self.has_recalled_flag = True
        self._just_finished_recall = True

    def set_current_recall_fps(self, fps: list):
        """设置当前召回的指纹列表"""
        self.current_recall_fps = fps

    def set_recall_blocks(self, blocks: list):
        """设置召回块"""
        self.recall_blocks = blocks

    def get_recall_blocks(self) -> list:
        """获取召回块"""
        return self.recall_blocks

    def auto_analyze_hits(self, reply: str):
        """分析回复内容，自动识别引用的记忆并添加到pending_hits"""
        if not self.recall_blocks or not reply:
            return

        reply_lower = reply.lower()
        for block in self.recall_blocks:
            fp = block.get("fingerprint", "")
            tag = block.get("tag", "")
            memory = block.get("memory", "")

            # 简单匹配：检查回复中是否提到tag或memory中的关键词
            referenced = False

            # 优先用tag匹配（tag通常更关键）
            if tag and len(tag) > 3 and tag.lower() in reply_lower:
                referenced = True
            # 检查memory中的关键片段（取前50字符）
            elif memory:
                key_phrase = memory[: min(30, len(memory))].strip()
                if len(key_phrase) > 5 and key_phrase.lower() in reply_lower:
                    referenced = True

            if referenced and fp:
                self.add_pending_hit(fp)

    def reset_round_state(self):
        """重置轮次状态"""
        self.pending_hits = []
        self.has_recalled_flag = False
        self.current_recall_fps = []
        self._last_tool_call_id = None
        self._just_finished_recall = False

    def _get_system_prompt(self, recall_blocks: list = None) -> str:
        from datetime import datetime, timedelta
        from src.system.context import format_recall_blocks

        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        today_weekday = "一二三四五六日"[now.weekday()]

        recall_section = ""
        if recall_blocks:
            recall_section = (
                f"\n\n## 当前召回的记忆\n{format_recall_blocks(recall_blocks)}\n"
            )
            # 第二轮：已召回记忆，简化提示词，直接回复
            return f"""基于以下信息回复用户：
{recall_section}"""

        # 第一轮：没有召回记忆
        return f"""你是记忆助手。

## 当前时间
今天：{today}（星期{today_weekday}）

## 记忆召回规则
当用户问及之前的信息（计划、进度、偏好、事件等）时，输出以下格式的文本来触发记忆召回（注意：这是纯文本格式，不是工具调用，系统会自动解析这段文本来执行召回）：

[TOOL:recall_from_key]{{"keys": ["关键词1", "关键词2"], "query": "具体要查的内容", "data": "日期范围"}}[/TOOL]

**data参数格式（优先使用）：**
- 单日："2026-04-04"
- 范围（用空格分隔）："2026-04-01 2026-04-06"
- 询问"昨天"、"上周"等相对时间时，需要先转换成具体日期

**当data有值时，优先从对话记录中召回，而非从记忆库召回。**

示例：
- 用户问"我昨天学了啥" → [TOOL:recall_from_key]{{"keys": ["study", "code"], "query": "昨天的学习内容", "data": "{yesterday}"}}[/TOOL]
- 用户问"上周有什么计划" → [TOOL:recall_from_key]{{"keys": ["schedule"], "query": "上周的计划安排", "data": "2026-03-31 2026-04-06"}}[/TOOL]
- 用户问"我考研准备得怎么样了" → [TOOL:recall_from_key]{{"keys": ["study", "schedule"], "query": "考研准备进度"}}[/TOOL]

## 直接回复
如果问题与之前的信息无关，直接回答即可。"""

    def _get_memory_space_block(self) -> str:
        """获取记忆空间块"""
        memory_space = get_memory_context_block()
        if memory_space:
            return f"<记忆空间>\n{memory_space}\n</记忆空间>\n"
        return ""

    def _get_tools(self) -> list:
        return [] + self._get_kb_tools()

    def _get_kb_tools(self) -> list:
        from src.tools.kb_tools import KB_TOOLS

        return KB_TOOLS

    def _get_tools_without_report_hits(self) -> list:
        """获取工具列表（不含report_hits，用于第二轮强制输出文本）"""
        tools = self._get_tools()
        return [t for t in tools if t["function"]["name"] != "report_hits"]
