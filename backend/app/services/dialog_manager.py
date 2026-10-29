import re
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, List
from backend.app.models.event import (
    EventType,
    EventCreate,
    EventUpdate,
    EventItem,
    EventFilter,
    AssistantResponse,
    AssistantAction,
)
from backend.app.database import (
    db_create_event,
    db_get_event,
    db_update_event,
    db_delete_event,
    db_list_events,
    db_find_conflicts,
)
from backend.app.services.search_service import hybrid_search_events
from backend.app.services.nlu_parser import (
    parse_russian_date,
    parse_russian_time,
)
from backend.app.services.llm_client import parse_query_with_llm_or_fallback

SESSION_CONTEXT: Dict[str, Dict[str, Any]] = {}


def get_session(session_id: str) -> Dict[str, Any]:
    if session_id not in SESSION_CONTEXT:
        SESSION_CONTEXT[session_id] = {
            "last_event_id": None,
            "pending_action": None,
            "awaiting_field": None,
            "draft_event": None,
        }
    return SESSION_CONTEXT[session_id]


def format_russian_date_spoken(date_str: str) -> str:
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").date()
        today = date.today()
        if dt == today:
            return "сегодня"
        elif dt == today + timedelta(days=1):
            return "завтра"
        elif dt == today + timedelta(days=2):
            return "послезавтра"

        months = [
            "", "января", "февраля", "марта", "апреля", "мая", "июня",
            "июля", "августа", "сентября", "октября", "ноября", "декабря"
        ]
        return f"{dt.day} {months[dt.month]} {dt.year if dt.year != today.year else ''}".strip()
    except Exception:
        return date_str


class DialogManager:
    @staticmethod
    async def process_user_message(
        message: str,
        session_id: str = "default",
        user_id: Optional[int] = None,
    ) -> AssistantResponse:
        session = get_session(session_id)
        text = message.strip()

        if session.get("awaiting_field") == "title":
            target_time = session.pop("draft_time", None)
            target_date = session.pop("draft_date", None) or date.today().isoformat()
            session["awaiting_field"] = None

            parsed = await parse_query_with_llm_or_fallback(text)
            if not parsed or parsed.get("intent") in ["INCOMPLETE", "UNKNOWN"]:
                parsed = {
                    "intent": "CREATE_EVENT",
                    "type": EventType.TASK,
                    "title": text.strip()[0].upper() + text.strip()[1:] if text.strip() else text.strip(),
                    "date": target_date,
                    "time": target_time,
                    "attendees": None,
                }
            else:
                parsed["intent"] = "CREATE_EVENT"
                if target_time and not parsed.get("time"):
                    parsed["time"] = target_time
                if target_date and not parsed.get("date"):
                    parsed["date"] = target_date
                if not parsed.get("title"):
                    parsed["title"] = text.strip()[0].upper() + text.strip()[1:] if text.strip() else text.strip()

        if session.get("awaiting_field") == "time" and session.get("draft_event"):
            extracted_time = parse_russian_time(text)
            if extracted_time:
                draft = session["draft_event"]
                draft.time = extracted_time
                session["awaiting_field"] = None
                session["draft_event"] = None

                if draft.type == EventType.MEETING and draft.time:
                    conflicts = db_find_conflicts(draft.date, draft.time, user_id=user_id)
                    if conflicts:
                        conflict_name = conflicts[0].title
                        created = db_create_event(draft, user_id=user_id)
                        session["last_event_id"] = created.id
                        reply = (
                            f"Встреча «{created.title}» добавлена на {format_russian_date_spoken(created.date)} в {created.time}. "
                            f"Обратите внимание: в это же время у вас уже запланирована встреча «{conflict_name}»."
                        )
                        return AssistantResponse(
                            reply_text=reply,
                            voice_text=reply,
                            affected_events=[created],
                            action=AssistantAction(
                                action_type="CREATE_WITH_CONFLICT",
                                target_event_id=created.id,
                                conflict_event_id=conflicts[0].id,
                            ),
                        )

                created = db_create_event(draft, user_id=user_id)
                session["last_event_id"] = created.id
                time_str = f" в {created.time}" if created.time else ""
                reply = f"Отлично! Добавил встречу «{created.title}» на {format_russian_date_spoken(created.date)}{time_str}."
                return AssistantResponse(
                    reply_text=reply,
                    voice_text=reply,
                    affected_events=[created],
                    action=AssistantAction(action_type="CREATE", target_event_id=created.id),
                )
            else:
                return AssistantResponse(
                    reply_text="Пожалуйста, уточните время в формате часов и минут, например: «в 15:00» или «в 10 утра».",
                    voice_text="Пожалуйста, уточните время встречи.",
                    requires_clarification=True,
                )

        if "parsed" not in locals():
            parsed = await parse_query_with_llm_or_fallback(text)
        intent = parsed.get("intent", "UNKNOWN")

        if intent in ["CHAT", "CHAT_GREETING"]:
            reply = "Здравствуйте! Я ваш голосовой ассистент. Могу запланировать встречу, поставить задачу, найти событие или показать список дел. Чем помочь?"
            return AssistantResponse(reply_text=reply, voice_text=reply)

        if intent == "CHAT_THANKS":
            reply = "Всегда пожалуйста! Обращайтесь, если нужно что-то запланировать или напомнить."
            return AssistantResponse(reply_text=reply, voice_text=reply)

        if intent == "HELP":
            reply = (
                "Я умею:\n"
                "• Создавать задачи и встречи («Поставь встречу с Иваном в 15:00»)\n"
                "• Показывать расписание («Покажи задачи на сегодня»)\n"
                "• Отмечать выполненными («Отметь задачу отчет»)\n"
                "• Переносить события («Перенеси на завтра в 11:00»)\n"
                "• Удалять события («Удали созвон с Иваном»)"
            )
            return AssistantResponse(reply_text=reply, voice_text="Я умею управлять задачами, встречами и расписанием. Что хотите сделать?")

        if intent == "INCOMPLETE":
            target_time = parsed.get("time")
            target_date = parsed.get("date")
            session["draft_time"] = target_time
            session["draft_date"] = target_date
            session["awaiting_field"] = "title"

            time_phrase = f" в {target_time}" if target_time else ""
            date_phrase = f" на {format_russian_date_spoken(target_date)}" if target_date else ""
            reply = f"Вы указали время{time_phrase}{date_phrase}, но не уточнили, какую задачу или встречу запланировать. Что именно нужно сделать?"
            return AssistantResponse(
                reply_text=reply,
                voice_text=reply,
                requires_clarification=True,
                action=AssistantAction(
                    action_type="CLARIFY",
                    clarification_question=reply,
                ),
            )

        if intent == "COMPLETE_EVENT":
            query = parsed.get("query", "")
            target_event = None
            if query:
                found = hybrid_search_events(query, limit=3, user_id=user_id)
                if found:
                    target_event = found[0]
            elif session.get("last_event_id"):
                target_event = db_get_event(session["last_event_id"], user_id=user_id)

            if target_event:
                updated = db_update_event(target_event.id, EventUpdate(is_completed=True), user_id=user_id)
                session["last_event_id"] = updated.id
                reply = f"Готово! Задача «{updated.title}» отмечена как выполненная."
                return AssistantResponse(
                    reply_text=reply,
                    voice_text=reply,
                    affected_events=[updated],
                    action=AssistantAction(action_type="COMPLETE", target_event_id=updated.id),
                )
            return AssistantResponse(
                reply_text="Не удалось найти задачу для отметки о выполнении. Уточните название.",
                voice_text="Не нашел такую задачу. Какую задачу отметить выполненной?",
            )

        if intent == "DELETE_EVENT":
            query = parsed.get("query", "")
            target_event = None
            if query:
                found = hybrid_search_events(query, limit=3, user_id=user_id)
                if found:
                    target_event = found[0]
            elif session.get("last_event_id"):
                target_event = db_get_event(session["last_event_id"], user_id=user_id)

            if target_event:
                db_delete_event(target_event.id, user_id=user_id)
                session["last_event_id"] = None
                reply = f"Запись «{target_event.title}» успешно удалена."
                return AssistantResponse(
                    reply_text=reply,
                    voice_text=reply,
                    action=AssistantAction(action_type="DELETE", target_event_id=target_event.id),
                )
            return AssistantResponse(
                reply_text="Не нашел запись для удаления. Уточните, какую именно задачу или встречу удалить.",
                voice_text="Какую задачу или встречу удалить?",
            )

        if intent == "RESCHEDULE_EVENT":
            new_date = parsed.get("date")
            new_time = parsed.get("time")
            last_id = session.get("last_event_id")
            if last_id:
                ev = db_get_event(last_id, user_id=user_id)
                if ev:
                    update_kwargs = {}
                    if new_date:
                        update_kwargs["date"] = new_date
                    if new_time:
                        update_kwargs["time"] = new_time
                    updated = db_update_event(ev.id, EventUpdate(**update_kwargs), user_id=user_id)
                    time_info = f" на {updated.time}" if updated.time else ""
                    reply = f"Перенес «{updated.title}» на {format_russian_date_spoken(updated.date)}{time_info}."
                    return AssistantResponse(
                        reply_text=reply,
                        voice_text=reply,
                        affected_events=[updated],
                        action=AssistantAction(action_type="UPDATE", target_event_id=updated.id),
                    )
            return AssistantResponse(
                reply_text="Какую именно задачу или встречу вы хотите перенести?",
                voice_text="Какое событие нужно перенести?",
            )

        if intent == "SEARCH_EVENTS":
            query = parsed.get("query", "")
            results = hybrid_search_events(query, limit=10, user_id=user_id) if query else []

            if results:
                lines = []
                for r in results[:5]:
                    t_str = f" в {r.time}" if r.time else ""
                    type_label = "Встреча" if r.type == EventType.MEETING else ("Напоминание" if r.type == EventType.REMINDER else "Задача")
                    lines.append(f"• [{type_label}] {format_russian_date_spoken(r.date)}{t_str}: {r.title}")
                session["last_event_id"] = results[0].id
                reply = f"Нашел по запросу «{query}» ({len(results)}):\n" + "\n".join(lines)
                first = results[0]
                voice = f"Нашел запись «{first.title}» на {format_russian_date_spoken(first.date)}."
                return AssistantResponse(
                    reply_text=reply,
                    voice_text=voice,
                    affected_events=results,
                    action=AssistantAction(action_type="SEARCH"),
                )
            else:
                reply = f"По запросу «{query}» ничего не найдено."
                return AssistantResponse(reply_text=reply, voice_text=reply)

        if intent == "LIST_EVENTS":
            target_date = parsed.get("date", date.today().isoformat())
            is_week = parsed.get("is_week", False)
            raw_type = parsed.get("type")
            event_type = None
            if isinstance(raw_type, str):
                if raw_type.lower() == "meeting":
                    event_type = EventType.MEETING
                elif raw_type.lower() == "reminder":
                    event_type = EventType.REMINDER
                elif raw_type.lower() == "task":
                    event_type = EventType.TASK
            elif isinstance(raw_type, EventType):
                event_type = raw_type

            if is_week:
                today = date.today()
                end_of_week = (today + timedelta(days=6 - today.weekday())).isoformat()
                filters = EventFilter(start_date=today.isoformat(), end_date=end_of_week, type=event_type)
                period_title = "на эту неделю"
            else:
                filters = EventFilter(start_date=target_date, end_date=target_date, type=event_type)
                period_title = f"на {format_russian_date_spoken(target_date)}"

            events = db_list_events(filters, limit=25, user_id=user_id)
            if events:
                lines = []
                for e in events:
                    t_str = f"{e.time} — " if e.time else ""
                    type_icon = "📅" if e.type == EventType.MEETING else "✅"
                    lines.append(f"{type_icon} {t_str}{e.title}")
                type_desc = "встречи " if event_type == EventType.MEETING else ("задачи " if event_type == EventType.TASK else "")
                reply = f"Ваши {type_desc}планы {period_title} ({len(events)}):\n" + "\n".join(lines)
                voice = f"У вас {len(events)} событий {period_title}. Первое: {events[0].title}."
                return AssistantResponse(
                    reply_text=reply,
                    voice_text=voice,
                    affected_events=events,
                    action=AssistantAction(action_type="LIST"),
                )
            else:
                type_desc = "встреч" if event_type == EventType.MEETING else ("задач" if event_type == EventType.TASK else "событий")
                reply = f"На этот период ({period_title}) запланированных {type_desc} нет. Вы свободны!"
                return AssistantResponse(reply_text=reply, voice_text=reply)

        if intent == "CREATE_EVENT":
            raw_type = parsed.get("type")
            if isinstance(raw_type, str):
                if raw_type.lower() == "meeting":
                    event_type = EventType.MEETING
                elif raw_type.lower() == "reminder":
                    event_type = EventType.REMINDER
                else:
                    event_type = EventType.TASK
            elif isinstance(raw_type, EventType):
                event_type = raw_type
            else:
                event_type = EventType.TASK

            title = parsed.get("title") or text
            target_date = parsed.get("date") or date.today().isoformat()
            target_time = parsed.get("time")
            attendees = parsed.get("attendees")

            meaningful = [
                w for w in re.sub(r"[^\w\s]", "", title.lower()).split()
                if w not in [
                    "хочу", "надо", "нужно", "можно", "мне", "пожалуйста", "в", "на", "к", "с",
                    "бы", "ли", "давай", "поставить", "поставь", "добавь", "создай", "запиши"
                ]
            ]
            if not meaningful:
                if target_time or target_date:
                    session["draft_time"] = target_time
                    session["draft_date"] = target_date
                    session["awaiting_field"] = "title"
                    time_info = f" в {target_time}" if target_time else ""
                    date_info = f" на {format_russian_date_spoken(target_date)}" if target_date else ""
                    reply = f"Вы указали время{time_info}{date_info}, но не уточнили, какую задачу или встречу запланировать. Что именно нужно сделать?"
                    return AssistantResponse(
                        reply_text=reply,
                        voice_text=reply,
                        requires_clarification=True,
                    )
                return AssistantResponse(
                    reply_text="Не совсем понял название задачи или встречи. Что именно нужно запланировать?",
                    voice_text="Что именно нужно запланировать?",
                    requires_clarification=True,
                )

            if event_type == EventType.MEETING and not target_time:
                draft = EventCreate(
                    type=event_type,
                    title=title,
                    date=target_date,
                    time=None,
                    attendees=attendees,
                )
                session["draft_event"] = draft
                session["awaiting_field"] = "time"
                clarification = "На какое время поставить встречу?"
                return AssistantResponse(
                    reply_text=f"Встреча «{title}» на {format_russian_date_spoken(target_date)}. {clarification}",
                    voice_text=clarification,
                    requires_clarification=True,
                    action=AssistantAction(
                        action_type="CLARIFY",
                        clarification_question=clarification,
                    ),
                )

            if event_type == EventType.MEETING and target_time:
                conflicts = db_find_conflicts(target_date, target_time, user_id=user_id)
                new_event = db_create_event(
                    EventCreate(
                        type=event_type,
                        title=title,
                        date=target_date,
                        time=target_time,
                        attendees=attendees,
                        user_id=user_id,
                    ),
                    user_id=user_id,
                )
                session["last_event_id"] = new_event.id

                if conflicts:
                    conflict_name = conflicts[0].title
                    reply = (
                        f"Встреча «{new_event.title}» добавлена на {format_russian_date_spoken(new_event.date)} в {new_event.time}. "
                        f"Внимание: в это же время уже запланирована встреча «{conflict_name}»."
                    )
                    return AssistantResponse(
                        reply_text=reply,
                        voice_text=f"Встреча добавлена, но в это же время у вас уже запланирована встреча {conflict_name}.",
                        affected_events=[new_event],
                        action=AssistantAction(
                            action_type="CREATE_WITH_CONFLICT",
                            target_event_id=new_event.id,
                            conflict_event_id=conflicts[0].id,
                        ),
                    )

            created = db_create_event(
                EventCreate(
                    type=event_type,
                    title=title,
                    date=target_date,
                    time=target_time,
                    attendees=attendees,
                    user_id=user_id,
                ),
                user_id=user_id,
            )
            session["last_event_id"] = created.id

            type_name = "Встреча" if created.type == EventType.MEETING else ("Напоминание" if created.type == EventType.REMINDER else "Задача")
            time_info = f" в {created.time}" if created.time else ""
            reply = f"{type_name} «{created.title}» сохранена на {format_russian_date_spoken(created.date)}{time_info}."
            return AssistantResponse(
                reply_text=reply,
                voice_text=reply,
                affected_events=[created],
                action=AssistantAction(action_type="CREATE", target_event_id=created.id),
            )

        return AssistantResponse(
            reply_text="Я могу создать задачу или встречу, найти события в расписании или отметить задачу выполненной. Что нужно сделать?",
            voice_text="Чем я могу вам помочь?",
        )
