from sqlalchemy.orm import Session
from app.db.models import ConversationDB, MessageDB
from app.models.conversation import Message, Conversation
from sqlalchemy import select


class ConversationRepository:

    def __init__(self, session: Session):
        self.session = session

    def _to_message(self, message_db: MessageDB) -> Message:
        message: Message = Message(
            id=message_db.id,
            role=message_db.role,
            content=message_db.content,
            created_at=message_db.created_at,
        )
        return message

    def _to_conversation(self, conversation_db: ConversationDB) -> Conversation:
        messages = []
        for message in conversation_db.messages:
            messages.append(self._to_message(message))
        conversation: Conversation = Conversation(
            id=conversation_db.id, messages=messages,
            last_memory_message_id=conversation_db.last_memory_message_id,
        )
        return conversation

    def create_conversation(self) -> Conversation:
        convo_db = ConversationDB()
        self.session.add(convo_db)
        self.session.flush()
        return self._to_conversation(convo_db)

    def get_conversation(self, conversation_id: int) -> Conversation | None:
        conversation = self.session.get(ConversationDB, conversation_id)
        if conversation:
            return self._to_conversation(conversation)
        return None

    def add_message(self, conversation_id: int, role: str, content: str) -> Message:
        message_db = MessageDB(
            conversation_id=conversation_id, role=role, content=content
        )
        self.session.add(message_db)
        self.session.flush()
        return self._to_message(message_db)

    def get_messages_after(
        self,
        conversation_id: int,
        message_id: int | None,
    ):
        stmt = select(MessageDB).where(
            MessageDB.conversation_id == conversation_id,
            MessageDB.role == "user",
        )

        if message_id is not None:
            stmt = stmt.where(MessageDB.id > message_id)

        stmt = stmt.order_by(MessageDB.id)

        return list(self.session.scalars(stmt).all())

    def update_memory_checkpoint(self, conversation_id: int, message_id: int) -> None:
        conversation = self.session.get(ConversationDB, conversation_id)
        if conversation is None:
            raise ValueError(f"Conversation {conversation_id} not found")
        conversation.last_memory_message_id = message_id
