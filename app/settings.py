"""Runtime limits; environment variables can override the defaults."""
import os
from dataclasses import dataclass


def positive_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


@dataclass(frozen=True)
class AgentSettings:
    memory_page_size: int = 5
    memory_max_items: int = 20
    memory_max_chars: int = 12000
    max_iterations: int = 16

    def __post_init__(self):
        if min(self.memory_page_size, self.memory_max_items,
               self.memory_max_chars, self.max_iterations) < 1:
            raise ValueError("Agent limits must be positive")

    @classmethod
    def from_env(cls):
        return cls(
            memory_page_size=positive_int("MEMORY_PAGE_SIZE", 5),
            memory_max_items=positive_int("MEMORY_MAX_ITEMS", 20),
            memory_max_chars=positive_int("MEMORY_MAX_CHARS", 12000),
            max_iterations=positive_int("AGENT_MAX_ITERATIONS", 16),
        )
