from datetime import datetime, timezone
from dataclasses import dataclass, field
@dataclass
class Message:
    id : int
    role : str
    content : str
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

@dataclass
class Conversation:
    id : int
    messages : list[Message]

