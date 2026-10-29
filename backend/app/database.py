import sqlite3
import os
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta
from backend.app.models.event import EventItem, EventCreate, EventUpdate, EventFilter, EventType
from backend.app.models.user import UserItem

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "assistant.db"))


def get_db_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL UNIQUE COLLATE NOCASE,
        hashed_password TEXT NOT NULL,
        salt TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        reset_code TEXT,
        reset_code_expires TEXT,
        created_at TEXT NOT NULL
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT NOT NULL DEFAULT 'task',
        title TEXT NOT NULL,
        date TEXT NOT NULL,
        time TEXT,
        description TEXT,
        attendees TEXT,
        is_completed INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        user_id INTEGER REFERENCES users(id)
    );
    """)

    cursor.execute("PRAGMA table_info(events);")
    columns = [row["name"] for row in cursor.fetchall()]
    if "user_id" not in columns:
        try:
            cursor.execute("ALTER TABLE events ADD COLUMN user_id INTEGER REFERENCES users(id);")
        except Exception:
            try:
                cursor.execute("ALTER TABLE events ADD COLUMN user_id INTEGER;")
            except Exception:
                pass

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_date ON events(date);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_datetime ON events(date, time);")
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_id);")
    except Exception:
        pass

    cursor.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
        title,
        description,
        attendees,
        content='events',
        content_rowid='id',
        tokenize='unicode61 remove_diacritics 2'
    );
    """)

    cursor.execute("""
    CREATE TRIGGER IF NOT EXISTS events_ai AFTER INSERT ON events BEGIN
        INSERT INTO events_fts(rowid, title, description, attendees) 
        VALUES (new.id, new.title, coalesce(new.description, ''), coalesce(new.attendees, ''));
    END;
    """)

    cursor.execute("""
    CREATE TRIGGER IF NOT EXISTS events_ad AFTER DELETE ON events BEGIN
        INSERT INTO events_fts(events_fts, rowid, title, description, attendees) 
        VALUES('delete', old.id, old.title, coalesce(old.description, ''), coalesce(old.attendees, ''));
    END;
    """)

    cursor.execute("""
    CREATE TRIGGER IF NOT EXISTS events_au AFTER UPDATE ON events BEGIN
        INSERT INTO events_fts(events_fts, rowid, title, description, attendees) 
        VALUES('delete', old.id, old.title, coalesce(old.description, ''), coalesce(old.attendees, ''));
        INSERT INTO events_fts(rowid, title, description, attendees) 
        VALUES (new.id, new.title, coalesce(new.description, ''), coalesce(new.attendees, ''));
    END;
    """)

    conn.commit()
    conn.close()


# -------------------------------------------------------------
# User Database Operations
# -------------------------------------------------------------

def db_create_user(email: str, password_hash: str, salt: str) -> UserItem:
    conn = get_db_connection()
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    cursor.execute(
        """
        INSERT INTO users (email, hashed_password, salt, is_active, created_at)
        VALUES (?, ?, ?, 1, ?)
        """,
        (email.strip().lower(), password_hash, salt, now_iso),
    )
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return UserItem(
        id=user_id,
        email=email.strip().lower(),
        is_active=True,
        created_at=now_iso,
    )


def db_get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ? COLLATE NOCASE", (email.strip().lower(),))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def db_get_user_by_id(user_id: int) -> Optional[UserItem]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, is_active, created_at FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return UserItem(
            id=row["id"],
            email=row["email"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
        )
    return None


def db_set_reset_code(email: str, code: str, expires_at: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET reset_code = ?, reset_code_expires = ? WHERE email = ? COLLATE NOCASE",
        (code, expires_at, email.strip().lower()),
    )
    success = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return success


def db_reset_password(email: str, code: str, new_hash: str, new_salt: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    cursor.execute(
        """
        SELECT id FROM users
        WHERE email = ? COLLATE NOCASE AND reset_code = ? AND reset_code_expires >= ?
        """,
        (email.strip().lower(), code, now_iso),
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False

    cursor.execute(
        """
        UPDATE users
        SET hashed_password = ?, salt = ?, reset_code = NULL, reset_code_expires = NULL
        WHERE id = ?
        """,
        (new_hash, new_salt, row["id"]),
    )
    conn.commit()
    conn.close()
    return True


def db_seed_starter_events_for_user(user_id: int):
    """Adds a helpful starter schedule for a newly registered user."""
    today = date.today()
    tomorrow = today + timedelta(days=1)
    day_after = today + timedelta(days=2)

    starter_items = [
        EventCreate(
            type=EventType.TASK,
            title="Ознакомиться с голосовым ассистентом",
            date=today.isoformat(),
            time="10:00",
            description="Попробовать создать задачу голосом через микрофон или текстом.",
            user_id=user_id,
        ),
        EventCreate(
            type=EventType.MEETING,
            title="Обсуждение рабочего плана",
            date=tomorrow.isoformat(),
            time="14:00",
            attendees="Алексей, Мария",
            description="Синхронизация по задачам и расписанию на неделю.",
            user_id=user_id,
        ),
        EventCreate(
            type=EventType.REMINDER,
            title="Отправить недельный отчет",
            date=day_after.isoformat(),
            time="17:00",
            description="Сформировать отчет по выполненным проектам.",
            user_id=user_id,
        ),
    ]

    for item in starter_items:
        db_create_event(item, user_id=user_id)


# -------------------------------------------------------------
# Event Database Operations
# -------------------------------------------------------------

def row_to_event(row: sqlite3.Row) -> EventItem:
    user_id = row["user_id"] if "user_id" in row.keys() else None
    return EventItem(
        id=row["id"],
        type=EventType(row["type"]),
        title=row["title"],
        date=row["date"],
        time=row["time"],
        description=row["description"],
        attendees=row["attendees"],
        is_completed=bool(row["is_completed"]),
        created_at=row["created_at"],
        user_id=user_id,
    )


def db_create_event(event: EventCreate, user_id: Optional[int] = None) -> EventItem:
    conn = get_db_connection()
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    target_user_id = user_id if user_id is not None else event.user_id

    cursor.execute(
        """
        INSERT INTO events (type, title, date, time, description, attendees, is_completed, created_at, user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.type.value,
            event.title.strip(),
            event.date,
            event.time,
            event.description,
            event.attendees,
            1 if event.is_completed else 0,
            now_iso,
            target_user_id,
        ),
    )
    event_id = cursor.lastrowid
    conn.commit()

    cursor.execute("SELECT * FROM events WHERE id = ?", (event_id,))
    row = cursor.fetchone()
    conn.close()
    return row_to_event(row)


def db_get_event(event_id: int, user_id: Optional[int] = None) -> Optional[EventItem]:
    conn = get_db_connection()
    cursor = conn.cursor()
    if user_id is not None:
        cursor.execute("SELECT * FROM events WHERE id = ? AND (user_id = ? OR user_id IS NULL)", (event_id, user_id))
    else:
        cursor.execute("SELECT * FROM events WHERE id = ?", (event_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row_to_event(row)
    return None


def db_update_event(event_id: int, update_data: EventUpdate, user_id: Optional[int] = None) -> Optional[EventItem]:
    conn = get_db_connection()
    cursor = conn.cursor()

    fields = []
    values = []

    if update_data.type is not None:
        fields.append("type = ?")
        values.append(update_data.type.value)
    if update_data.title is not None:
        fields.append("title = ?")
        values.append(update_data.title.strip())
    if update_data.date is not None:
        fields.append("date = ?")
        values.append(update_data.date)
    if update_data.time is not None:
        fields.append("time = ?")
        values.append(update_data.time)
    if update_data.description is not None:
        fields.append("description = ?")
        values.append(update_data.description)
    if update_data.attendees is not None:
        fields.append("attendees = ?")
        values.append(update_data.attendees)
    if update_data.is_completed is not None:
        fields.append("is_completed = ?")
        values.append(1 if update_data.is_completed else 0)

    if not fields:
        conn.close()
        return db_get_event(event_id, user_id=user_id)

    values.append(event_id)
    if user_id is not None:
        query = f"UPDATE events SET {', '.join(fields)} WHERE id = ? AND (user_id = ? OR user_id IS NULL)"
        values.append(user_id)
    else:
        query = f"UPDATE events SET {', '.join(fields)} WHERE id = ?"

    cursor.execute(query, values)
    conn.commit()

    cursor.execute("SELECT * FROM events WHERE id = ?", (event_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row_to_event(row)
    return None


def db_delete_event(event_id: int, user_id: Optional[int] = None) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    if user_id is not None:
        cursor.execute("DELETE FROM events WHERE id = ? AND (user_id = ? OR user_id IS NULL)", (event_id, user_id))
    else:
        cursor.execute("DELETE FROM events WHERE id = ?", (event_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def db_list_events(
    filters: Optional[EventFilter] = None,
    limit: int = 200,
    user_id: Optional[int] = None,
) -> List[EventItem]:
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM events WHERE 1=1"
    params: List[Any] = []

    target_user_id = user_id if user_id is not None else (filters.user_id if filters else None)
    if target_user_id is not None:
        query += " AND user_id = ?"
        params.append(target_user_id)

    if filters:
        if filters.type:
            query += " AND type = ?"
            params.append(filters.type.value)
        if filters.start_date:
            query += " AND date >= ?"
            params.append(filters.start_date)
        if filters.end_date:
            query += " AND date <= ?"
            params.append(filters.end_date)
        if filters.is_completed is not None:
            query += " AND is_completed = ?"
            params.append(1 if filters.is_completed else 0)
        if filters.query:
            query += " AND (title LIKE ? OR description LIKE ? OR attendees LIKE ?)"
            like_term = f"%{filters.query}%"
            params.extend([like_term, like_term, like_term])

    query += " ORDER BY date ASC, time ASC, id ASC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [row_to_event(r) for r in rows]


def db_find_conflicts(
    date: str,
    time: str,
    exclude_id: Optional[int] = None,
    user_id: Optional[int] = None,
) -> List[EventItem]:
    if not time:
        return []
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM events WHERE date = ? AND time = ? AND type = 'meeting'"
    params: List[Any] = [date, time]

    if exclude_id is not None:
        query += " AND id != ?"
        params.append(exclude_id)

    if user_id is not None:
        query += " AND (user_id = ? OR user_id IS NULL)"
        params.append(user_id)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [row_to_event(r) for r in rows]


def db_search_fts(
    search_term: str,
    limit: int = 50,
    user_id: Optional[int] = None,
) -> List[EventItem]:
    if not search_term or not search_term.strip():
        return []

    conn = get_db_connection()
    cursor = conn.cursor()

    cleaned = "".join(ch for ch in search_term if ch.isalnum() or ch.isspace()).strip()
    words = cleaned.split()
    if not words:
        conn.close()
        return []

    fts_query = " ".join(f"{w}*" for w in words)

    user_clause = " AND (e.user_id = ? OR e.user_id IS NULL)" if user_id is not None else ""
    user_param = [user_id] if user_id is not None else []

    try:
        sql = f"""
            SELECT e.*, rank FROM events e
            JOIN (
                SELECT rowid, rank FROM events_fts WHERE events_fts MATCH ?
            ) f ON e.id = f.rowid
            WHERE 1=1 {user_clause}
            ORDER BY rank
            LIMIT ?
        """
        cursor.execute(sql, [fts_query] + user_param + [limit])
        rows = cursor.fetchall()
        events = [row_to_event(r) for r in rows]
    except Exception:
        like_term = f"%{search_term}%"
        user_like_clause = " AND (user_id = ? OR user_id IS NULL)" if user_id is not None else ""
        cursor.execute(
            f"""
            SELECT * FROM events 
            WHERE (title LIKE ? OR description LIKE ? OR attendees LIKE ?) {user_like_clause}
            ORDER BY date DESC LIMIT ?
            """,
            [like_term, like_term, like_term] + user_param + [limit],
        )
        rows = cursor.fetchall()
        events = [row_to_event(r) for r in rows]

    conn.close()
    return events
