from google import genai
from google.genai import types
from app.services.agent_service import AgentService
from app.tools.time_tool import get_current_time
from app.tools.calculator_tool import calculate
from app.tools.registry import ToolRegistry
from dotenv import load_dotenv
import os

load_dotenv()
from app.llm.gemini_adapter import GeminiAdapter

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = "gemini-3.5-flash-lite"

adapter = GeminiAdapter(api_key=API_KEY, model=MODEL)
tool_registry = ToolRegistry()
tool_registry.register("get_current_time", get_current_time)
tool_registry.register("calculate", calculate)

agent = AgentService(llm=adapter, tool_registry=tool_registry, max_iterations=5)
agent.run("My name is Johan.")
response = agent.run("What is my name?")
print(response)
#
# client = genai.Client(api_key=API_KEY)
# tool_registry = ToolRegistry()
# tool_registry.register("get_current_time", get_current_time)
# tool_registry.register("calculate", calculate)
#
#
# prompt = "What is 6 multiplied by 7?"
# config = types.GenerateContentConfig(
#    tools=[
#        tool_registry.get("get_current_time"),
#        tool_registry.get("calculate")
#    ],
#    automatic_function_calling=types.AutomaticFunctionCallingConfig(
#        disable=True
#    )
# )
#
# response = client.models.generate_content(
#    model=MODEL,
#    contents=prompt,
#    config=config
# )
# function_call = response.function_calls[0] if response.function_calls else None
#
#
# if function_call:
#    tool = tool_registry.get(function_call.name)
#    result = tool(**function_call.args)
#
#
#
#
# tool_result = types.Part.from_function_response(
#    name=function_call.name,
#    response={"tool_result": result},
#
# )
#
# response2 = client.models.generate_content(
#    model=MODEL,
#    contents=[
#        types.Content(
#            role="user",
#            parts=[types.Part.from_text(
#                text=prompt
#            )]
#        ),
#        response.candidates[0].content,
#        types.Content(
#            role="user",
#            parts=[tool_result]
#        )
#    ],
#    config=config
# )
#
# print("Final response:", response2.text)
#
#
#
#
#
# client.close()
