from dataclasses import dataclass

@dataclass
class Message:
    role: str
    content: str
    timestamp: int

@dataclass
class Conversation:
    session_id: str
    messages: list[Message]
    updated_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "messages": [
                {"role":m.role, "content":m.content} for m in self.messages
            ],
            "updated_at":self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Conversation":
        return cls(
            session_id=data["session_id"],
            messages = [Message(**m) for m in data["messages"]],
            updated_at = data.get("updated_at"),
        )