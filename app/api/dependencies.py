from app.db.database import SessionLocal
from app.repositories.conversation_repository import ConversationRepository
from collections.abc import Generator
from app.services.chat_service import ChatService
from app.services.agent_service import AgentService
from app.tools.registry import ToolRegistry
from app.llm.gemini_adapter import GeminiAdapter
from app.tools.time_tool import get_current_time
from app.tools.calculator_tool import calculate
from dotenv import load_dotenv
import os

load_dotenv()


def get_chat_service() -> ChatService:
    API_KEY = os.getenv("GEMINI_API_KEY")
    if not API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set in the environment variables.")
    gemini_adapter = GeminiAdapter(api_key=API_KEY)
    return ChatService(llm=gemini_adapter)


def get_agent_service() -> Generator[AgentService, None, None]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    llm = GeminiAdapter(api_key=api_key)

    tools = ToolRegistry()
    tools.register("get_current_time", get_current_time)
    tools.register("calculate", calculate)

    with SessionLocal() as session:
        repository = ConversationRepository(session)

        yield AgentService(
            llm=llm,
            tool_registry=tools,
            repository=repository,
            session=session,
        )
