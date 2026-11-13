from app.llm.gemini_adapter import GeminiAdapter
from app.tools.registry import ToolRegistry
from google.genai import types
from app.exceptions import AgentMaxIterationsExceeded, AgentResponseError
from app.repositories.conversation_repository import ConversationRepository
from sqlalchemy.orm import Session
from app.agents.memory_agent import Memory as MemorySchema
from app.agents.memory_agent import MemoryAgent
from app.repositories.memory_repository import MemoryRepository
from app.settings import AgentSettings
from app.tools.memory_tool import MemorySearch
from app.agents.instructions import AGENT_INSTRUCTIONS, REVIEW_INSTRUCTIONS
import logging
import json
import uuid
from pathlib import Path
import os
from pydantic import validate_call, ValidationError, BaseModel

logger = logging.getLogger(__name__)


class AnalysisReview(BaseModel):
    approved: bool
    feedback: str


class AgentService:
    def __init__(
        self,
        llm: GeminiAdapter,
        tool_registry: ToolRegistry,
        repository: ConversationRepository,
        session: Session,
        memory_agent: MemoryAgent,
        memory_repository: MemoryRepository,
        max_iterations: int | None = None,
        settings: AgentSettings | None = None,
    ):
        self.llm = llm
        self.tool_registry = tool_registry
        self.repository = repository
        self.session = session
        self.settings = settings or AgentSettings.from_env()
        self.max_iterations = max_iterations if max_iterations is not None else self.settings.max_iterations
        if self.max_iterations < 1:
            raise ValueError("max_iterations must be positive")
        self.memory_agent = memory_agent
        self.memory_repository = memory_repository
        self.memory_search = MemorySearch(memory_repository, self.settings)
        self.tool_trace = []
        self.trace_id = uuid.uuid4().hex
        self.reviews = []
        self.tool_registry.register("search_memories", self.memory_search.search_memories)
        self.config = types.GenerateContentConfig(
            system_instruction=AGENT_INSTRUCTIONS,
            tools=list(self.tool_registry.get_all().values()),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True
            ),
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode="AUTO")
            ),
        )

    def _generate_response(self, history, final_turn=False):
        self.calls_remaining -= 1
        response = self.llm.client.models.generate_content(
            model=self.llm.model, contents=history,
            config=(self.config.model_copy(update={"tools": None, "tool_config": None})
                    if final_turn else self.config)
        )
        return response

    def _execute_tools(self, function_calls) -> list[types.Part]:
        tools_results = []
        if function_calls:
            for function_call in function_calls:
                try:
                    tool = self.tool_registry.get(function_call.name)
                    result = validate_call(tool)(**(function_call.args or {}))
                except ValidationError as error:
                    result = {"error": "Invalid tool arguments", "details": error.errors(include_input=False, include_url=False),
                              "next_action": "Correct the arguments and call the tool again."}
                except ValueError as error:
                    result = {"error": str(error), "next_action": "Check the tool name and arguments, then correct the call."}
                except Exception:
                    logger.exception("Tool execution failed: %s", function_call.name)
                    result = {"error": "Tool execution failed", "next_action": "The operation did not succeed. Try a corrected call or disclose the failure."}
                self.tool_trace.append({"name": function_call.name, "args": function_call.args, "result": result})

                tool_result = types.Part.from_function_response(
                    name=function_call.name,
                    response={"tool_result": result},
                )
                tool_result.function_response.id = function_call.id
                tools_results.append(tool_result)
        self._save_trace()
        return tools_results

    def _save_trace(self, answer=None):
        try:
            directory = Path(os.getenv("ANALYSIS_DATA_DIR", ".analysis")) / "agent_runs"
            directory.mkdir(parents=True, exist_ok=True)
            (directory / f"{self.trace_id}.json").write_text(json.dumps(
                {"trace_id": self.trace_id, "model": self.llm.model,
                 "model_calls_remaining": getattr(self, 'calls_remaining', None),
                 "tools": self.tool_trace, "reviews": self.reviews, "answer": answer},
                ensure_ascii=False, default=str))
        except OSError:
            logger.exception("Unable to save agent execution trace")

    def _review_analysis_answer(self, answer):
        evidence = []
        for entry in self.tool_trace:
            result = entry['result']
            evidence.append({
                'tool': entry['name'],
                'analysis_code': (entry['args'] or {}).get('code'),
                'rationale': (entry['args'] or {}).get('rationale'),
                'result': ({k: v for k, v in result.items() if k not in {'columns', 'puuid'}}
                           if isinstance(result, dict) else result),
            })
        if not evidence:
            return AnalysisReview(approved=True, feedback='No tool execution to review.')
        if self.calls_remaining <= 0:
            raise AgentResponseError('No model budget remains to verify the statistical answer.')
        self.calls_remaining -= 1
        response = self.llm.client.models.generate_content(
            model=self.llm.model,
            contents=json.dumps({'candidate_answer': answer, 'tool_evidence': evidence,
                                 'model_calls_remaining': self.calls_remaining,
                                 'user_request': getattr(self, 'user_request', '')}, ensure_ascii=False),
            config=types.GenerateContentConfig(
                system_instruction=REVIEW_INSTRUCTIONS,
                response_mime_type='application/json', response_schema=AnalysisReview,
            ),
        )
        if response.parsed is None:
            raise AgentResponseError('Analysis review returned no usable result.')
        review = AnalysisReview.model_validate(response.parsed)
        self.reviews.append(review.model_dump())
        return review

    def run(
        self,
        message: str,
        conversation_id: int | None = None,
        memories: list[str] | None = None,
    ) -> tuple[str, int]:
        self.memory_search.reset()
        self.user_request = message
        self.tool_trace = []
        self.trace_id = uuid.uuid4().hex
        self.reviews = []
        self.calls_remaining = self.max_iterations
        if conversation_id is None:
            conversation = self.repository.create_conversation()
        else:
            conversation = self.repository.get_conversation(conversation_id)
            if conversation is None:
                raise ValueError(f"Conversation {conversation_id} not found")

        conversation_id = conversation.id

        history = [
            types.Content(role=msg.role, parts=[types.Part.from_text(text=msg.content)])
            for msg in sorted(conversation.messages, key=lambda m: m.id)
        ]
        history = history[-10:]
        history.append(
            types.Content(role="user", parts=[types.Part.from_text(text=message)])
        )
        if memories:
            memory_context = "\n".join(f"- {memory}" for memory in memories)

            history.insert(
                0,
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(
                            text=(
                                "Relevant information from previous conversations:\n"
                                f"{memory_context}"
                            )
                        )
                    ],
                ),
            )
        for i in range(self.max_iterations):
            needs_review = bool(self.tool_trace)
            final_turn = self.calls_remaining <= (2 if needs_review else 1)
            if final_turn:
                history.append(types.Content(role="user", parts=[types.Part.from_text(
                    text=("INTERNAL CONTROL MESSAGE, not a change of user language: tool budget reached. "
                          "Answer using available context, or ask a focused question if essential context is missing. "
                          "Follow the requested language of the ORIGINAL USER MESSAGE: " + message)
                )]))
            response = self._generate_response(history, final_turn=final_turn)

            if not response.candidates or not response.candidates[0].content:
                raise AgentResponseError("LLM returned no usable response; no analysis was completed.")

            if not response.function_calls:
                if not response.text:
                    raise AgentResponseError("LLM returned no text answer.")
                history.append(response.candidates[0].content)
                review = self._review_analysis_answer(response.text)
                if not review.approved:
                    self._save_trace()
                    if final_turn or self.calls_remaining <= 0:
                        raise AgentResponseError('Analysis did not pass evidence review: ' + review.feedback)
                    history.append(types.Content(role='user', parts=[types.Part.from_text(
                        text=('INTERNAL REVIEW, not a new user request or language preference. '
                              'Correct the analysis or disclose limitations: ' + review.feedback
                              + '\nUse the language requested by the ORIGINAL USER MESSAGE: ' + message))]))
                    continue

                try:
                    self.repository.add_message(conversation_id, "user", message)
                    self.repository.add_message(conversation_id, "model", response.text)
                    self.update_memories(conversation)
                    self.session.commit()
                except Exception:
                    self.session.rollback()
                    raise

                self._save_trace(response.text)
                return response.text, conversation_id

            if final_turn:
                self.session.rollback()
                raise AgentMaxIterationsExceeded("Maximum iterations reached.")

            tool_results = self._execute_tools(response.function_calls)

            history.append(response.candidates[0].content)
            history.append(types.Content(role="user", parts=tool_results))

    def update_memories(self, conversation):
        new_messages = self.repository.get_messages_after(
            conversation_id=conversation.id,
            message_id=conversation.last_memory_message_id,
        )

        if len(new_messages) < 10:
            return

        existing_memories = [
            MemorySchema(
                id=m.id,
                type=m.type,
                content=m.content,
                importance=m.importance,
                active=m.active,
            )
            for m in self.memory_repository.get_active_memories()
        ]

        result = self.memory_agent.consolidate_memories(
            messages=[msg.content for msg in new_messages],
            existing_memories=existing_memories,
        )

        self.memory_repository.apply_actions(result)

        checkpoint = new_messages[-1].id
        self.repository.update_memory_checkpoint(conversation.id, checkpoint)
        conversation.last_memory_message_id = checkpoint
