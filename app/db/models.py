from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, DateTime
from datetime import datetime, timezone
from sqlalchemy import String, Text, Float, Boolean, Integer


class Base(DeclarativeBase):
    pass


class ConversationDB(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    messages: Mapped[list["MessageDB"]] = relationship(back_populates="conversation")
    last_memory_message_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )


class MessageDB(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    role: Mapped[str]
    content: Mapped[str]
    conversation: Mapped["ConversationDB"] = relationship(back_populates="messages")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(primary_key=True)

    type: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    importance: Mapped[float] = mapped_column(Float)

    active: Mapped[bool] = mapped_column(Boolean, default=True)
