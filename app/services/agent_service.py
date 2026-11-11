from app.llm.gemini_adapter import GeminiAdapter
from app.tools.registry import ToolRegistry
from google.genai import types
from app.exceptions import AgentMaxIterationsExceeded

class AgentService:
    def __init__(self, llm: GeminiAdapter, tool_registry: ToolRegistry, max_iterations: int = 5):
        self.llm = llm
        self.tool_registry = tool_registry
        self.max_iterations = max_iterations
        self.history: list[types.Content] = []
        self.config = types.GenerateContentConfig(
    tools=list(self.tool_registry.get_all().values()),
    automatic_function_calling=types.AutomaticFunctionCallingConfig(
        disable=True
    ),
    tool_config=types.ToolConfig(
        function_calling_config=types.FunctionCallingConfig(
            mode="AUTO"
        )
    )
)

    def _generate_response(self, history):
        print("🔍 Tool config:", self.config.tool_config)
        print("🔍 Tools:", self.config.tools)
        response = self.llm.client.models.generate_content(
            model=self.llm.model,
            contents=history,
            config=self.config
        )
        print("🔍 Raw response:", response)
        return response

    def _execute_tools(self, function_calls)-> list[types.Part]:
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


    def run(self, message: str) -> str:
        history = self.history.copy()
        history.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=message)]
            )
        )
        for i in range(self.max_iterations):
            response = self._generate_response(history)
            print("🔍 Function calls:", response.function_calls)

            if not response.function_calls:
                history.append(response.candidates[0].content)
                self.history = history
                return response.text

            if i == self.max_iterations - 1:
                raise AgentMaxIterationsExceeded(
                    "Maximum iterations reached."
                )

            tool_results = self._execute_tools(response.function_calls)

            history.append(response.candidates[0].content)
            history.append(
                types.Content(
                    role="user",
                    parts=tool_results
                )
            )

            
            
           