from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime


class EventType(str, Enum):
    TASK = "task"
    MEETING = "meeting"
    REMINDER = "reminder"


class EventStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class EventBase(BaseModel):
    type: EventType = Field(default=EventType.TASK, description="Тип записи: task, meeting, reminder")
    title: str = Field(..., description="Название или текст задачи/встречи")
    date: str = Field(..., description="Дата в формате YYYY-MM-DD")
    time: Optional[str] = Field(None, description="Время в формате HH:MM")
    description: Optional[str] = Field(None, description="Подробное описание или заметка")
    attendees: Optional[str] = Field(None, description="Участники (для встреч или звонков)")
    is_completed: bool = Field(default=False, description="Статус выполнения")


class EventCreate(EventBase):
    pass


class EventUpdate(BaseModel):
    type: Optional[EventType] = None
    title: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    description: Optional[str] = None
    attendees: Optional[str] = None
    is_completed: Optional[bool] = None


class EventItem(EventBase):
    id: int
    created_at: str

    class Config:
        from_attributes = True


class EventFilter(BaseModel):
    type: Optional[EventType] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_completed: Optional[bool] = None
    query: Optional[str] = None


class AssistantMessage(BaseModel):
    role: str
    content: str


class AssistantRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default"
    history: Optional[List[AssistantMessage]] = None


class AssistantAction(BaseModel):
    action_type: str
    target_event_id: Optional[int] = None
    event_data: Optional[EventCreate] = None
    conflict_event_id: Optional[int] = None
    confirmation_required: bool = False
    clarification_question: Optional[str] = None


class AssistantResponse(BaseModel):
    reply_text: str
    voice_text: str
    action: Optional[AssistantAction] = None
    affected_events: Optional[List[EventItem]] = None
    requires_clarification: bool = False
