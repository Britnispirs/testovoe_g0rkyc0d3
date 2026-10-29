import re
from typing import List, Dict, Any, Tuple
from backend.app.models.event import EventItem
from backend.app.database import db_list_events, db_search_fts

SYNONYM_CLUSTERS = [
    {"договор", "контракт", "соглашение", "согласование", "акт"},
    {"встреча", "созвон", "планёрка", "планерка", "митинг", "беседа", "демо"},
    {"отчет", "отчёт", "статистика", "аналитика", "сводка"},
    {"презентация", "слайды", "питч", "демо"},
    {"смета", "бюджет", "финансы", "расходы"},
    {"продукт", "приложение", "сервис", "crm", "сайт"},
]


def tokenize_russian(text: str) -> List[str]:
    text = text.lower().replace("ё", "е")
    words = re.findall(r"\b[а-яa-z0-9]{3,}\b", text)
    stems = []
    endings = (
        "ями", "ами", "ому", "ему", "ого", "его", "ыми", "ими", "ешь", "ете",
        "или", "ала", "ела", "ила", "ых", "их", "ой", "ей", "ам", "ем",
        "ом", "ах", "ях", "ую", "юю", "ые", "ие", "ов", "ев", "ть", "ся",
        "а", "е", "и", "й", "о", "у", "ы", "ь", "я"
    )
    for w in words:
        stem = w
        for end in sorted(endings, key=len, reverse=True):
            if stem.endswith(end) and len(stem) - len(end) >= 3:
                stem = stem[:-len(end)]
                break
        stems.append(stem)
    return stems


def calculate_semantic_similarity(query: str, target: str) -> float:
    q_tokens = set(tokenize_russian(query))
    t_tokens = set(tokenize_russian(target))

    if not q_tokens or not t_tokens:
        return 0.0

    expanded_q = set(q_tokens)
    q_words_raw = set(re.findall(r"\b[а-яa-z0-9]+\b", query.lower().replace("ё", "е")))
    for word in q_words_raw:
        for cluster in SYNONYM_CLUSTERS:
            if word in cluster:
                for syn in cluster:
                    expanded_q.update(tokenize_russian(syn))

    intersection = expanded_q.intersection(t_tokens)
    if not intersection:
        for qt in expanded_q:
            for tt in t_tokens:
                if qt in tt or tt in qt:
                    intersection.add(qt)

    similarity = len(intersection) / max(len(q_tokens), 1)
    return min(similarity, 1.0)


def hybrid_search_events(query: str, limit: int = 15, user_id: Optional[int] = None) -> List[EventItem]:
    if not query or not query.strip():
        return db_list_events(limit=limit, user_id=user_id)

    fts_results = db_search_fts(query, limit=50, user_id=user_id)
    all_events_dict: Dict[int, Tuple[EventItem, float]] = {}

    for rank, ev in enumerate(fts_results):
        score = 1.0 / (1.0 + rank * 0.1)
        all_events_dict[ev.id] = (ev, score)

    if len(all_events_dict) < limit:
        all_events = db_list_events(limit=250, user_id=user_id)
        for ev in all_events:
            combined_text = f"{ev.title} {ev.description or ''} {ev.attendees or ''}"
            sim = calculate_semantic_similarity(query, combined_text)
            if sim > 0.35:
                if ev.id in all_events_dict:
                    old_ev, old_score = all_events_dict[ev.id]
                    all_events_dict[ev.id] = (ev, old_score + sim)
                else:
                    all_events_dict[ev.id] = (ev, sim)

    sorted_items = sorted(all_events_dict.values(), key=lambda x: x[1], reverse=True)
    return [item[0] for item in sorted_items[:limit]]
