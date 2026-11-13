from fastapi import APIRouter, Depends
from app.schemas import chat as chat_schemas
from app.api.dependencies import get_agent_service
from app.services.agent_service import AgentService

router = APIRouter()


@router.post("/agent", response_model=chat_schemas.ChatResponse)
def agent(
    chat_request: chat_schemas.ChatRequest,
    service: AgentService = Depends(get_agent_service),
) -> chat_schemas.ChatResponse:

    response_text, conversation_id = service.run(
        message=chat_request.message,
        conversation_id=chat_request.conversation_id,
    )
    print("DEBUG conversation_id:", conversation_id)
    return chat_schemas.ChatResponse(
        response=response_text,
        conversation_id=conversation_id,
    )
