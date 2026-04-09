from src.system.llm_client import chat_completion
from src.system.retry import call_with_retry
from src.system.config import load_config


class CompressionAgent:
    def __init__(self, event_bus=None):
        self._event_bus = event_bus
        self.system_prompt = self._build_prompt()
        self._threshold = None

    @property
    def threshold(self) -> int:
        if self._threshold is None:
            self._threshold = load_config().get("context_threshold", 150000)
        return self._threshold

    def _build_prompt(self) -> str:
        return """你是一个对话历史压缩Agent。你的职责是压缩历史对话，减少token使用。

## 压缩规则
1. 用户消息：保持完整，不压缩
2. 模型回复：压缩为摘要，保留关键信息
3. 压缩后的模型回复以"（已压缩）"标记

## 压缩方法
- 保留核心信息和结论
- 删除冗余的解释和过渡语句
- 保留具体的数字、日期、承诺等关键事实

## 输出格式
直接输出压缩后的对话历史，保持原有格式。
"""

    def format_history_for_compression(self, history: list) -> str:
        """将对话历史列表格式化为待压缩的文本"""
        lines = []
        for msg in history:
            role = msg.get("role", "")
            content = msg.get("content") or ""
            if role == "tool":
                continue
            if not content:
                continue
            role_text = "用户" if role == "user" else "助手"
            lines.append(f"{role_text}：{content}")
        return "\n".join(lines)

    def parse_compressed_history(self, text: str) -> list:
        """将压缩后的文本解析回对话历史列表"""
        result = []
        lines = text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            if line.startswith("用户："):
                content = line[3:]
                result.append({"role": "user", "content": content})
            elif line.startswith("助手（已压缩）："):
                content = line[9:]
                result.append({"role": "assistant", "content": content})
            elif line.startswith("助手："):
                content = line[3:]
                result.append({"role": "assistant", "content": content})
            i += 1
        return result

    def estimate_tokens(self, text: str) -> int:
        chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        other_chars = len(text) - chinese_chars
        return int(chinese_chars * 1.5 + other_chars)

    def should_compress(self, history: list) -> bool:
        """检查是否需要压缩"""
        if not history:
            return False
        text = self.format_history_for_compression(history)
        return self.estimate_tokens(text) > self.threshold

    def compress(self, history: list) -> list:
        """压缩对话历史列表，返回压缩后的新列表"""
        if not self.should_compress(history):
            return history

        old_len = len(history)
        text = self.format_history_for_compression(history)

        def _call():
            if self._event_bus:
                self._event_bus.emit_thinking("CompressionAgent", "compressing_history")

            response = chat_completion(
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": f"请压缩以下对话历史：\n\n{text}"},
                ],
                provider="deepseek",
            )
            return response.choices[0].message.content

        compressed_text = call_with_retry(_call)
        result = self.parse_compressed_history(compressed_text)
        new_len = len(result)

        if self._event_bus:
            self._event_bus.emit_result("CompressionAgent", {"compressed": True, "old_count": old_len, "new_count": new_len})

        return result
