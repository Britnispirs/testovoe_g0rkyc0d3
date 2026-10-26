from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)


def get_main_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📅 На сегодня"),
                KeyboardButton(text="📋 Мои задачи"),
            ],
            [
                KeyboardButton(text="🤝 Мои встречи"),
                KeyboardButton(text="❓ Помощь"),
            ],
        ],
        resize_keyboard=True,
    )


def get_cancel_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_dialog")]
        ]
    )


def get_event_action_keyboard(event_id: int, is_completed: bool = False) -> InlineKeyboardMarkup:
    buttons = []
    if not is_completed:
        buttons.append(InlineKeyboardButton(text="✅ Выполнить", callback_data=f"done:{event_id}"))
    buttons.append(InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del:{event_id}"))
    return InlineKeyboardMarkup(inline_keyboard=[buttons])
