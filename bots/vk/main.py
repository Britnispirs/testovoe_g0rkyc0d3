import asyncio
import logging
import random
import sys
import httpx

from bots.vk.config import VK_TOKEN, VK_GROUP_ID, BACKEND_URL
from bots.vk.keyboards import get_vk_main_keyboard

logger = logging.getLogger(__name__)

VK_API_VERSION = "5.199"


async def vk_api_call(method: str, params: dict) -> dict:
    url = f"https://api.vk.com/method/{method}"
    params["access_token"] = VK_TOKEN
    params["v"] = VK_API_VERSION
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, data=params)
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"VK API error: {data['error']}")
        return data.get("response", {})


async def send_vk_message(peer_id: int, message: str, keyboard: str = None) -> None:
    params = {
        "peer_id": peer_id,
        "message": message,
        "random_id": random.randint(1, 2147483647),
    }
    if keyboard:
        params["keyboard"] = keyboard
    await vk_api_call("messages.send", params)


async def call_backend_chat(text: str, session_id: str) -> dict:
    url = f"{BACKEND_URL}/api/assistant/chat"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json={"message": text, "session_id": session_id})
        resp.raise_for_status()
        return resp.json()


async def call_backend_voice(audio_bytes: bytes, filename: str, session_id: str) -> dict:
    url = f"{BACKEND_URL}/api/voice/process"
    files = {"audio": (filename, audio_bytes, "audio/ogg")}
    data = {"session_id": session_id}
    async with httpx.AsyncClient(timeout=25.0) as client:
        resp = await client.post(url, files=files, data=data)
        resp.raise_for_status()
        return resp.json()


async def handle_message_new(msg: dict):
    from_id = msg.get("from_id")
    peer_id = msg.get("peer_id", from_id)
    text = (msg.get("text") or "").strip()
    attachments = msg.get("attachments") or []
    session_id = f"vk_{from_id}"
    keyboard = get_vk_main_keyboard()

    if text.lower() in ["начать", "start", "привет"]:
        welcome = (
            "Привет! Я голосовой ассистент расписания.\n\n"
            "Вы можете отправить мне текстовое или голосовое сообщение:\n"
            "• «Поставь встречу с Михаилом завтра в 14:00»\n"
            "• «Напомни позвонить врачу сегодня в 18:30»\n"
            "• «Что у меня запланировано на сегодня?»\n"
            "• «Найди задачу про отчет»"
        )
        await send_vk_message(peer_id, welcome, keyboard)
        return

    if text in ["❓ Помощь", "помощь", "/help"]:
        help_text = (
            "📖 Справка:\n\n"
            "📅 Встречи:\n"
            "• «Встреча с командой в пятницу в 15:00»\n\n"
            "📋 Задачи и напоминания:\n"
            "• «Напомни купить кофе завтра в 9 утра»\n\n"
            "🔍 Расписание:\n"
            "• «Что у меня сегодня?»\n"
            "• «Планы на завтра»"
        )
        await send_vk_message(peer_id, help_text, keyboard)
        return

    audio_msg = None
    for att in attachments:
        if att.get("type") == "audio_message":
            audio_msg = att.get("audio_message")
            break

    if audio_msg:
        audio_url = audio_msg.get("link_ogg") or audio_msg.get("link_mp3")
        if audio_url:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    audio_resp = await client.get(audio_url)
                    audio_bytes = audio_resp.content

                res = await call_backend_voice(audio_bytes, "voice.ogg", session_id)
                transcribed = res.get("transcribed_text", "")
                reply = res.get("reply_text", "")

                output = f"🎤 Распознано: «{transcribed}»\n\n{reply}" if transcribed else reply
                await send_vk_message(peer_id, output, keyboard)
                return
            except Exception as e:
                logger.exception("VK voice processing error: %s", e)
                await send_vk_message(peer_id, "Не удалось распознать голосовое сообщение.", keyboard)
                return

    if text:
        try:
            res = await call_backend_chat(text, session_id)
            reply = res.get("reply_text", "")
            await send_vk_message(peer_id, reply, keyboard)
        except Exception as e:
            logger.exception("VK text processing error: %s", e)
            await send_vk_message(peer_id, "Ошибка связи с сервером ассистента.", keyboard)


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if not VK_TOKEN or not VK_GROUP_ID:
        logger.error("VK_TOKEN and VK_GROUP_ID must be set in environment variables.")
        sys.exit(1)

    group_id = int(VK_GROUP_ID.lstrip("-"))
    logger.info("Initializing VK LongPoll for group %s...", group_id)

    lp = await vk_api_call("groups.getLongPollServer", {"group_id": group_id})
    server = lp["server"]
    key = lp["key"]
    ts = lp["ts"]

    logger.info("VK Bot successfully started and listening for messages.")

    async with httpx.AsyncClient(timeout=40.0) as client:
        while True:
            try:
                url = f"{server}?act=a_check&key={key}&ts={ts}&wait=25"
                resp = await client.get(url)
                data = resp.json()

                if "failed" in data:
                    code = data["failed"]
                    if code == 1:
                        ts = data["ts"]
                    else:
                        lp = await vk_api_call("groups.getLongPollServer", {"group_id": group_id})
                        key = lp["key"]
                        ts = lp["ts"]
                        server = lp["server"]
                    continue

                ts = data.get("ts", ts)
                updates = data.get("updates", [])

                for update in updates:
                    if update.get("type") == "message_new":
                        obj = update.get("object", {})
                        msg = obj.get("message", obj)
                        await handle_message_new(msg)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in VK LongPoll loop: %s", e)
                await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
