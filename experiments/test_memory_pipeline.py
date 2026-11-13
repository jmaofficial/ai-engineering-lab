import os

from dotenv import load_dotenv

from app.db.database import SessionLocal
from app.llm.gemini_adapter import GeminiAdapter
from app.agents.memory_agent import MemoryAgent, Memory as MemorySchema
from app.repositories.memory_repository import MemoryRepository

load_dotenv()


def main():
    llm = GeminiAdapter(api_key=os.environ["GEMINI_API_KEY"])
    agent = MemoryAgent(llm)

    messages = [
        "User: I prefer Python over JavaScript.",
        "User: I decided to use PostgreSQL for my AI project.",
    ]

    with SessionLocal() as session:
        repository = MemoryRepository(session)

        # Load existing memories from PostgreSQL
        existing_memories = [
            MemorySchema.model_validate(
                {
                    "id": memory.id,
                    "type": memory.type,
                    "content": memory.content,
                    "importance": memory.importance,
                    "active": memory.active,
                }
            )
            for memory in repository.get_active_memories()
        ]

        # Let Gemini decide what to remember
        result = agent.consolidate_memories(
            messages=messages,
            existing_memories=existing_memories,
        )

        print("\nMEMORY ACTIONS:")
        print(result.model_dump_json(indent=2))

        # Apply changes to PostgreSQL
        repository.apply_actions(result)

        session.commit()

        print("\nACTIVE MEMORIES:")
        for memory in repository.get_active_memories():
            print(memory.id, memory.type, memory.content)


if __name__ == "__main__":
    main()
