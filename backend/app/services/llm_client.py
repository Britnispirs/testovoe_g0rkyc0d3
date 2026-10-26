import os
import json
import logging
import time
from datetime import date, datetime
from typing import Dict, Any, Optional
import httpx
from backend.app.services.nlu_parser import parse_user_intent

def _load_env():
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_env()

MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

_mistral_blocked_until = 0.0


async def call_mistral_llm(prompt: str) -> Optional[Dict[str, Any]]:
    global _mistral_blocked_until
    if not MISTRAL_API_KEY or time.time() < _mistral_blocked_until:
        return None

    today_str = date.today().isoformat()
    now_time = datetime.now().strftime("%H:%M")
    weekdays = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
    current_weekday = weekdays[date.today().weekday()]

    system_prompt = f"""Ты — интеллектуальный модуль распознавания намерений личного голосового ассистента.
Текущая дата: {today_str} ({current_weekday}), текущее время: {now_time}.
Твоя задача — извлечь параметры из запроса пользователя и вернуть исключительно JSON следующего формата:
{{
    "intent": "CREATE_EVENT" | "LIST_EVENTS" | "SEARCH_EVENTS" | "COMPLETE_EVENT" | "DELETE_EVENT" | "RESCHEDULE_EVENT" | "INCOMPLETE" | "CHAT" | "UNKNOWN",
    "type": "task" | "meeting" | "reminder" | null,
    "title": "название задачи/встречи без служебных слов",
    "date": "YYYY-MM-DD или null",
    "time": "HH:MM или null",
    "attendees": "имя участника или null",
    "query": "поисковый запрос при поиске/удалении/завершении",
    "is_week": false
}}
Верни только валидный JSON без markdown форматирования."""

    url = "https://api.mistral.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "mistral-small-latest",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
        "max_tokens": 150,
    }

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                return json.loads(content)
            elif resp.status_code == 429:
                _mistral_blocked_until = time.time() + 120.0
                logger.warning("Mistral API 429 rate limit exceeded. Backing off for 2 minutes.")
            else:
                logger.warning(f"Mistral API returned status {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.warning(f"Mistral API call failed: {e}. Falling back to internal NLU.")
    return None


async def call_groq_llm(prompt: str) -> Optional[Dict[str, Any]]:
    if not GROQ_API_KEY:
        return None

    today_str = date.today().isoformat()
    now_time = datetime.now().strftime("%H:%M")
    weekdays = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
    current_weekday = weekdays[date.today().weekday()]

    system_prompt = f"""Ты — интеллектуальный модуль распознавания намерений личного голосового ассистента.
Текущая дата: {today_str} ({current_weekday}), текущее время: {now_time}.
Твоя задача — классифицировать запрос пользователя и вернуть исключительно валидный JSON следующего формата:
{{
    "intent": "CREATE_EVENT" | "LIST_EVENTS" | "SEARCH_EVENTS" | "COMPLETE_EVENT" | "DELETE_EVENT" | "RESCHEDULE_EVENT" | "INCOMPLETE" | "CHAT" | "UNKNOWN",
    "type": "task" | "meeting" | "reminder" | null,
    "title": "название задачи/встречи без служебных слов и без дат/времени или null",
    "date": "YYYY-MM-DD или null",
    "time": "HH:MM или null",
    "attendees": "имя участника или null",
    "query": "поисковый запрос при поиске/удалении/завершении или null",
    "is_week": false
}}

ПРАВИЛА КЛАССИФИКАЦИИ:
1. "LIST_EVENTS": Пользователь просит показать, вывести, озвучить задачи, дела, встречи или расписание (например: "покажи задачи на сегодня мне", "какие планы", "список дел на завтра"). Укажи date: YYYY-MM-DD и type: "task"/"meeting"/null.
2. "INCOMPLETE": Пользователь назвал только время/дату или обрывок фразы без конкретного действия/названия задачи (например: "хочу в девть часов", "в 11 утра", "на завтра"). НЕ создавай событие, верни intent: "INCOMPLETE", time: "HH:MM", date: "YYYY-MM-DD или null", title: null!
3. "CHAT": Приветствия ("привет", "здравствуйте"), благодарности ("спасибо"), вопросы о возможностях ("что ты умеешь"). НЕ создавай событие!
4. "CREATE_EVENT": Создание конкретной задачи, встречи или напоминания.
   - Если указана встреча/беседа/созвон/кофе/ланч ("поставь мне беседку с моим братиком иваном на часов 11") — type: "meeting", title: "Беседка с братиком Иваном", attendees: "Иван", time: "11:00", date: "{today_str}".
   - Очищай title от служебных слов: "поставь мне", "добавь задачу", "напомни", дат и времени.
5. "COMPLETE_EVENT": Отметить задачу/встречу выполненной ("отметь отчет", "сделано").
6. "DELETE_EVENT": Удалить запись ("удали созвон с Иваном").
7. "RESCHEDULE_EVENT": Перенести запись ("перенеси на 15:00").
8. "SEARCH_EVENTS": Поиск по расписанию ("найди задачу про отчет").
Верни только JSON."""

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0",
    }
    payload = {
        "model": "qwen/qwen3.8-27b",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
        "max_tokens": 150,
    }

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                return json.loads(content)
            else:
                logger.warning(f"Groq API returned status {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.warning(f"Groq API call failed: {e}")
    return None


async def parse_query_with_llm_or_fallback(text: str) -> Dict[str, Any]:
    if GROQ_API_KEY:
        llm_res = await call_groq_llm(text)
        if llm_res and "intent" in llm_res:
            return llm_res

    if MISTRAL_API_KEY:
        llm_res = await call_mistral_llm(text)
        if llm_res and "intent" in llm_res:
            return llm_res

    return parse_user_intent(text)
