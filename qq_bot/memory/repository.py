from typing import Protocol, runtime_checkable

@runtime_checkable
class MemoryRepository(Protocol):
      """记忆存储抽象接口

      所有存储后端（JSON 文件 / SQLite / 未来可能的 Redis 等）
      只需实现这 6 个方法，MemoryManager 就能无缝切换。
      """
      async def init(self) -> None:
          """初始化存储（建表、建目录等），首次使用前调用一次"""
          ...

      async def get_messages(self, session_id: str, limit: int | None = None) -> list[dict]:
          """按时间升序返回消息列表。

          Args:
              session_id: 会话 ID，如 "group_795245301"
              limit:      None 返回全部；指定 N 则只返回最近 N 条

          Returns:
              [
                  {"role": "user", "content": "你好"},
                  {"role": "assistant", "content": "你好！"},
                  ...
              ]
              新会话（无记录）返回空列表 []

          批量追加消息，并自动截断超出部分。
          Args:
              session_id: 会话 ID
              messages:   [
                              {"role": "user", "content": "..."},
                              {"role": "assistant", "content": "..."},
                          ]
          """
          ...
    
      async def add_messages(self, session_id: str, messages: list[dict]) -> None:
          """记录新增的对话"""
          ...
    
    
      async def delete_session(self, session_id: str) -> None:
          """删除整个会话的所有记录。不存在的 session 静默成功（幂等）。"""
          ...


      async def get_message_count(self, session_id: str) -> int:
          """返回某会话的消息总数。新会话返回 0。"""
          ...


      async def close(self) -> None:
          """关闭存储连接（SQLite 需要，JSON 文件可为空实现）"""
          ...
        