import os
import io
import logging
from typing import Optional, Dict, Any, Tuple
import httpx

logger = logging.getLogger(__name__)

def _load_env():
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_env()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
YANDEX_API_KEY = os.environ.get("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.environ.get("YANDEX_FOLDER_ID")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")


class STTService:
    @classmethod
    async def transcribe(
        cls,
        audio_bytes: bytes,
        filename: str = "audio.webm",
        content_type: str = "audio/webm",
        language: str = "ru",
        prompt: Optional[str] = "Календарь, задачи, встречи, напоминания, расписание, дата и время."
    ) -> Tuple[Optional[str], str]:
        if not audio_bytes or len(audio_bytes) < 100:
            logger.warning("Empty or too short audio bytes provided for STT")
            return None, "none"

        groq_key = os.environ.get("GROQ_API_KEY") or GROQ_API_KEY
        if groq_key:
            text = await cls._transcribe_groq(
                audio_bytes=audio_bytes,
                filename=filename,
                content_type=content_type,
                api_key=groq_key,
                language=language,
                prompt=prompt
            )
            if text:
                return text.strip(), "groq-whisper"

        yandex_key = os.environ.get("YANDEX_API_KEY") or YANDEX_API_KEY
        yandex_folder = os.environ.get("YANDEX_FOLDER_ID") or YANDEX_FOLDER_ID
        if yandex_key and yandex_folder:
            text = await cls._transcribe_yandex(
                audio_bytes=audio_bytes,
                api_key=yandex_key,
                folder_id=yandex_folder,
                content_type=content_type
            )
            if text:
                return text.strip(), "yandex-speechkit"

        openai_key = os.environ.get("OPENAI_API_KEY") or OPENAI_API_KEY
        if openai_key:
            text = await cls._transcribe_openai(
                audio_bytes=audio_bytes,
                filename=filename,
                content_type=content_type,
                api_key=openai_key,
                language=language
            )
            if text:
                return text.strip(), "openai-whisper"

        logger.error("No STT provider succeeded or API keys are missing.")
        return None, "none"

    @classmethod
    async def _transcribe_groq(
        cls,
        audio_bytes: bytes,
        filename: str,
        content_type: str,
        api_key: str,
        language: str = "ru",
        prompt: Optional[str] = None
    ) -> Optional[str]:
        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        headers = {
            "Authorization": f"Bearer {api_key}",
        }

        safe_filename = filename or "audio.webm"
        if not any(safe_filename.endswith(ext) for ext in [".wav", ".mp3", ".ogg", ".opus", ".webm", ".m4a", ".flac"]):
            safe_filename += ".webm"

        files = {
            "file": (safe_filename, audio_bytes, content_type or "audio/webm")
        }
        data = {
            "model": "whisper-large-v3-turbo",
            "language": language,
            "response_format": "json",
            "temperature": "0.0",
        }
        if prompt:
            data["prompt"] = prompt

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, headers=headers, files=files, data=data)
                if resp.status_code == 200:
                    res_json = resp.json()
                    text = res_json.get("text", "")
                    logger.info(f"Groq Whisper STT recognized: '{text}'")
                    return text
                else:
                    logger.warning(f"Groq Whisper STT returned status {resp.status_code}: {resp.text}")
                    if "whisper-large-v3-turbo" in data["model"]:
                        data["model"] = "whisper-large-v3"
                        resp2 = await client.post(url, headers=headers, files={"file": (safe_filename, audio_bytes, content_type or "audio/webm")}, data=data)
                        if resp2.status_code == 200:
                            return resp2.json().get("text", "")
        except Exception as e:
            logger.warning(f"Groq Whisper STT call failed: {e}")
        return None

    @classmethod
    async def _transcribe_yandex(
        cls,
        audio_bytes: bytes,
        api_key: str,
        folder_id: str,
        content_type: str
    ) -> Optional[str]:
        url = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"
        headers = {
            "Authorization": f"Api-Key {api_key}",
            "x-folder-id": folder_id
        }
        audio_format = "oggopus" if "ogg" in content_type or "opus" in content_type else "lpcm"
        params = {
            "lang": "ru-RU",
            "topic": "general",
            "format": audio_format
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, headers=headers, params=params, content=audio_bytes)
                if resp.status_code == 200:
                    return resp.json().get("result", "")
                logger.warning(f"Yandex STT returned status {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.warning(f"Yandex STT call failed: {e}")
        return None

    @classmethod
    async def _transcribe_openai(
        cls,
        audio_bytes: bytes,
        filename: str,
        content_type: str,
        api_key: str,
        language: str = "ru"
    ) -> Optional[str]:
        url = "https://api.openai.com/v1/audio/transcriptions"
        headers = {
            "Authorization": f"Bearer {api_key}"
        }
        safe_filename = filename or "audio.webm"
        files = {
            "file": (safe_filename, audio_bytes, content_type or "audio/webm")
        }
        data = {
            "model": "whisper-1",
            "language": language
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, headers=headers, files=files, data=data)
                if resp.status_code == 200:
                    return resp.json().get("text", "")
                logger.warning(f"OpenAI Whisper STT returned status {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.warning(f"OpenAI Whisper STT call failed: {e}")
        return None
