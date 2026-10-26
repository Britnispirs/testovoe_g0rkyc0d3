import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.stt_service import STTService

client = TestClient(app)


@pytest.mark.asyncio
async def test_stt_service_empty_input():
    text, engine = await STTService.transcribe(b"")
    assert text is None
    assert engine == "none"

    text2, engine2 = await STTService.transcribe(b"too_short")
    assert text2 is None
    assert engine2 == "none"


def test_api_voice_transcribe_empty():
    response = client.post(
        "/api/voice/transcribe",
        files={"audio": ("empty.wav", b"", "audio/wav")}
    )
    assert response.status_code == 400


def test_api_voice_transcribe_mocked():
    with patch.object(STTService, "transcribe", new=AsyncMock(return_value=("Поставь встречу с Иваном в 14:00", "groq-whisper"))):
        response = client.post(
            "/api/voice/transcribe",
            files={"audio": ("test.wav", b"dummy_audio_bytes_content_for_testing", "audio/wav")}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["text"] == "Поставь встречу с Иваном в 14:00"
        assert data["engine"] == "groq-whisper"


def test_api_voice_process_mocked():
    with patch.object(STTService, "transcribe", new=AsyncMock(return_value=("Что у меня сегодня?", "groq-whisper"))):
        response = client.post(
            "/api/voice/process",
            files={"audio": ("test.wav", b"dummy_audio_bytes_content_for_testing", "audio/wav")},
            data={"session_id": "test_voice_session"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["transcribed_text"] == "Что у меня сегодня?"
        assert data["engine"] == "groq-whisper"
        assert "reply_text" in data
