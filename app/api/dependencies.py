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
from app.agents.memory_agent import MemoryAgent
from app.repositories.memory_repository import MemoryRepository
from app.tools.riot_tool import RiotTools
from app.tools.analysis_tool import AnalysisTools
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
    riot = RiotTools()
    tools.register("riot_account", riot.riot_account)
    tools.register("riot_match_history", riot.riot_match_history)
    tools.register("riot_analyze_champions", riot.riot_analyze_champions)
    analysis = AnalysisTools(riot)
    tools.register("collect_match_dataset", analysis.collect_match_dataset)
    tools.register("inspect_match_dataset", analysis.inspect_match_dataset)
    tools.register("collect_more_matches", analysis.collect_more_matches)
    tools.register("analyze_match_dataset", analysis.analyze_match_dataset)

    with SessionLocal() as session:
        repository = ConversationRepository(session)

        memory_agent = MemoryAgent(llm)
        memory_repository = MemoryRepository(session)
        yield AgentService(
            llm=llm,
            tool_registry=tools,
            repository=repository,
            session=session,
            memory_repository=memory_repository,
            memory_agent=memory_agent,
        )
