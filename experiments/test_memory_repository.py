from app.db.database import SessionLocal
from app.repositories.memory_repository import MemoryRepository


def main():
    with SessionLocal() as session:
        repository = MemoryRepository(session)

        memory = repository.add_memory(
            type="decision",
            content="User selected PostgreSQL for their AI project.",
            importance=0.9,
        )

        session.commit()

        print(f"Created memory with ID: {memory.id}")

        print("\nACTIVE MEMORIES:")
        for memory in repository.get_active_memories():
            print(memory.id, memory.type, memory.content)

        repository.deactivate_memory(memory.id)
        session.commit()

        print("\nAFTER DEACTIVATION:")
        for memory in repository.get_active_memories():
            print(memory.id, memory.type, memory.content)


if __name__ == "__main__":
    main()
