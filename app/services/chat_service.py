from app.llm.base import BaseLLM

class ChatService:
    def __init__(self, llm: BaseLLM):
        self.llm = llm

    def chat(self, message: str) -> str:
        return self.llm.generate(prompt=message)



