import json
import re
from datetime import datetime
from pathlib import Path
from ..ai.types import ChatMessage


class MemoryManager:
    def __init__(self, max_history: int, data_dir: Path):
        self.max_history = max_history
        self._data_dir = data_dir


    def _get_file_path(self, session_id: str) -> Path:
        # pathlib语法糖拼接路径，就和os.path.join()
        return self._data_dir / "ai_chat" / "conversations"/ f"{session_id}.json"
    

    def _ensure_dir(self):
        # dummy是session_id占位符填什么都无所谓，.parent会将文件名去除，然后检查文件夹是否存在
        self._get_file_path("dummy").parent.mkdir(parents=True, exist_ok=True)


    def get_history(self, session_id: str) -> list[ChatMessage]:
        file_path = self._get_file_path(session_id)
        if not file_path.exists():
            # 文件不存在说明是新对话
            return []
        # 采用pathlib写法read_text就相当于对pathlib对象with open read
        history = json.loads(file_path.read_text(encoding="UTF-8"))

        return [ChatMessage(**m) for m in history["messages"]]
    

    def append(self, session_id: str, user_msg: str, assistant_msg: str):
        """
        记录对话历史到json文件中，全量覆盖
        """
        self._ensure_dir()
        file_path = self._get_file_path(session_id)
        # 存在记录就读取，不存在就创建新的对话记录对象
        if file_path.exists():
            data = json.loads(file_path.read_text(encoding="UTF-8"))
        else:
            data = {"session_id": session_id, "messages": []}

        data["messages"].append({"role": "user", "content": user_msg})
        data["messages"].append({"role": "assistant", "content": assistant_msg})
        data["updated_at"] = datetime.now().isoformat()

        # 如果messages长度超过设定上限的两倍，前面的聊天记录部分就会被截断，不保存，这样可以保证这个文件不会无限增长
        if len(data["messages"]) > self.max_history * 2:
            data["messages"] = data["messages"][-(self.max_history * 2):]
        # 写回文件中，全量覆盖
        file_path.write_text(json.dumps(data, ensure_ascii=False, indent = 2), encoding="UTF-8")


    def clear(self, session_id: str):
        """
        删除聊天记录文件，让ai失忆
        """
        self._ensure_dir()
        file = self._get_file_path(session_id)
        file.unlink(missing_ok=True)
    

    def get_session_info(self, session_id: str) -> dict[str, int]:
        self._ensure_dir()
        file_path = self._get_file_path(session_id)

        if file_path.exists():
            data = json.loads(file_path.read_text(encoding="UTF-8"))["messages"]
        else:
            # 直接返回None，调用方容易出问题，直接返回双0
            return {"message_count": 0, "estimated_tokens": 0}
        
        msg_count = len(data)
        # 将messages中的消息遍历计算大致token数量
        est_tokens = 0
        for i in data:
            est_tokens += self._estimated_tokens(i["content"])

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

