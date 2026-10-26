import re
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, Tuple, List
from backend.app.models.event import EventType

MONTHS_RU = {
    "января": 1, "январь": 1,
    "февраля": 2, "февраль": 2,
    "марта": 3, "март": 3,
    "апреля": 4, "апрель": 4,
    "мая": 5, "май": 5,
    "июня": 6, "июнь": 6,
    "июля": 7, "июль": 7,
    "августа": 8, "август": 8,
    "сентября": 9, "сентябрь": 9,
    "октября": 10, "октябрь": 10,
    "ноября": 11, "ноябрь": 11,
    "декабря": 12, "декабрь": 12,
}

WEEKDAYS_RU = {
    "понедельник": 0, "пн": 0,
    "вторник": 1, "вт": 1,
    "среда": 2, "среду": 2, "ср": 2,
    "четверг": 3, "чт": 3,
    "пятница": 4, "пятницу": 4, "пт": 4,
    "суббота": 5, "субботу": 5, "сб": 5,
    "воскресенье": 6, "вс": 6,
}


WORDS_TO_HOURS = {
    "час": 1, "один": 1,
    "два": 2,
    "три": 3,
    "четыре": 4,
    "пять": 5,
    "шесть": 6,
    "семь": 7,
    "восемь": 8,
    "девять": 9, "девть": 9, "девяти": 9,
    "десять": 10, "десяти": 10,
    "одиннадцать": 11, "одиннадцати": 11,
    "двенадцать": 12, "двенадцати": 12,
    "полдень": 12,
    "полночь": 0,
}


def parse_russian_time(text: str) -> Optional[str]:
    lower = text.lower()

    match_colon = re.search(r"\b([0-1]?[0-9]|2[0-3]):([0-5][0-9])\b", lower)
    if match_colon:
        hours = int(match_colon.group(1))
        minutes = int(match_colon.group(2))
        return f"{hours:02d}:{minutes:02d}"

    words_pat = "|".join(sorted(WORDS_TO_HOURS.keys(), key=len, reverse=True))
    num_pat = rf"(?:2[0-3]|1[0-9]|0?[0-9]|{words_pat})"

    patterns = [
        rf"\b(?:в|во|к|на)\s*(?:примерно|около)?\s*(?:часов|часа)?\s*({num_pat})\s*(?:часов|часа|час)?\s*(утра|дня|вечера|ночи)?\b",
        rf"\b(?:часов|часа)\s+(?:в|во|к|на)?\s*({num_pat})\s*(утра|дня|вечера|ночи)?\b",
        rf"\b({num_pat})\s*(?:часов|часа|час)\s*(утра|дня|вечера|ночи)?\b",
    ]

    for pat in patterns:
        m = re.search(pat, lower)
        if m:
            val_str = m.group(1)
            period = m.group(2) if len(m.groups()) > 1 else None
            if val_str in WORDS_TO_HOURS:
                h = WORDS_TO_HOURS[val_str]
            elif val_str.isdigit():
                h = int(val_str)
            else:
                continue

            if 0 <= h <= 23:
                if period in ["вечера", "дня"] and h < 12:
                    h += 12
                elif period == "ночи" and h == 12:
                    h = 0
                return f"{h:02d}:00"

    match_rel = re.search(r"через\s+(\d+|два|три|четыре|полчаса|час)\s*(час|часа|часов|минут|минуты)?", lower)
    if match_rel:
        raw_val = match_rel.group(1)
        unit = match_rel.group(2) or ""
        val = 1
        if raw_val == "два":
            val = 2
        elif raw_val == "три":
            val = 3
        elif raw_val == "четыре":
            val = 4
        elif raw_val == "полчаса":
            val = 30
            unit = "минут"
        elif raw_val.isdigit():
            val = int(raw_val)

        now = datetime.now()
        if "минут" in unit:
            future = now + timedelta(minutes=val)
        else:
            future = now + timedelta(hours=val)
        return future.strftime("%H:%M")

    return None


def parse_russian_date(text: str, base_date: Optional[date] = None) -> Optional[str]:
    if base_date is None:
        base_date = date.today()

    lower = text.lower()

    if "послезавтра" in lower:
        return (base_date + timedelta(days=2)).isoformat()
    if "завтра" in lower or "завтречко" in lower:
        return (base_date + timedelta(days=1)).isoformat()
    if "сегодня" in lower or "седня" in lower or "щас" in lower or "сейчас" in lower:
        return base_date.isoformat()

    if "через" in lower and any(u in lower for u in ["час", "часа", "часов", "минут", "полчаса"]):
        return base_date.isoformat()

    if "до конца недели" in lower or "на этой неделе" in lower or "в конце недели" in lower:
        days_ahead = 6 - base_date.weekday()
        return (base_date + timedelta(days=days_ahead)).isoformat()

    if "на следующей неделе" in lower or "следующая неделя" in lower:
        days_ahead = (7 - base_date.weekday()) + 0
        return (base_date + timedelta(days=days_ahead)).isoformat()

    for wday_name, wday_num in WEEKDAYS_RU.items():
        pattern = rf"\b(?:в|во|на)?\s*(следующий|следующую)?\s*{wday_name}\b"
        match = re.search(pattern, lower)
        if match:
            is_next = bool(match.group(1))
            current_wday = base_date.weekday()
            days_diff = (wday_num - current_wday) % 7
            if days_diff == 0:
                days_diff = 7
            if is_next and days_diff < 7:
                days_diff += 7
            return (base_date + timedelta(days=days_diff)).isoformat()

    for month_name, month_num in MONTHS_RU.items():
        pattern = rf"\b(\d{{1,2}})\s+{month_name}\b"
        match = re.search(pattern, lower)
        if match:
            day = int(match.group(1))
            year = base_date.year
            try:
                target = date(year, month_num, day)
                if target < base_date:
                    target = date(year + 1, month_num, day)
                return target.isoformat()
            except ValueError:
                pass

    match_iso = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", lower)
    if match_iso:
        return f"{match_iso.group(1)}-{match_iso.group(2)}-{match_iso.group(3)}"

    match_dot = re.search(r"\b(\d{1,2})\.(\d{1,2})\.?(\d{4})?\b", lower)
    if match_dot:
        d = int(match_dot.group(1))
        m = int(match_dot.group(2))
        y = int(match_dot.group(3)) if match_dot.group(3) else base_date.year
        try:
            return date(y, m, d).isoformat()
        except ValueError:
            pass

    return None


def clean_title(raw_text: str, event_type: EventType, date_str: Optional[str], time_str: Optional[str]) -> str:
    cleaned = raw_text

    prefixes = [
        r"^(пожалуйста\s*,?\s*)",
        r"^(напомни мне\s+)",
        r"^(напомни\s+)",
        r"^(поставь мне задачу\s+)",
        r"^(поставь задачу\s+)",
        r"^(поставь мне встречу\s+)",
        r"^(поставь встречу\s+)",
        r"^(поставь мне\s+)",
        r"^(поставь\s+)",
        r"^(добавь мне задачу\s+)",
        r"^(добавь задачу\s+)",
        r"^(добавь мне встречу\s+)",
        r"^(добавь встречу\s+)",
        r"^(добавь мне\s+)",
        r"^(добавь\s+)",
        r"^(создай мне задачу\s+)",
        r"^(создай задачу\s+)",
        r"^(создай мне встречу\s+)",
        r"^(создай встречу\s+)",
        r"^(создай мне\s+)",
        r"^(создай\s+)",
        r"^(запланируй мне встречу\s+)",
        r"^(запланируй встречу\s+)",
        r"^(запланируй мне\s+)",
        r"^(запланируй\s+)",
        r"^(запиши мне\s+)",
        r"^(запиши\s+)",
        r"^(организуй мне\s+)",
        r"^(организуй нам\s+)",
        r"^(организуй\s+)",
        r"^(сделай мне\s+)",
        r"^(сделай\s+)",
        r"^(у меня встреча\s+с\s+)",
        r"^(у меня встреча\s+)",
        r"^(у меня созвон\s+с\s+)",
        r"^(у меня созвон\s+)",
        r"^(у меня\s+)",
        r"^(встреча\s+с\s+)",
        r"^(встреча\s+)",
        r"^(нужно\s+)",
        r"^(надо\s+)",
        r"^(хочу\s+)",
        r"^(давай\s+)",
    ]
    for pref in prefixes:
        cleaned = re.sub(pref, "", cleaned, flags=re.IGNORECASE)

    words_pat = "|".join(sorted(WORDS_TO_HOURS.keys(), key=len, reverse=True))
    num_pat = rf"(?:2[0-3]|1[0-9]|0?[0-9]|{words_pat})"
    date_time_phrases = [
        r"\b(сегодня|седня|завтра|завтречко|послезавтра|щас|сейчас)\b",
        r"\b(до конца недели|на этой неделе|на следующей неделе|в конце недели)\b",
        r"\b[0-2]?[0-9]:[0-5][0-9]\b",
        rf"\b(?:в|во|к|на)\s*(?:примерно|около)?\s*(?:часов|часа)?\s*(?:{num_pat})\s*(?:часов|часа|час)?\s*(?:утра|дня|вечера|ночи)?\b",
        rf"\b(?:часов|часа)\s+(?:в|во|к|на)?\s*(?:{num_pat})\s*(?:утра|дня|вечера|ночи)?\b",
        rf"\b(?:{num_pat})\s*(?:часов|часа|час)\s*(?:утра|дня|вечера|ночи)?\b",
        r"\bчерез\s+(\d+|два|три|четыре|полчаса|час)\s*(час|часа|часов|минут|минуты)?\b",
        r"\b(в|во)\s+(понедельник|вторник|среду|четверг|пятницу|субботу|воскресенье)\b",
    ]
    for dt_phrase in date_time_phrases:
        cleaned = re.sub(dt_phrase, "", cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r"\bу меня\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bмне\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-")

    if event_type == EventType.MEETING:
        lower_cl = cleaned.lower()
        if lower_cl.startswith("беседку"):
            cleaned = "Беседка" + cleaned[7:]
        elif lower_cl.startswith("беседу"):
            cleaned = "Беседа" + cleaned[6:]
        elif not any(k in lower_cl for k in ["встреча", "созвон", "планерка", "планёрка", "демо", "бесед", "поболтать", "поговор", "ланч", "кофе", "обед"]):
            if lower_cl.startswith("с ") or lower_cl.startswith("со "):
                cleaned = f"Встреча {cleaned}"
            elif cleaned:
                cleaned = f"Встреча: {cleaned}"

    if not cleaned:
        return ""
    return cleaned[0].upper() + cleaned[1:] if len(cleaned) > 0 else cleaned


def clean_search_query(text: str) -> str:
    cleaned = text.lower()
    phrases_to_remove = [
        r"я когда-то ставил задачу",
        r"когда у меня была встреча",
        r"когда была встреча",
        r"когда у меня была",
        r"когда была",
        r"найди задачу",
        r"найди встречу",
        r"найди напоминание",
        r"найди ее",
        r"найди его",
        r"найди их",
        r"найди",
        r"найти",
        r"поищи",
        r"пожалуйста",
        r"подскажи",
        r"покажи",
        r"\bпро\b",
        r"\bпо\b",
        r"\bоб?\b",
        r"\bс\b",
        r"\bсо\b",
        r"\bдля\b",
        r"\bу меня\b",
        r"\bбыла\b",
        r"\bбыл\b",
        r"\bбыли\b",
        r"\bзадачу\b",
        r"\bзадача\b",
        r"\bвстречу\b",
        r"\bвстреча\b",
        r"\bее\b",
        r"\bего\b",
    ]
    for p in phrases_to_remove:
        cleaned = re.sub(p, " ", cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def parse_user_intent(text: str) -> Dict[str, Any]:
    lower = text.lower().strip()

    if any(re.search(rf"\b{g}\b", lower) for g in ["привет", "здравствуй", "здравствуйте", "салют", "доброе утро", "добрый день", "добрый вечер", "хай", "хеллоу"]):
        return {"intent": "CHAT_GREETING", "raw_text": text}

    if any(re.search(rf"\b{g}\b", lower) for g in ["спасибо", "благодарю", "от души", "сенкс"]):
        return {"intent": "CHAT_THANKS", "raw_text": text}

    if any(k in lower for k in ["что ты умеешь", "что можешь", "помощь", "команды", "как пользоваться", "help"]):
        return {"intent": "HELP", "raw_text": text}

    if any(k in lower for k in ["отметь выполненной", "отметь задачу выполненной", "выполнил задачу", "заверши задачу", "сделано", "отметь как сделано", "отметь задачу"]):
        query = clean_search_query(text)
        return {
            "intent": "COMPLETE_EVENT",
            "query": query,
            "raw_text": text,
        }

    if any(k in lower for k in ["удали", "удалить", "отмени", "отменить", "стереть"]):
        query = clean_search_query(text)
        return {
            "intent": "DELETE_EVENT",
            "query": query,
            "raw_text": text,
        }

    if any(k in lower for k in ["перенеси", "перенести", "сдвинь", "поменяй время", "отложи"]):
        target_date = parse_russian_date(lower)
        target_time = parse_russian_time(lower)
        return {
            "intent": "RESCHEDULE_EVENT",
            "date": target_date,
            "time": target_time,
            "raw_text": text,
        }

    if any(k in lower for k in [
        "найди", "найти", "поищи", "когда у меня была", "когда была", "когда-то ставил", "найди ее", "найди задачу", "найди встречу"
    ]):
        query = clean_search_query(text)
        return {
            "intent": "SEARCH_EVENTS",
            "query": query,
            "raw_text": text,
        }

    list_keywords = [
        "что у меня", "какие планы", "покажи мои", "какие задачи", "есть ли у меня",
        "что запланировано", "планы на", "список задач", "список", "расписание",
        "покажи", "выведи", "глянь", "посмотри", "какие дела", "какие встречи",
        "что делать", "что мне делать", "дела на", "задачи на", "встречи на",
        "что на сегодня", "что на завтра", "мои задачи", "мои встречи", "мои планы",
        "озвучь задачи", "озвучь планы", "расскажи планы"
    ]
    is_list = any(k in lower for k in list_keywords) or bool(
        re.search(r"\b(задач[иаеы]|встреч[иае]|дел[ао]|план[ыов]|событи[яй])\b.*\b(на\s+(сегодня|седня|завтра|недел)|покажи|список)\b", lower)
    ) or bool(
        re.search(r"\b(покажи|выведи|глянь|посмотри|список)\b.*\b(задач|встреч|дел|план|событи|напоминан|расписани)\b", lower)
    )

    if is_list:
        target_date = parse_russian_date(lower)
        is_week = any(k in lower for k in ["неделю", "на этой неделе", "на следующую неделю"])

        ev_type = None
        if "встреч" in lower or "созвон" in lower:
            ev_type = EventType.MEETING
        elif "задач" in lower or "дел" in lower:
            ev_type = EventType.TASK
        elif "напоминани" in lower:
            ev_type = EventType.REMINDER

        return {
            "intent": "LIST_EVENTS",
            "date": target_date or date.today().isoformat(),
            "is_week": is_week,
            "type": ev_type,
            "raw_text": text,
        }

    is_meeting = any(k in lower for k in [
        "встреча", "созвон", "планёрка", "планерка", "демо", "встречу", "встретиться",
        "беседа", "беседу", "беседку", "поболтать", "поговорить", "митинг", "синк",
        "кофе", "ланч", "обед", "созвониться", "звонок", "1-on-1"
    ])
    is_reminder = any(k in lower for k in ["напомни", "напоминание", "не забудь"])

    if is_meeting:
        event_type = EventType.MEETING
    elif is_reminder:
        event_type = EventType.REMINDER
    else:
        event_type = EventType.TASK

    extracted_date = parse_russian_date(lower)
    extracted_time = parse_russian_time(lower)

    title = clean_title(text, event_type, extracted_date, extracted_time)

    attendee = None
    attendee_match = re.search(
        r"\b(?:с|со|для)\s+(?:моим|моей|нашим|своим)?\s*(?:братом|братиком|другом|подругой|коллегой|партнером|партнёром|клиентом)?\s*([А-Яа-яA-Za-z]+)",
        text,
        flags=re.IGNORECASE,
    )
    if attendee_match:
        cand = attendee_match.group(1).capitalize()
        if cand.lower() not in ["командой", "партнером", "партнёром", "братом", "братиком", "моим", "моей", "своим", "нашим"]:
            if cand.endswith("ом") or cand.endswith("ем"):
                cand = cand[:-2]
            attendee = cand

    meaningful_words = [
        w for w in re.sub(r"[^\w\s]", "", title.lower()).split()
        if w not in [
            "хочу", "надо", "нужно", "можно", "мне", "у", "меня", "пожалуйста",
            "бы", "ли", "давай", "в", "на", "к", "с", "со", "для", "и", "поставить",
            "поставь", "добавь", "создай", "запиши", "запланируй", "задачу", "встречу"
        ]
    ]

    if not meaningful_words:
        if extracted_time or extracted_date:
            return {
                "intent": "INCOMPLETE",
                "date": extracted_date,
                "time": extracted_time,
                "raw_text": text,
            }
        return {
            "intent": "UNKNOWN",
            "raw_text": text,
        }

    return {
        "intent": "CREATE_EVENT",
        "type": event_type,
        "title": title,
        "date": extracted_date,
        "time": extracted_time,
        "attendees": attendee,
        "raw_text": text,
    }
