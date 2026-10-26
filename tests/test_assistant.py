import pytest
from datetime import date, timedelta
from backend.app.database import init_db, db_create_event, db_list_events
from backend.app.models.event import EventCreate, EventType
from backend.app.services.nlu_parser import parse_user_intent, parse_russian_date, parse_russian_time, clean_search_query
from backend.app.services.search_service import hybrid_search_events
from backend.app.services.dialog_manager import DialogManager


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def test_nlu_date_parsing():
    today = date.today()
    assert parse_russian_date("сегодня") == today.isoformat()
    assert parse_russian_date("завтра") == (today + timedelta(days=1)).isoformat()
    assert parse_russian_date("послезавтра") == (today + timedelta(days=2)).isoformat()


def test_nlu_time_parsing():
    assert parse_russian_time("в 15:00") == "15:00"
    assert parse_russian_time("в 10 утра") == "10:00"
    assert parse_russian_time("в 7 вечера") == "19:00"


def test_clean_search_query():
    assert clean_search_query("Найди задачу про презентацию") == "презентацию"
    assert "иваном" in clean_search_query("Когда у меня была встреча с Иваном?")
    assert "договору" in clean_search_query("Я когда-то ставил задачу по договору, найди ее")


def test_intent_create_reminder():
    res = parse_user_intent("Напомни мне завтра в 10 утра позвонить Ивану")
    assert res["intent"] == "CREATE_EVENT"
    assert res["type"] == EventType.REMINDER
    assert res["time"] == "10:00"


def test_intent_create_meeting():
    res = parse_user_intent("Добавь встречу с командой завтра в 15:00")
    assert res["intent"] == "CREATE_EVENT"
    assert res["type"] == EventType.MEETING
    assert res["time"] == "15:00"


def test_intent_list_events():
    res_today = parse_user_intent("Что у меня сегодня?")
    assert res_today["intent"] == "LIST_EVENTS"

    res_meetings = parse_user_intent("Есть ли у меня встречи сегодня?")
    assert res_meetings["intent"] == "LIST_EVENTS"
    assert res_meetings["type"] == EventType.MEETING

    res_tasks = parse_user_intent("Какие задачи у меня на завтра?")
    assert res_tasks["intent"] == "LIST_EVENTS"
    assert res_tasks["type"] == EventType.TASK

    res_week = parse_user_intent("Что запланировано на эту неделю?")
    assert res_week["intent"] == "LIST_EVENTS"
    assert res_week["is_week"] is True


@pytest.mark.asyncio
async def test_clarification_dialog():
    session_id = "test_clarify_flow"
    r1 = await DialogManager.process_user_message("Поставь встречу с Иваном завтра", session_id=session_id)
    assert r1.requires_clarification is True
    assert "время" in r1.reply_text.lower()

    r2 = await DialogManager.process_user_message("в 15:00", session_id=session_id)
    assert r2.requires_clarification is False
    assert "15:00" in r2.reply_text
    assert r2.affected_events is not None


@pytest.mark.asyncio
async def test_search_and_conflict():
    test_date = (date.today() + timedelta(days=10)).isoformat()
    db_create_event(EventCreate(
        type=EventType.MEETING,
        title="Совет директоров",
        date=test_date,
        time="12:00",
        attendees="Иван",
        is_completed=False
    ))

    results = hybrid_search_events("директоров", limit=5)
    assert len(results) > 0
    assert any("директоров" in e.title.lower() for e in results)

    conf_res = await DialogManager.process_user_message(
        f"Встреча с партнером {test_date} в 12:00",
        session_id="conflict_test"
    )
    assert conf_res.action is not None
    assert conf_res.action.action_type == "CREATE_WITH_CONFLICT"


@pytest.mark.asyncio
async def test_user_complaint_scenarios():
    res1 = await DialogManager.process_user_message("хочу в девть часов", session_id="user_flow_1")
    assert res1.requires_clarification is True
    assert "09:00" in res1.reply_text

    res1_follow = await DialogManager.process_user_message("сделать отчет", session_id="user_flow_1")
    assert res1_follow.requires_clarification is False
    assert res1_follow.affected_events is not None
    assert res1_follow.affected_events[0].time == "09:00"
    assert "отчет" in res1_follow.affected_events[0].title.lower()

    res2 = await DialogManager.process_user_message("покажи задачи на седня мне", session_id="user_flow_2")
    assert res2.action is not None
    assert res2.action.action_type == "LIST"

    res3 = await DialogManager.process_user_message("поставь мне беседку с моим братиком иваном на часов 11", session_id="user_flow_3")
    assert res3.affected_events is not None
    ev = res3.affected_events[0]
    assert ev.type == EventType.MEETING
    assert ev.time == "11:00"
    assert "иван" in ev.attendees.lower()
    assert "беседка" in ev.title.lower()

