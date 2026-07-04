import re
from .repository import MemoryRepository
from ..ai.types import ChatMessage


class MemoryManager:
    def __init__(self, repository: MemoryRepository, max_history: int):
        self._repo = repository
        self.max_history = max_history


    async def get_history(self, session_id: str) -> list[ChatMessage]:
        rows = await self._repo.get_messages(session_id=session_id, limit=self.max_history*2)
        return [ChatMessage(**r) for r in rows]
    

    async def append(self, session_id: str, user_name: str, user_msg: str, assistant_msg: str):
        """记录对话历史到db文件中，全量覆盖"""
        await self._repo.add_messages(session_id=session_id, messages=[
            {"sender_name": user_name, "role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg},
            ])


    async def clear(self, session_id: str):
        """清除会话记忆"""
        await self._repo.delete_session(session_id=session_id)
    

    async def get_session_info(self, session_id: str) -> dict[str, int]:
        """先获取统计数量如果为0返回结果为0，有数值再统计数值"""
        msg_count = await self._repo.get_message_count(session_id=session_id)
        if msg_count == 0:
            return {"message_count": 0, "estimated_tokens": 0}
        rows = await self._repo.get_messages(session_id=session_id)
        est_tokens = sum(self._estimated_tokens(r["content"] or "") for r in rows)

        return {"message_count": msg_count, "estimated_tokens": est_tokens}


    # 暂不设限
    def trim_if_needed(self, messages: list[ChatMessage], max_token: int) -> list[ChatMessage]:
        # 循环计算所有内容长度，超出长度就从第一条对话开始删除，直到满足max_token条件
        if len(messages) <= 2:
            return messages
        
        while True:
            total = sum(self._estimated_tokens(m.content or "") for m in messages)
            if total <= max_token or len(messages) <= 2:
                break
            # 0是prompt，1是时间最早的对话记录，pop删除之后列表整体前移
            messages.pop(1)

        return messages


    def _estimated_tokens(self, text: str) -> int:
        # 区分中英文用Unicode字符范围判断,\u4e00-\u9fff 是 CJK 统一表意文字的基础区，覆盖了常用汉字。
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        non_chinese = re.sub(r'[\u4e00-\u9fff]', ' ', text)
        english_words = len(non_chinese.split())

        return int(chinese_chars * 2 + english_words * 1.3)
    
    async def get_history_by_date(
        self, session_id: str, date_str: str, limit: int | None = None,
    ) -> list[dict]:
        """按日期查询消息，返回原始 dict 列表（含 created_at）"""
        return await self._repo.get_messages_by_date(
            session_id=session_id, date_str=date_str, limit=limit,
        )

    async def close(self) -> None:
        await self._repo.close()

