from app.llm.gemini_adapter import GeminiAdapter
from app.tools.registry import ToolRegistry
from google.genai import types
from app.exceptions import AgentMaxIterationsExceeded
from app.repositories.conversation_repository import ConversationRepository
from sqlalchemy.orm import Session


class AgentService:
    def __init__(
        self,
        llm: GeminiAdapter,
        tool_registry: ToolRegistry,
        repository: ConversationRepository,
        session: Session,
        max_iterations: int = 5,
    ):
        self.llm = llm
        self.tool_registry = tool_registry
        self.repository = repository
        self.session = session
        self.max_iterations = max_iterations
        self.config = types.GenerateContentConfig(
            tools=list(self.tool_registry.get_all().values()),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True
            ),
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode="AUTO")
            ),
        )

    def _generate_response(self, history):
        print("🔍 Tool config:", self.config.tool_config)
        print("🔍 Tools:", self.config.tools)
        response = self.llm.client.models.generate_content(
            model=self.llm.model, contents=history, config=self.config
        )
        print("🔍 Raw response:", response)
        return response

    def _execute_tools(self, function_calls) -> list[types.Part]:
        tools_results = []
        if function_calls:
            for function_call in function_calls:
                tool = self.tool_registry.get(function_call.name)
                result = tool(**function_call.args)

                tool_result = types.Part.from_function_response(
                    name=function_call.name,
                    response={"tool_result": result},
                )
                tools_results.append(tool_result)
        return tools_results

    def run(self, message: str, conversation_id: int | None = None) -> tuple[str, int]:
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

        history.append(
            types.Content(role="user", parts=[types.Part.from_text(text=message)])
        )

        for i in range(self.max_iterations):
            response = self._generate_response(history)

            if not response.function_calls:
                history.append(response.candidates[0].content)

                try:
                    self.repository.add_message(conversation_id, "user", message)
                    self.repository.add_message(conversation_id, "model", response.text)
                    self.session.commit()
                except Exception:
                    self.session.rollback()
                    raise

                return response.text, conversation_id

            if i == self.max_iterations - 1:
                self.session.rollback()
                raise AgentMaxIterationsExceeded("Maximum iterations reached.")

            tool_results = self._execute_tools(response.function_calls)

            history.append(response.candidates[0].content)
            history.append(types.Content(role="user", parts=tool_results))
