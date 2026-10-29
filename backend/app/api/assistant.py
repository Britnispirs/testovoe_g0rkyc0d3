from typing import Optional
from fastapi import APIRouter, Depends
from backend.app.models.event import AssistantRequest, AssistantResponse
from backend.app.models.user import UserItem
from backend.app.auth import get_current_user_optional
from backend.app.services.dialog_manager import DialogManager, SESSION_CONTEXT

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


@router.post("/chat", response_model=AssistantResponse)
async def assistant_chat_endpoint(
    req: AssistantRequest,
    current_user: Optional[UserItem] = Depends(get_current_user_optional),
):
    user_id = current_user.id if current_user else None
    return await DialogManager.process_user_message(
        message=req.message,
        session_id=req.session_id or "default",
        user_id=user_id,
    )


@router.post("/reset-session")
def reset_session_endpoint(session_id: str = "default"):
    if session_id in SESSION_CONTEXT:
        del SESSION_CONTEXT[session_id]
    return {"status": "session_reset", "session_id": session_id}
