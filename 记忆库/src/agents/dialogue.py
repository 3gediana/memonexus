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
    def __init__(self, all_keys: list, event_bus=None, persona: str = None):
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
        self._persona = persona

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

    def _cleanup_kb_tool_results(self):
        """将历史对话中 KB 工具的巨大返回结果替换为占位符，防止跨轮次爆 Token"""
        kb_tools = {"kb_search", "kb_sans_search", "kb_get_chunk", "kb_get_document", "kb_index", "kb_list_indexed", "kb_get_stats"}
        call_ids_to_clean = set()
        
        for msg in self.conversation_history:
            if msg.get("role") == "assistant" and "tool_calls" in msg:
                for tc in msg["tool_calls"]:
                    if tc.get("function", {}).get("name") in kb_tools:
                        call_ids_to_clean.add(tc.get("id"))
            elif msg.get("role") == "tool" and msg.get("tool_call_id") in call_ids_to_clean:
                if msg.get("content") != "[info used cleared]":
                    msg["content"] = "[info used cleared]"

    def receive_message(
        self, message: str = None, conversation_history: list = None
    ) -> dict:
        if conversation_history is not None:
            self.conversation_history = list(conversation_history)
        if message:
            self._user_message = message
            self._load_kb_tools = self._should_load_kb_tools(message)
            self._cleanup_kb_tool_results()  # 清理上一轮的知识库沉重返回
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
            self._user_message = message
            self._load_kb_tools = self._should_load_kb_tools(message)
            self._cleanup_kb_tool_results()  # 清理上一轮的知识库沉重返回
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

        persona_block = self._get_persona_prompt()

        recall_section = ""
        if recall_blocks:
            recall_section = (
                f"\n\n## 当前召回的记忆\n{format_recall_blocks(recall_blocks)}\n"
            )
            return f"""{persona_block}基于以下信息回复用户：
{recall_section}"""

        if self._load_kb_tools:
            return self._get_kb_system_prompt()
        else:
            return self._get_recall_system_prompt(
                today, today_weekday, yesterday, self.all_keys
            )

    def _get_persona_prompt(self) -> str:
        """根据 persona 返回角色设定提示词"""
        if self._persona == "study_mentor":
            return """你是「Memonexus · 考研陪伴导师」，一位温暖、专业、富有经验的考研辅导老师。

## 你的人设
- 你不是冷冰冰的AI，你是学生备考路上最可靠的陪伴者
- 你了解考研的每一个环节：择校、复习规划、真题训练、面试准备、心态调节
- 你会记住关于这个学生的一切——学习进度、情绪状态、生活习惯、目标院校
- 你说话风格：温暖但不啰嗦，专业但不说教，像一个亦师亦友的学长/学姐

## 回复原则
- 主动关联过去的记忆来给出个性化建议（例如："你上次说高数复习到第三章了，这周进展如何？"）
- 当学生表达压力/焦虑时，先共情再给建议，不要急着讲解决方案
- 给出的学习建议要具体、可执行，不要泛泛而谈
- 适当使用 emoji 增加亲和力，但不要过度
- 如果召回了相关记忆，自然地融入回复中，让学生感受到"你真的记得我"
- 回复长度适中，不要太短（敷衍），也不要太长（信息过载）

"""  # noqa: E501
        # 默认：无额外角色设定
        return ""

    def _get_recall_system_prompt(
        self, today: str, today_weekday: str, yesterday: str, all_keys: list
    ) -> str:
        keys_str = "、".join(f'"{k}"' for k in all_keys[:20]) if all_keys else "暂无"
        persona_block = self._get_persona_prompt()
        return f"""{persona_block}你是记忆助手。

## 当前时间
今天：{today}（星期{today_weekday}）

## 可用分类
{keys_str}

## 背景便签（仅供参考的通用常识）
以下便签只是通用常识，不是用户的个人记忆。

## 记忆召回机制（最高优先级！）
你拥有一个强大的外部记忆库，里面存储了用户过去告诉你的所有个人信息。
但是，你无法直接看到这些记忆——你必须通过工具来检索。

### 何时必须调用工具（满足任一条件就必须调用）：
- 用户提到了自己的学习进度、成绩、分数
- 用户提到了自己的情绪、压力、心态
- 用户提到了自己的健康、作息、饮食
- 用户提到了自己的计划、日程、安排
- 用户提到了自己的偏好、习惯
- 用户提到了某个人（朋友、室友、家人等）
- 用户说"帮我回忆"、"你还记得吗"、"之前"等
- 用户的问题需要你了解他的背景才能回答好
- 用户自报了姓名或身份

### 调用格式（必须严格遵守）：
先用一句简短的话回应用户（让用户知道你在处理），然后紧接着输出工具调用：
[TOOL:recall_from_keys]{{"keys": ["分类1", "分类2"], "query": "用一句话描述你想查什么"}}[/TOOL]

### 示例：
用户说："我最近复习得好累" →
小林，辛苦了！让我翻一下你的复习记录 📖
[TOOL:recall_from_keys]{{"keys": ["study", "emotion"], "query": "最近的复习状态和情绪"}}[/TOOL]

用户说："帮我盘点一下底牌" →
好的，我来帮你整理一下各科的情况 📊
[TOOL:recall_from_keys]{{"keys": ["study", "schedule"], "query": "目前的学习进度和各科成绩"}}[/TOOL]

用户说："胃疼怎么办" →
胃疼可不能忽视！我先看看你的健康记录 🏥
[TOOL:recall_from_keys]{{"keys": ["health", "preference"], "query": "健康状况和饮食习惯"}}[/TOOL]

### 绝对禁止：
- 禁止在没有调用工具的情况下编造用户的个人经历
- 禁止把背景便签里的常识当作用户的个人记忆
- 禁止说"我没有你的记录"——你有记忆库，先查再说！

## 何时可以直接回复
仅当用户的问题完全不涉及个人信息时（如"1+1等于几"、"什么是微积分"），才可以直接回答。"""

    def _get_kb_system_prompt(self) -> str:
        persona_block = self._get_persona_prompt()
        return f"""{persona_block}你是记忆助手，同时具备知识库查询能力。

## 知识库
当用户询问知识库相关内容时，可以查询知识库获取信息。

## 背景便签（仅供参考的通用常识）
以下便签只是通用常识，不是用户的个人记忆。

## 记忆召回机制（重要！）
需要查询用户个人信息时，先用一句话回应用户，然后输出：
[TOOL:recall_from_keys]{{"keys": ["分类1", "分类2"], "query": "查询关键字"}}[/TOOL]
注意：
1. `keys` 数组从可用分类中挑选1-2个。
2. 也可以直接使用知识库搜索工具（如果是知识库需求）。
3. 绝对不能瞎编，必须严格根据工具返回数据。

## 直接回复
如果问题与知识库和记忆都无关，直接回答即可。"""

    def _get_memory_space_block(self) -> str:
        memory_space = get_memory_context_block()
        if memory_space:
            return f"<背景便签>\n{memory_space}\n</背景便签>\n"
        return ""

    def _get_tools(self) -> list:
        if self._load_kb_tools:
            from src.tools.kb_tools import KB_TOOLS

            return KB_TOOLS
        return []

    def _get_tools_without_report_hits(self) -> list:
        tools = self._get_tools()
        return [t for t in tools if t["function"]["name"] != "report_hits"]
