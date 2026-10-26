import io
import logging
import httpx
from typing import Optional
from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery

from bots.telegram.config import BACKEND_URL
from bots.telegram.keyboards import (
    get_main_reply_keyboard,
    get_cancel_inline_keyboard,
    get_event_action_keyboard,
)

logger = logging.getLogger(__name__)
router = Router()


async def _call_backend_chat(text: str, session_id: str) -> dict:
    url = f"{BACKEND_URL}/api/assistant/chat"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json={"message": text, "session_id": session_id})
        resp.raise_for_status()
        return resp.json()


async def _call_backend_voice(audio_bytes: bytes, filename: str, session_id: str) -> dict:
    url = f"{BACKEND_URL}/api/voice/process"
    files = {"audio": (filename, audio_bytes, "audio/ogg")}
    data = {"session_id": session_id}
    async with httpx.AsyncClient(timeout=25.0) as client:
        resp = await client.post(url, files=files, data=data)
        resp.raise_for_status()
        return resp.json()


async def _mark_event_completed(event_id: int) -> bool:
    url = f"{BACKEND_URL}/api/events/{event_id}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.patch(url, json={"is_completed": True})
        return resp.status_code == 200


async def _delete_event(event_id: int) -> bool:
    url = f"{BACKEND_URL}/api/events/{event_id}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.delete(url)
        return resp.status_code == 200


@router.message(CommandStart())
async def cmd_start(message: Message):
    text = (
        "Привет! Я умный ассистент расписания.\n\n"
        "Отправьте мне голосовое или текстовое сообщение:\n"
        "• «Поставь встречу с Михаилом завтра в 14:00»\n"
        "• «Напомни позвонить врачу сегодня в 18:30»\n"
        "• «Что у меня запланировано на сегодня?»\n"
        "• «Найди задачу про отчет»"
    )
    await message.answer(text, reply_markup=get_main_reply_keyboard())


@router.message(Command("help"))
@router.message(F.text == "❓ Помощь")
async def cmd_help(message: Message):
    text = (
        "📖 Доступные команды:\n\n"
        "📅 Встречи:\n"
        "• «Встреча с командой в пятницу в 15:00»\n"
        "• «Созвон с клиентом в 11:00»\n\n"
        "📋 Задачи и напоминания:\n"
        "• «Напомни купить кофе завтра в 9 утра»\n"
        "• «Задача: подготовить презентацию»\n\n"
        "🔍 Просмотр и поиск:\n"
        "• «Что у меня сегодня?»\n"
        "• «Планы на завтра»\n"
        "• «Найди задачу про договор»\n\n"
        "❌ Для сброса незавершенного диалога введите /cancel"
    )
    await message.answer(text)


@router.message(Command("cancel"))
@router.message(F.text.lower().in_(["отмена", "сброс", "отменить"]))
async def cmd_cancel(message: Message):
    session_id = f"tg_{message.chat.id}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"{BACKEND_URL}/api/assistant/reset-session?session_id={session_id}")
    except Exception:
        pass
    await message.answer("Контекст диалога сброшен. Чем могу помочь?", reply_markup=get_main_reply_keyboard())


@router.callback_query(F.data == "cancel_dialog")
async def cb_cancel_dialog(callback: CallbackQuery):
    session_id = f"tg_{callback.message.chat.id}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"{BACKEND_URL}/api/assistant/reset-session?session_id={session_id}")
    except Exception:
        pass
    await callback.answer("Диалог сброшен")
    if callback.message:
        await callback.message.edit_text("Действие отменено.")


@router.callback_query(F.data.startswith("done:"))
async def cb_done_event(callback: CallbackQuery):
    event_id = int(callback.data.split(":")[1])
    success = await _mark_event_completed(event_id)
    if success:
        await callback.answer("Выполнено!")
        if callback.message and callback.message.text:
            await callback.message.edit_text(f"{callback.message.text}\n\n✅ Отмечено как выполненное.")
    else:
        await callback.answer("Ошибка или запись уже завершена")


@router.callback_query(F.data.startswith("del:"))
async def cb_del_event(callback: CallbackQuery):
    event_id = int(callback.data.split(":")[1])
    success = await _delete_event(event_id)
    if success:
        await callback.answer("Удалено!")
        if callback.message:
            await callback.message.edit_text("🗑 Запись успешно удалена.")
    else:
        await callback.answer("Ошибка при удалении")


@router.message(F.text == "📅 На сегодня")
async def btn_today(message: Message):
    await _handle_user_text(message, "Что у меня запланировано на сегодня?")


@router.message(F.text == "📋 Мои задачи")
async def btn_tasks(message: Message):
    await _handle_user_text(message, "Какие у меня задачи?")


@router.message(F.text == "🤝 Мои встречи")
async def btn_meetings(message: Message):
    await _handle_user_text(message, "Какие у меня встречи?")


@router.message(F.voice)
async def handle_voice(message: Message, bot: Bot):
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    session_id = f"tg_{message.chat.id}"

    try:
        buf = io.BytesIO()
        await bot.download(message.voice, destination=buf)
        audio_bytes = buf.getvalue()

        data = await _call_backend_voice(
            audio_bytes=audio_bytes,
            filename="voice.ogg",
            session_id=session_id,
        )

        transcribed = data.get("transcribed_text", "")
        reply_text = data.get("reply_text", "")
        requires_clarification = data.get("requires_clarification", False)
        affected = data.get("affected_events") or []

        msg_body = f"🎤 Распознано: «{transcribed}»\n\n{reply_text}" if transcribed else reply_text

        kb = None
        if requires_clarification:
            kb = get_cancel_inline_keyboard()
        elif affected and len(affected) == 1:
            kb = get_event_action_keyboard(affected[0]["id"], affected[0].get("is_completed", False))

        await message.answer(msg_body, reply_markup=kb)
    except Exception as e:
        logger.exception("Voice processing error: %s", e)
        await message.answer("Не удалось обработать голосовое сообщение. Попробуйте еще раз.")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: Message):
    await _handle_user_text(message, message.text)


async def _handle_user_text(message: Message, text: str):
    session_id = f"tg_{message.chat.id}"
    try:
        data = await _call_backend_chat(text, session_id=session_id)
        reply_text = data.get("reply_text", "")
        requires_clarification = data.get("requires_clarification", False)
        affected = data.get("affected_events") or []

        kb = None
        if requires_clarification:
            kb = get_cancel_inline_keyboard()
        elif affected and len(affected) == 1:
            kb = get_event_action_keyboard(affected[0]["id"], affected[0].get("is_completed", False))

        await message.answer(reply_text, reply_markup=kb)
    except Exception as e:
        logger.exception("Text processing error: %s", e)
        await message.answer("Не удалось связаться с сервером ассистента. Проверьте запуск бэкенда.")
