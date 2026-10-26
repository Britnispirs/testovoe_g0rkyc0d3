import json


def get_vk_main_keyboard() -> str:
    keyboard = {
        "one_time": False,
        "buttons": [
            [
                {
                    "action": {
                        "type": "text",
                        "label": "📅 На сегодня",
                        "payload": json.dumps({"command": "today"}),
                    },
                    "color": "primary",
                },
                {
                    "action": {
                        "type": "text",
                        "label": "📋 Мои задачи",
                        "payload": json.dumps({"command": "tasks"}),
                    },
                    "color": "secondary",
                },
            ],
            [
                {
                    "action": {
                        "type": "text",
                        "label": "🤝 Мои встречи",
                        "payload": json.dumps({"command": "meetings"}),
                    },
                    "color": "secondary",
                },
                {
                    "action": {
                        "type": "text",
                        "label": "❓ Помощь",
                        "payload": json.dumps({"command": "help"}),
                    },
                    "color": "secondary",
                },
            ],
        ],
    }
    return json.dumps(keyboard, ensure_ascii=False)
