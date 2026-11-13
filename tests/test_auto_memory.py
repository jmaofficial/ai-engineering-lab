import unittest
from unittest.mock import Mock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.agents.memory_agent import MemoryAction, MemoryConsolidation
from app.db.models import Base
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.memory_repository import MemoryRepository
from app.services.agent_service import AgentService
from app.tools.registry import ToolRegistry


class AutoMemoryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.repository = ConversationRepository(self.session)
        self.memories = MemoryRepository(self.session)
        self.agent = Mock()
        self.agent.consolidate_memories.return_value = MemoryConsolidation(
            actions=[MemoryAction(action="ADD", content="Uses Python",
                                  type="fact", importance=0.7)]
        )
        self.service = AgentService(Mock(), ToolRegistry(), self.repository,
                                    self.session, self.agent, self.memories)
        self.conversation_id = self.repository.create_conversation().id
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def add_turns(self, count):
        for _ in range(count):
            self.repository.add_message(self.conversation_id, "user", "Uses Python")
            self.repository.add_message(self.conversation_id, "model", "OK")
        self.session.commit()

    def process(self):
        self.service.update_memories(
            self.repository.get_conversation(self.conversation_id)
        )

    def test_threshold_and_persistent_checkpoint(self):
        self.add_turns(9)
        self.process()
        self.agent.consolidate_memories.assert_not_called()
        self.add_turns(1)
        self.process()
        self.session.commit()
        self.assertEqual(len(self.agent.consolidate_memories.call_args.kwargs["messages"]), 10)
        self.assertEqual(len(self.memories.get_active_memories()), 1)
        # Reload through a fresh session, as on the next HTTP request.
        self.session.close()
        self.session = Session(self.engine)
        self.repository = ConversationRepository(self.session)
        self.memories = MemoryRepository(self.session)
        self.service.repository = self.repository
        self.service.memory_repository = self.memories
        self.service.session = self.session
        self.process()
        self.agent.consolidate_memories.assert_called_once()
        self.add_turns(9)
        self.process()
        self.agent.consolidate_memories.assert_called_once()
        self.add_turns(1)
        self.process()
        self.assertEqual(self.agent.consolidate_memories.call_count, 2)

    def test_failed_actions_roll_back_memories_and_checkpoint(self):
        self.add_turns(10)
        self.agent.consolidate_memories.return_value = MemoryConsolidation(actions=[
            MemoryAction(action="ADD", content="Uses Python", type="fact", importance=0.7),
            MemoryAction(action="SUPERSEDE", content="Invalid", type="fact",
                         importance=0.7, supersedes_id=999),
        ])
        with self.assertRaises(ValueError):
            self.process()
        self.session.rollback()
        self.assertEqual(self.memories.get_active_memories(), [])
        conversation = self.repository.get_conversation(self.conversation_id)
        self.assertIsNone(conversation.last_memory_message_id)
        self.assertEqual(len(self.repository.get_messages_after(self.conversation_id, None)), 10)


if __name__ == "__main__":
    unittest.main()
