"""DialogueAgent - 对话代理

负责与用户对话，决定是直接回复还是召回记忆。
支持多轮tool-use循环。
"""

import json
import time
import uuid
from src.system.llm_client import chat_completion
from src.system.retry import call_with_retry
from src.system.context import assemble_context
from src.tools.memory_space_tools import get_memory_context_block
from src.system.logger import get_module_logger

logger = get_module_logger("dialogue")


class DialogueAgent:
    def __init__(self, all_keys: list, event_bus=None):
        self.all_keys = all_keys
        self.conversation_history = []
        self.pending_hits = []
        self.has_recalled_flag = False
        self.current_recall_fps = []
        self.recall_blocks = []
        self._last_tool_call_id = None
        self._just_finished_recall = False
        self._compression_agent = None
        self._reasoning_buffer = ""
        self._event_bus = event_bus
        self._load_kb_tools = False
        self._user_message = ""

    def _get_compression_agent(self):
        if self._compression_agent is None:
            from src.agents.compression import CompressionAgent

            self._compression_agent = CompressionAgent(event_bus=self._event_bus)
        return self._compression_agent

    def _maybe_compress(self):
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
        if conversation_history is not None:
            self.conversation_history = list(conversation_history)
        if message:
            self._user_message = message
            self._load_kb_tools = self._should_load_kb_tools(message)
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

        import re as regex_module

        tool_pattern = regex_module.compile(
            r"\[(?:TOOL|OL):(\w+)\](.*?)\[(?:/TOOL|/OL)\]", regex_module.DOTALL
        )
        m = tool_pattern.search(content)
        if m:
            tool_name = m.group(1)
            args_text = m.group(2).strip()
            try:
                args = json.loads(args_text)
            except json.JSONDecodeError:
                args = args_text
            self._last_tool_call_id = (self._last_tool_call_id or 0) + 1
            return {
                "action": "tool_call",
                "tool_name": tool_name,
                "params": args,
                "tool_call_id": f"call_{self._last_tool_call_id}",
            }

        self.conversation_history.append({"role": "assistant", "content": content})
        return {"action": "reply", "content": content}

    def generate_reply_with_context(self, context: str) -> str:
        response = chat_completion(
            messages=[{"role": "user", "content": context}],
            provider="deepseek",
        )
        return response.choices[0].message.content or ""

    def receive_message_streaming(
        self, message: str = None, conversation_history: list = None
    ):
        import re

        if conversation_history is not None:
            self.conversation_history = list(conversation_history)

        if message:
            self.conversation_history.append({"role": "user", "content": message})
            self._maybe_compress()

        system_prompt = self._get_system_prompt(self.recall_blocks)
        memory_space_block = self._get_memory_space_block()

        if self._just_finished_recall and self.recall_blocks:
            tools = None
        else:
            tools = self._get_tools()

        # 发送 DialogueAgent 思考事件
        if self._event_bus:
            self._event_bus.emit_thinking("DialogueAgent", "generating_response")

        stream = chat_completion(
            messages=self.conversation_history,
            system=memory_space_block + system_prompt,
            tools=tools,
            provider="deepseek",
            stream=True,
        )

        self._reasoning_buffer = ""
        content_buffer = ""
        reasoning_phase = False
        self._last_content_end = 0
        search_start = 0

        tool_pattern = re.compile(
            r"\[(?:TOOL|OL):(\w+)\](.*?)\[(?:/TOOL|/OL)\]", re.DOTALL
        )
        trash_pattern = re.compile(r"\[(?:TOOL|OL):[^\]]*$")

        for content_delta, reasoning, is_final, finish_reason, tc in stream:
            if reasoning and reasoning != self._reasoning_buffer:
                reasoning_phase = True
                new_reasoning = reasoning[len(self._reasoning_buffer) :]
                self._reasoning_buffer = reasoning
                if new_reasoning:
                    yield {"type": "reasoning", "delta": new_reasoning}

                for event in self._extract_tool_blocks_from_reasoning():
                    yield event
            elif reasoning_phase and (
                not reasoning or reasoning == self._reasoning_buffer
            ):
                reasoning_phase = False

            if content_delta and not reasoning_phase:
                content_buffer += content_delta
                search_start = self._last_content_end

                # Try to find and process complete tool blocks
                found_tool = False
                for m in tool_pattern.finditer(content_buffer, search_start):
                    # Found complete tool block
                    found_tool = True

                    # Output content before tool block
                    if m.start() > search_start:
                        yield {
                            "type": "content",
                            "delta": content_buffer[search_start : m.start()],
                        }

                    # Extract tool info
                    tool_name = m.group(1)
                    args_text = m.group(2).strip()
                    try:
                        args = json.loads(args_text)
                    except:
                        args = args_text

                    # Output tool call event
                    yield {
                        "type": "tool_call",
                        "tool_name": tool_name,
                        "params": args,
                        "tool_call_id": f"call_{self._last_tool_call_id or uuid.uuid4().hex[:12]}",
                    }
                    logger.debug(
                        f"[ToolParse] Found complete tool: {tool_name}, end_tag_pos={content_buffer.find('[/TOOL]', m.end())}"
                    )
                    self._last_tool_call_id = (self._last_tool_call_id or 0) + 1

                    # Handle report_hits specially
                    if tool_name == "report_hits":
                        fps = (
                            args.get("fingerprints", [])
                            if isinstance(args, dict)
                            else []
                        )
                        for fp in fps:
                            self.add_pending_hit(fp)
                        yield {
                            "type": "tool_call",
                            "tool_name": tool_name,
                            "params": args,
                            "tool_call_id": f"call_{self._last_tool_call_id - 1}",
                        }
                        yield {
                            "type": "tool_return",
                            "tool_name": tool_name,
                            "tool_call_id": f"call_{self._last_tool_call_id - 1}",
                            "result": json.dumps(
                                {"success": True, "content": "hits reported"}
                            ),
                        }

                    # Update position after tool block
                    end_tag = content_buffer.find("[/TOOL]", m.end())
                    if end_tag < 0:
                        end_tag = content_buffer.find("[/OL]", m.end())
                    if end_tag >= 0:
                        self._last_content_end = end_tag + len("[/TOOL]")
                        if content_buffer[end_tag : end_tag + 5] == "[/OL]":
                            self._last_content_end = end_tag + len("[/OL]")
                    break  # Only process first tool block

                if not found_tool:
                    # No complete tool block found - check if we're building one
                    remaining = content_buffer[search_start:]

                    # Conservative approach: check if content MIGHT be part of a tool block
                    # Any '[' could potentially start [TOOL:xxx]...[/TOOL]
                    # So we only output content that clearly cannot be part of a tool block

                    # Check if there's a '[' in the content
                    has_bracket = "[" in remaining

                    if has_bracket:
                        # Content has '[' - might be forming a tool block
                        # Only output content BEFORE the first '['
                        bracket_pos = remaining.find("[")
                        if bracket_pos > 0:
                            # Output content before '['
                            yield {
                                "type": "content",
                                "delta": remaining[:bracket_pos],
                            }
                        self._last_content_end = search_start + bracket_pos
                        logger.debug(
                            f"[ToolParse] Has bracket, waiting. buffer={remaining[:20]}"
                        )
                    else:
                        # No '[' in content, safe to output
                        if remaining:
                            yield {
                                "type": "content",
                                "delta": remaining,
                            }
                        self._last_content_end = len(content_buffer)

            if is_final:
                if self._last_content_end < len(content_buffer):
                    remaining = content_buffer[self._last_content_end :]
                    cleaned = trash_pattern.sub("", remaining)
                    if cleaned.strip():
                        yield {"type": "content", "delta": cleaned}
                break

        if finish_reason == "tool_calls" and tc:
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
                yield {
                    "type": "tool_call",
                    "tool_name": tool_name,
                    "params": params,
                    "tool_call_id": tool_call_id,
                }
                yield {
                    "type": "tool_return",
                    "tool_name": tool_name,
                    "tool_call_id": tool_call_id,
                    "result": json.dumps({"success": True, "content": "hits reported"}),
                }
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

    def _extract_tool_blocks_from_reasoning(self):
        import re as regex_module

        rb = self._reasoning_buffer
        tool_pattern = regex_module.compile(
            r"\[(?:TOOL|OL):(\w+)\](.*?)\[(?:/TOOL|/OL)\]", regex_module.DOTALL
        )

        while True:
            m = tool_pattern.search(rb)
            if not m:
                break
            prefix = rb[: m.start()]
            if prefix.strip():
                yield {"type": "content", "delta": prefix}
            tool_name = m.group(1)
            args_text = m.group(2).strip()
            try:
                args = json.loads(args_text)
            except json.JSONDecodeError as e:
                logger.warning(f"JSON decode error in tool args: {e}, using raw text")
                args = args_text
            yield {
                "type": "tool_call",
                "tool_name": tool_name,
                "params": args,
                "tool_call_id": f"call_{self._last_tool_call_id or 0}",
            }
            self._last_tool_call_id = (self._last_tool_call_id or 0) + 1
            if tool_name == "report_hits":
                fps = args.get("fingerprints", []) if isinstance(args, dict) else []
                for fp in fps:
                    self.add_pending_hit(fp)
            rb = rb[m.end() :]

        self._reasoning_buffer = rb

    def _should_load_kb_tools(self, message: str) -> bool:
        if not message:
            return False
        return "知识库" in message

    def add_pending_hit(self, fingerprint: str) -> bool:
        if fingerprint not in self.pending_hits:
            self.pending_hits.append(fingerprint)
            return True
        return False

    def get_pending_hits(self) -> list:
        return list(self.pending_hits)

    def has_recalled(self) -> bool:
        return self.has_recalled_flag

    def record_recall_happened(self):
        self.has_recalled_flag = True
        self._just_finished_recall = True

    def set_current_recall_fps(self, fps: list):
        self.current_recall_fps = fps

    def set_recall_blocks(self, blocks: list):
        self.recall_blocks = blocks

    def get_recall_blocks(self) -> list:
        return self.recall_blocks

    def auto_analyze_hits(self, reply: str):
        if not self.recall_blocks or not reply:
            return

        reply_lower = reply.lower()
        for block in self.recall_blocks:
            fp = block.get("fingerprint", "")
            tag = block.get("tag", "")
            memory = block.get("memory", "")

            referenced = False

            if tag and len(tag) > 3 and tag.lower() in reply_lower:
                referenced = True
            elif memory:
                key_phrase = memory[: min(30, len(memory))].strip()
                if len(key_phrase) > 5 and key_phrase.lower() in reply_lower:
                    referenced = True

            if referenced and fp:
                self.add_pending_hit(fp)

    def reset_round_state(self):
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
            return f"""基于以下信息回复用户：
{recall_section}"""

        if self._load_kb_tools:
            return self._get_kb_system_prompt()
        else:
            return self._get_recall_system_prompt(
                today, today_weekday, yesterday, self.all_keys
            )

    def _get_recall_system_prompt(
        self, today: str, today_weekday: str, yesterday: str, all_keys: list
    ) -> str:
        keys_str = "、".join(f'"{k}"' for k in all_keys[:20]) if all_keys else "暂无"
        return f"""你是记忆助手。

## 当前时间
今天：{today}（星期{today_weekday}）

## 可用分类
{keys_str}

## 存储记忆
仅当用户明确说与自己相关的重要信息时触发：

[TOOL:save_to_key]{{"key": "分类", "content": "内容", "tag": "标签"}}[/TOOL]

- key：从可用分类中选择最贴切的一个
- content：简要记录核心信息
- tag：可选简短标签

触发示例：用户说"我爱吃川菜"、"明天有会议"
不触发：闲聊、提问、一般性对话

## 召回记忆
用户询问之前的信息时触发：

[TOOL:recall_from_key]{{"keys": ["分类"], "query": "查询内容"}}[/TOOL]

- keys：从可用分类选择相关的（可多个）
- query：具体要查什么
- date_range：可选，日期如"{yesterday}"（昨天）或"2024-01-01至2024-01-07"

示例："我爱吃什么"→召回preference/food，"昨天学了啥"→召回study

## 直接回复
不需要存储或召回时，直接回答。"""

    def _get_kb_system_prompt(self) -> str:
        return """你是记忆助手，同时具备知识库查询能力。

## 当前时间
请根据对话上下文判断当前时间。

## 知识库查询
当用户询问知识库相关内容时，你可以使用以下工具：
- kb_search: 搜索知识库内容
- kb_get_document: 获取文档详情

## 记忆召回规则
当用户问及之前的信息时，使用 recall_from_key 工具召回记忆。

## 直接回复
如果问题与之前的记忆和知识库都无关，直接回答即可。"""

    def _get_memory_space_block(self) -> str:
        memory_space = get_memory_context_block()
        if memory_space:
            return f"<记忆空间>\n{memory_space}\n</记忆空间>\n"
        return ""

    def _get_tools(self) -> list:
        if self._load_kb_tools:
            from src.tools.kb_tools import KB_TOOLS

            return KB_TOOLS
        return []

    def _get_tools_without_report_hits(self) -> list:
        tools = self._get_tools()
        return [t for t in tools if t["function"]["name"] != "report_hits"]
