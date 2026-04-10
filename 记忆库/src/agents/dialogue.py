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
            tools=tools, # 仅包含 KB 工具的原生定义
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

        # 将 dialogue_messages 格式转换为 LLM 期望的格式
        # dialogue_messages 格式: {turn, user_message, assistant_message, has_recalled}
        # LLM 期望格式: {role, content}
        if conversation_history is not None:
            llm_history = []
            for entry in conversation_history:
                if not isinstance(entry, dict):
                    continue
                user_msg = entry.get("user_message")
                if user_msg:
                    llm_history.append({"role": "user", "content": str(user_msg) if not isinstance(user_msg, str) else user_msg})
                assistant_msg = entry.get("assistant_message")
                if assistant_msg:
                    llm_history.append({"role": "assistant", "content": str(assistant_msg) if not isinstance(assistant_msg, str) else assistant_msg})
            self.conversation_history = llm_history

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
            tools=tools, # 仅包含 KB 工具的原生定义
            provider="deepseek",
            stream=True,
        )

        self._reasoning_buffer = ""
        content_buffer = ""
        self._last_content_end = 0

        tool_pattern = re.compile(
            r"\[(?:TOOL|OL):(\w+)\](.*?)\[(?:/TOOL|/OL)\]", re.DOTALL
        )
        trash_pattern = re.compile(r"\[(?:TOOL|OL):[^\]]*$")

        for content_delta, reasoning, is_final, finish_reason, tc in stream:
            # 1. 处理思考过程
            if reasoning and reasoning != self._reasoning_buffer:
                new_reasoning = reasoning[len(self._reasoning_buffer) :]
                self._reasoning_buffer = reasoning
                if new_reasoning:
                    yield {"type": "reasoning", "delta": new_reasoning}

                # 在由于流式输出，可能从思考过程提取工具并直接处理
                for event in self._extract_tool_blocks_from_reasoning():
                    yield event

            # 2. 处理回复内容
            if content_delta:
                content_buffer += content_delta

                # 开始查找完整工具块
                while True:
                    search_start = self._last_content_end
                    m = tool_pattern.search(content_buffer, search_start)

                    if m:
                        # 找到完整工具块
                        # a. 先输出工具块之前的内容
                        if m.start() > search_start:
                            yield {
                                "type": "content",
                                "delta": content_buffer[search_start : m.start()],
                            }

                        # b. 解析并输出工具调用
                        tool_name = m.group(1)
                        args_text = m.group(2).strip()
                        try:
                            args = json.loads(args_text)
                        except:
                            args = args_text

                        self._last_tool_call_id = (self._last_tool_call_id or 0) + 1
                        tool_call_dict = {
                            "type": "tool_call",
                            "tool_name": tool_name,
                            "params": args,
                            "tool_call_id": f"call_{self._last_tool_call_id}",
                        }
                        yield tool_call_dict

                        # 特殊处理 report_hits
                        if tool_name == "report_hits":
                            fps = args.get("fingerprints", []) if isinstance(args, dict) else []
                            for fp in fps:
                                self.add_pending_hit(fp)
                            yield {
                                "type": "tool_return",
                                "tool_name": tool_name,
                                "tool_call_id": tool_call_dict["tool_call_id"],
                                "result": json.dumps({"success": True, "content": "hits reported"}),
                            }

                        # c. 更新 self._last_content_end 到工具结束标记之后
                        end_tag_pos = content_buffer.find("[/TOOL]", m.end())
                        if end_tag_pos < 0:
                            end_tag_pos = content_buffer.find("[/OL]", m.end())

                        if end_tag_pos >= 0:
                            tag_len = 7 if content_buffer[end_tag_pos:end_tag_pos+7] == "[/TOOL]" else 5
                            self._last_content_end = end_tag_pos + tag_len
                        else:
                            # 理论上匹配了 pattern 就应该有结束标记，但以防万一
                            self._last_content_end = m.end()

                        # 继续查找下一个工具块
                        continue
                    else:
                        # 没找到完整工具块
                        remaining = content_buffer[search_start:]
                        if not remaining:
                            break

                        # 检查是否有未完成的工具标记 [TOOL:
                        bracket_pos = remaining.find("[")
                        if bracket_pos >= 0:
                            potential_tool = remaining[bracket_pos:]

                            # 严格判断是否是工具标签正在形成：
                            # potential_tool 是 buffer 中从 "[" 开始的内容
                            # 如果它以 "[TOOL:" 或 "[OL:" 开头，说明正在形成工具调用
                            is_tool_prefix = (
                                potential_tool.startswith("[TOOL:") or
                                potential_tool.startswith("[OL:")
                            )

                            if is_tool_prefix:
                                # 确定是工具调用，耐心缓冲，不要输出
                                if bracket_pos > 0:
                                    yield {"type": "content", "delta": remaining[:bracket_pos]}
                                    self._last_content_end = search_start + bracket_pos
                                # 保持 [ 及其后面内容在 buffer 中等待闭合标签
                                break
                            else:
                                # 明确不是我们的工具标签（比如是用户说的普通中括号）
                                yield {"type": "content", "delta": remaining}
                                self._last_content_end = len(content_buffer)
                                break
                        else:
                            # 没有 [，直接输出全部
                            yield {"type": "content", "delta": remaining}
                            self._last_content_end = len(content_buffer)
                            break

            if is_final:
                if self._last_content_end < len(content_buffer):
                    remaining = content_buffer[self._last_content_end :]

                    # 强力过滤：移除所有可能的工具标记和底层模型的原生指令
                    # 包括我们定义的 [TOOL] 和 潜在的原生标签 <|...|>
                    cleaned = trash_pattern.sub("", remaining)
                    cleaned = re.sub(r"<\|.*?\|>", "", cleaned)
                    cleaned = re.sub(r"&lt;\|.*?\|&gt;", "", cleaned) # 适配HTML转义情况

                    if cleaned.strip():
                        yield {"type": "content", "delta": cleaned}
                break

        if finish_reason == "tool_calls" and tc:
            if content_buffer:
                # 检查并清理内容缓冲（防止残留标签）
                cleaned_content = trash_pattern.sub("", content_buffer)
                if cleaned_content.strip():
                    yield {"type": "content", "delta": cleaned_content}
                content_buffer = ""

            args = tc.get("arguments", "{}")
            try:
                params = json.loads(args)
            except:
                params = args
            tool_name = tc.get("name", "")
            tool_call_id = tc.get("id", f"call_{self._last_tool_call_id or 0}")

            self._last_tool_call_id = (self._last_tool_call_id or 0) + 1

            # 手报命中工具特殊处理
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

            # 通用工具调用（包括 kb_search 等原生调用）
            yield {
                "type": "tool_call",
                "tool_name": tool_name,
                "params": params,
                "tool_call_id": tool_call_id,
            }
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

### 调用格式 (必须严格遵守文本标签格式):
1. 召回记忆: [TOOL:recall_from_keys]{{"keys": ["分类"], "query": "我想查...", "data": "时间范围(可选)"}}[/TOOL]
2. 存储新记忆: [TOOL:save_to_key]{{"key": "分类", "content": "要存的内容", "tag": "简短标签"}}[/TOOL]

⚠️ 关于 `data` 参数的重要限制（请仔细阅读）：
- 格式必须是严格的日期格式 `YYYY-MM-DD`，或日期范围 `YYYY-MM-DD至YYYY-MM-DD`。绝对不能写成"昨天"、"上周"等自然语言！
- 注意！一旦且仅当你传入了 `data` 参数，底层系统将**绕过所有分类记忆库**，直接降级为纯时间检索——它会且仅会去历史对话档案（sub）中寻找当天的原始对话记录。
- 因此，如果你需要的是系统经过消化提取后归档的结构化个人记忆，**绝对不要**传 `data` 参数！只有当你确实被要求"看看昨天具体的对话原文"时才使用。

### 示例：
用户说："我最近复习得好累" →
小林，辛苦了！让我翻一下你的复习记录 📖
[TOOL:recall_from_keys]{{"keys": ["study", "emotion"], "query": "最近的复习状态和情绪"}}[/TOOL]

用户说："记一下，我打算改考深圳大学了" →
收到！深大也是非常棒的选择，地理位置很有优势。我这就帮你更新目标院校 📍
[TOOL:save_to_key]{{"key": "study", "content": "用户改考目标为深圳大学计算机专业", "tag": "目标院校变更"}}[/TOOL]

### 绝对禁止：
- 绝对禁止使用底层模型的原生函数调用格式（如 `<｜DSML｜>` 等内部标签）！必须且只能使用约定的 `[TOOL:函数名]{...}[/TOOL]` 纯文本格式。
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
