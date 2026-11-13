import os
from dotenv import load_dotenv

from app.llm.gemini_adapter import GeminiAdapter
from app.agents.memory_agent import MemoryAgent, Memory

load_dotenv()

llm = GeminiAdapter(api_key=os.environ["GEMINI_API_KEY"])
agent = MemoryAgent(llm)

existing_memories = [
    Memory(
        id=1,
        type="decision",
        content="User selected MySQL for their AI project.",
        importance=0.9,
    )
]

scenarios = {
    "NEW": ["User: I prefer writing Python code."],
    "DUPLICATE": ["User: I have selected MySQL for my AI project."],
    "UPDATED": [
        "User: I changed my mind. We will use PostgreSQL instead of MySQL for my AI project."
    ],
}

expected_actions = {
    "NEW": "ADD",
    "DUPLICATE": "SKIP",
    "UPDATED": "SUPERSEDE",
}

for name, messages in scenarios.items():
    print(f"\n{'=' * 50}")
    print(f"SCENARIO: {name}")

    # 1. Let Gemini analyze the messages
    result = agent.consolidate_memories(
        messages=messages,
        existing_memories=existing_memories,
    )

    print("\nLLM ACTIONS:")
    print(result.model_dump_json(indent=2))

    # 2. Apply the suggested actions
    updated_memories = agent.apply_memory_actions(
        existing_memories=existing_memories,
        consolidation=result,
    )

    print("\nUPDATED MEMORIES:")
    for memory in updated_memories:
        print(memory.model_dump_json(indent=2))

    # 3. Verify the result
    assert len(result.actions) == 1, f"{name}: Expected exactly one action"

    assert (
        result.actions[0].action == expected_actions[name]
    ), f"{name}: Unexpected action"

    if name == "NEW":
        assert len(updated_memories) == 2
        assert all(m.active for m in updated_memories)

    elif name == "DUPLICATE":
        assert len(updated_memories) == 1
        assert updated_memories[0].active

    elif name == "UPDATED":
        assert len(updated_memories) == 2
        assert updated_memories[0].active is False
        assert updated_memories[1].active is True
        assert result.actions[0].supersedes_id == 1

    print(f"\n✅ {name} PASSED!")

print("\n🎉 ALL MEMORY TESTS PASSED!")
