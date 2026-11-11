from app.db.database import SessionLocal
from app.repositories.conversation_repository import ConversationRepository


def test_repository():
    with SessionLocal() as session:
        repo = ConversationRepository(session)

        # 1. Skapa en konversation
        conversation = repo.create_conversation()
        print("Created conversation:", conversation)

        # 2. Lägg till meddelanden
        repo.add_message(
            conversation_id=conversation.id, role="user", content="Hej! Vad är 2 + 2?"
        )

        repo.add_message(
            conversation_id=conversation.id, role="assistant", content="2 + 2 = 4!"
        )

        # 3. Spara i PostgreSQL
        session.commit()

        # 4. Hämta konversationen igen
        saved_conversation = repo.get_conversation(conversation.id)

        print("\nRetrieved conversation:")
        print(saved_conversation)

        # 5. Verifiera resultatet
        assert saved_conversation is not None
        assert len(saved_conversation.messages) == 2
        assert saved_conversation.messages[0].content == "Hej! Vad är 2 + 2?"
        assert saved_conversation.messages[1].content == "2 + 2 = 4!"

        print("\n✅ All tests passed!")


if __name__ == "__main__":
    test_repository()
