from sqlalchemy import select, or_
import re
from sqlalchemy.orm import Session

from app.db.models import Memory


class MemoryRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_active_memories(self) -> list[Memory]:
        stmt = select(Memory).where(Memory.active.is_(True))
        return list(self.session.scalars(stmt).all())

    def search_memories(self, query: str, excluded_ids: set[int], limit: int) -> list[Memory]:
        stmt = select(Memory).where(Memory.active.is_(True))
        words = list(dict.fromkeys(re.findall(r"\w+", query)))[:20]
        if words:
            stmt = stmt.where(or_(*(Memory.content.icontains(word, autoescape=True)
                                   for word in words)))
        if excluded_ids:
            stmt = stmt.where(Memory.id.not_in(excluded_ids))
        stmt = stmt.order_by(Memory.importance.desc(), Memory.id).limit(limit)
        return list(self.session.scalars(stmt).all())

    def add_memory(
        self,
        type: str,
        content: str,
        importance: float,
    ) -> Memory:
        memory = Memory(
            type=type,
            content=content,
            importance=importance,
            active=True,
        )

        self.session.add(memory)
        self.session.flush()

        return memory

    def deactivate_memory(self, memory_id: int) -> None:
        memory = self.session.get(Memory, memory_id)

        if memory is None:
            raise ValueError(f"Memory {memory_id} not found")

        memory.active = False

    from app.agents.memory_agent import MemoryConsolidation

    def apply_actions(self, consolidation: MemoryConsolidation) -> None:
        for action in consolidation.actions:

            if action.action == "SKIP":
                continue

            if action.action == "SUPERSEDE":
                if action.supersedes_id is None:
                    raise ValueError("SUPERSEDE requires supersedes_id")

                old_memory = self.session.get(Memory, action.supersedes_id)

                if old_memory is None or not old_memory.active:
                    raise ValueError(f"Invalid supersedes_id: {action.supersedes_id}")

                old_memory.active = False

            if action.action in ("ADD", "SUPERSEDE"):
                self.add_memory(
                    type=action.type,
                    content=action.content,
                    importance=action.importance,
                )
