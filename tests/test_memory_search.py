import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import Base
from app.repositories.memory_repository import MemoryRepository
from app.settings import AgentSettings
from app.tools.memory_tool import MemorySearch
from app.services.agent_service import AgentService, AnalysisReview
from app.tools.registry import ToolRegistry
from app.repositories.conversation_repository import ConversationRepository
from google.genai import types


class MemorySearchTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.repository = MemoryRepository(self.session)
        self.repository.add_memory("fact", "Python project", 0.8)
        self.repository.add_memory("fact", "Python tools", 0.7)
        old = self.repository.add_memory("fact", "Python obsolete", 1.0)
        old.active = False
        self.repository.add_memory("fact", "PostgreSQL database", 0.9)
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_paging_reformulation_and_reset(self):
        tool = MemorySearch(self.repository, AgentSettings(memory_page_size=1))
        first = tool.search_memories("Python")
        self.assertTrue(first["has_more"])
        second = tool.search_memories("Python")
        self.assertFalse(second["has_more"])
        self.assertNotEqual(first["memories"][0]["id"], second["memories"][0]["id"])
        self.assertEqual(tool.search_memories("Python")["memories"], [])
        self.assertEqual(tool.search_memories("")["memories"][0]["content"], "PostgreSQL database")
        tool.reset()
        self.assertEqual(tool.search_memories("Python"), first)

    def test_budgets_and_no_match(self):
        tool = MemorySearch(self.repository, AgentSettings(memory_max_items=1))
        self.assertEqual(tool.search_memories("absent")["status"], "query_exhausted")
        self.assertEqual(len(tool.search_memories("")["memories"]), 1)
        self.assertEqual(tool.search_memories("")["status"], "budget_exhausted")
        tool = MemorySearch(self.repository, AgentSettings(memory_max_chars=2))
        self.assertEqual(tool.search_memories("")["status"], "budget_exhausted")
        self.assertEqual(tool.used_chars, 0)

    def test_agent_calls_tool_then_asks_user_on_final_iteration(self):
        llm = Mock()
        llm.client.models.generate_content.side_effect = [
            SimpleNamespace(function_calls=[types.FunctionCall(name="search_memories", args={"query": "missing"})],
                            candidates=[SimpleNamespace(content=types.Content(role="model", parts=[
                                types.Part.from_function_call(name="search_memories", args={"query": "missing"})]))]),
            SimpleNamespace(function_calls=None, text="Vilken databas använder du?",
                            candidates=[SimpleNamespace(content=types.Content(role="model", parts=[
                                types.Part.from_text(text="Vilken databas använder du?")]))]),
        ]
        service = AgentService(llm, ToolRegistry(), ConversationRepository(self.session),
                               self.session, Mock(), self.repository, max_iterations=2)
        answer, _ = service.run("Hjälp mig med databasen")
        self.assertEqual(answer, "Vilken databas använder du?")
        final_call = llm.client.models.generate_content.call_args
        self.assertIsNone(final_call.kwargs["config"].tools)
        self.assertIn("query_exhausted", str(final_call.kwargs["contents"]))

    def test_tool_argument_error_is_returned_and_can_be_corrected(self):
        service = AgentService(Mock(), ToolRegistry(), ConversationRepository(self.session),
                               self.session, Mock(), self.repository)
        bad = types.FunctionCall(name="search_memories", args={"wrong": 1}, id="bad-call")
        result = service._execute_tools([bad])[0].function_response
        self.assertEqual(result.id, "bad-call")
        self.assertEqual(result.response['tool_result']['error'], 'Invalid tool arguments')
        good = types.FunctionCall(name="search_memories", args={"query": "Python"}, id="fixed-call")
        result = service._execute_tools([good])[0].function_response
        self.assertEqual(result.id, "fixed-call")
        self.assertEqual(len(result.response['tool_result']['memories']), 2)

    def test_unknown_or_crashing_tool_does_not_crash_agent(self):
        registry = ToolRegistry()
        def crash():
            raise RuntimeError('example internal error')
        registry.register('crash', crash)
        service = AgentService(Mock(), registry, ConversationRepository(self.session),
                               self.session, Mock(), self.repository)
        with self.assertLogs('app.services.agent_service', level='ERROR'):
            results = service._execute_tools([types.FunctionCall(name='unknown'),
                                               types.FunctionCall(name='crash')])
        self.assertIn('error', results[0].function_response.response['tool_result'])
        self.assertEqual(results[1].function_response.response['tool_result']['error'], 'Tool execution failed')

    def test_evidence_review_receives_source_code_and_rejects_bad_analysis(self):
        llm = Mock()
        llm.client.models.generate_content.return_value = SimpleNamespace(
            parsed=AnalysisReview(approved=False, feedback='Incorrect interval method'))
        service = AgentService(llm, ToolRegistry(), ConversationRepository(self.session),
                               self.session, Mock(), self.repository)
        service.calls_remaining = 3
        code = "stats.binom.interval(0.95, 10, 0.5)"
        service.tool_trace = [{'name': 'analyze_match_dataset', 'args': {'code': code},
                               'result': {'success': True, 'output': 'interval [20%,80%]'}}]
        review = service._review_analysis_answer('95% confidence interval is 20%..80%')
        self.assertFalse(review.approved)
        self.assertIn(code, llm.client.models.generate_content.call_args.kwargs['contents'])
        self.assertEqual(service.calls_remaining, 2)


if __name__ == "__main__":
    unittest.main()
