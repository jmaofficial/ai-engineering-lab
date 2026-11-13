from fastapi import APIRouter, Depends, HTTPException
from google.genai.errors import APIError
from app.exceptions import AgentResponseError, AgentMaxIterationsExceeded
import logging
from app.schemas import chat as chat_schemas
from app.api.dependencies import get_agent_service
from app.services.agent_service import AgentService

router = APIRouter()


@router.post("/agent", response_model=chat_schemas.ChatResponse)
def agent(
    chat_request: chat_schemas.ChatRequest,
    service: AgentService = Depends(get_agent_service),
) -> chat_schemas.ChatResponse:

    try:
        response_text, conversation_id = service.run(
            message=chat_request.message,
            conversation_id=chat_request.conversation_id,
        )
    except APIError:
        logging.getLogger(__name__).exception("Model provider request failed")
        raise HTTPException(status_code=503, detail="Modelltjänsten kunde inte slutföra anropet. Försök igen senare.") from None
    except (AgentResponseError, AgentMaxIterationsExceeded):
        logging.getLogger(__name__).exception("Agent returned no usable answer")
        raise HTTPException(status_code=502, detail="Agenten kunde inte slutföra svaret. Analysen är inte bekräftad.") from None
    return chat_schemas.ChatResponse(
        response=response_text,
        conversation_id=conversation_id,
    )
