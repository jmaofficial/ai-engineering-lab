from typing import Literal

from pydantic import BaseModel, Field
from google.genai import types

from app.llm.gemini_adapter import GeminiAdapter


class MemoryAction(BaseModel):
    action: Literal["ADD", "SKIP", "SUPERSEDE"]
    content: str
    type: Literal["fact", "preference", "decision"]
    importance: float = Field(ge=0.0, le=1.0)
    supersedes_id: int | None = None


class MemoryConsolidation(BaseModel):
    actions: list[MemoryAction]


class Memory(BaseModel):
    id: int | None = None
    type: Literal["fact", "preference", "decision"]
    content: str
    importance: float = Field(ge=0.0, le=1.0)
    active: bool = True


class MemoryExtraction(BaseModel):
    memories: list[Memory]


class MemoryAgent:
    def __init__(self, llm: GeminiAdapter):
        self.llm = llm

        self.system_prompt = """
        You are a memory extraction agent.

        Your task is to analyze conversations and extract
        information that could be useful in future interactions.

        Extract:
        - Facts about the user or their projects.
        - User preferences.
        - Important decisions.

        Rules:
        - Only extract information explicitly supported by the conversation.
        - Do not invent information.
        - Ignore temporary or irrelevant details.
        - Avoid duplicate memories.
        - Each memory should be self-contained.
        - Return an empty list if nothing is worth remembering.

        Assign an importance score between 0.0 and 1.0:
        - 0.0–0.3: Low importance
        - 0.4–0.7: Moderate importance
        - 0.8–1.0: High importance
        """

    def extract_memories(self, messages: list[str]) -> MemoryExtraction:
        conversation = "\n".join(messages)

        response = self.llm.client.models.generate_content(
            model=self.llm.model,
            contents=conversation,
            config=types.GenerateContentConfig(
                system_instruction=self.system_prompt,
                response_mime_type="application/json",
                response_schema=MemoryExtraction,
                temperature=0.2,
            ),
        )

        if response.parsed is None:
            raise ValueError("Memory extraction failed.")

        return MemoryExtraction.model_validate(response.parsed)

    def consolidate_memories(
        self,
        messages: list[str],
        existing_memories: list[Memory],
    ) -> MemoryConsolidation:

        prompt = f"""
        Analyze the new conversation messages and compare them
        with the existing memories.

        Existing memories:
        {existing_memories}

        New messages:
        {messages}

        For each relevant piece of information, choose an action:

        ADD: New information worth remembering.
        SKIP: Information already known or not worth remembering.
        SUPERSEDE: Information that replaces an existing memory.

        Rules:
        - Do not invent information.
        - Avoid duplicate memories.
        - Only supersede memories when the new information clearly
        contradicts or updates an existing memory.
        - When superseding, provide the ID of the old memory.
        - Preserve the meaning of previous decisions.
        """

        response = self.llm.client.models.generate_content(
            model=self.llm.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=MemoryConsolidation,
                temperature=0.2,
            ),
        )

        if response.parsed is None:
            raise ValueError("Memory consolidation failed.")

        return MemoryConsolidation.model_validate(response.parsed)

    def apply_memory_actions(
        self,
        existing_memories: list[Memory],
        consolidation: MemoryConsolidation,
    ) -> list[Memory]:

        # Work on copies to avoid modifying the original memories
        memories = [memory.model_copy(deep=True) for memory in existing_memories]

        # Generate unique IDs for new memories
        next_id = (
            max(
                (memory.id for memory in memories if memory.id is not None),
                default=0,
            )
            + 1
        )

        for action in consolidation.actions:

            if action.action == "SKIP":
                continue

            if action.action == "SUPERSEDE":
                old_memory = next(
                    (
                        memory
                        for memory in memories
                        if memory.id == action.supersedes_id and memory.active
                    ),
                    None,
                )

                if action.supersedes_id is None or old_memory is None:
                    raise ValueError(f"Invalid supersedes_id: {action.supersedes_id}")

                old_memory.active = False

            if action.action in ("ADD", "SUPERSEDE"):
                new_memory = Memory(
                    id=next_id,
                    type=action.type,
                    content=action.content,
                    importance=action.importance,
                    active=True,
                )

                memories.append(new_memory)
                next_id += 1

        return memories
