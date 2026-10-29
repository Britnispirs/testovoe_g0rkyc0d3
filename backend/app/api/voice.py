import logging
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from pydantic import BaseModel

from backend.app.services.stt_service import STTService
from backend.app.services.dialog_manager import DialogManager
from backend.app.models.event import AssistantResponse
from backend.app.models.user import UserItem
from backend.app.auth import get_current_user_optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice", tags=["voice"])


class TranscribeResponse(BaseModel):
    text: str
    engine: str
    status: str = "success"


class VoiceProcessResponse(AssistantResponse):
    transcribed_text: str
    engine: str


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio_endpoint(
    audio: UploadFile = File(..., description="Аудиофайл для распознавания (webm, wav, mp3, ogg, etc.)"),
    language: str = Form(default="ru", description="Язык распознавания")
):
    try:
        audio_bytes = await audio.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Пустой аудиофайл")

        text, engine = await STTService.transcribe(
            audio_bytes=audio_bytes,
            filename=audio.filename or "audio.webm",
            content_type=audio.content_type or "audio/webm",
            language=language
        )

        if not text:
            raise HTTPException(status_code=422, detail="Не удалось распознать речь в переданном аудио")

        return TranscribeResponse(text=text, engine=engine)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in /transcribe: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка обработки звука: {str(e)}")


@router.post("/process", response_model=VoiceProcessResponse)
async def process_voice_message_endpoint(
    audio: UploadFile = File(..., description="Голосовое сообщение"),
    session_id: str = Form(default="default", description="Идентификатор сессии диалога"),
    current_user: Optional[UserItem] = Depends(get_current_user_optional),
):
    try:
        audio_bytes = await audio.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Пустой аудиофайл")

        text, engine = await STTService.transcribe(
            audio_bytes=audio_bytes,
            filename=audio.filename or "audio.webm",
            content_type=audio.content_type or "audio/webm",
            language="ru"
        )

        if not text:
            return VoiceProcessResponse(
                transcribed_text="",
                engine="none",
                reply_text="Не удалось расслышать голосовое сообщение. Попробуйте сказать четче или написать текстом.",
                voice_text="Не удалось расслышать голосовое сообщение.",
                requires_clarification=False
            )

        user_id = current_user.id if current_user else None
        assistant_res = await DialogManager.process_user_message(
            message=text,
            session_id=session_id,
            user_id=user_id,
        )

        return VoiceProcessResponse(
            transcribed_text=text,
            engine=engine,
            reply_text=assistant_res.reply_text,
            voice_text=assistant_res.voice_text,
            action=assistant_res.action,
            affected_events=assistant_res.affected_events,
            requires_clarification=assistant_res.requires_clarification
        )
    except Exception as e:
        logger.exception(f"Error in /process: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка обработки голосового запроса: {str(e)}")
