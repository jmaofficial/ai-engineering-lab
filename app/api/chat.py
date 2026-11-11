from fastapi import APIRouter, Depends
from app.api.dependencies import get_chat_service
from app.schemas import chat as chat_schemas
from app.services.chat_service import ChatService

router = APIRouter()


@router.post("/chat", response_model=chat_schemas.ChatResponse)
def chat(
    chat_request: chat_schemas.ChatRequest,
    service: ChatService = Depends(get_chat_service)
) -> chat_schemas.ChatResponse:

    response_text = service.chat(message=chat_request.message)

    return chat_schemas.ChatResponse(response=response_text)