"""
Telegram клавіатури
"""


def main_menu():
    return {
        "keyboard": [
            ["📊 Подивитися котирування"],
            ["✏️ Виправити рівні"],
            ["⚙️ Параметри токенів"]
        ],
        "resize_keyboard": True
    }


def back_menu():
    return {
        "keyboard": [["⬅️ Назад"]],
        "resize_keyboard": True
    }


def timeframe_menu():
    return {
        "inline_keyboard": [
            [{"text": "1m", "callback_data": "tf:1m"},
             {"text": "5m", "callback_data": "tf:5m"},
             {"text": "15m", "callback_data": "tf:15m"}],
            [{"text": "1h", "callback_data": "tf:1h"},
             {"text": "4h", "callback_data": "tf:4h"},
             {"text": "1d", "callback_data": "tf:1d"}],
            [{"text": "⬅️ Назад", "callback_data": "back"}]
        ]
    }


def levels_menu():
    return {
        "keyboard": [
            ["➕ Додати рівень"],
            ["🗑 Видалити рівень"],
            ["⬅️ Назад"]
        ],
        "resize_keyboard": True
    }


def symbols_menu():
    """Меню налаштувань токенів"""
    return {
        "keyboard": [
            ["➕ Додати токен"],
            ["✏️ Редагувати токен"],
            ["🗑 Видалити токен"],
            ["⬅️ Назад"]
        ],
        "resize_keyboard": True
    }


def param_names_readable():
    """Читабельні назви параметрів"""
    return {
        "short_threshold": "Short threshold",
        "middle_threshold": "Middle threshold",
        "long_threshold": "Long threshold",
        "sl_small_pct": "Stop Loss Small, %",
        "sl_big_pct": "Stop Loss Big, %"
    }


def dynamic_symbols_keyboard(symbols_list):
    """
    Динамічна клавіатура з кнопками для кожного токена.
    symbols_list — список назв токенів, наприклад ["BTCUSDT", "ETHUSDT"]
    """
    keyboard = [[s] for s in sorted(symbols_list)]
    keyboard.append(["⬅️ Назад"])
    return {
        "keyboard": keyboard,
        "resize_keyboard": True
    }


def dynamic_levels_keyboard(levels_list):
    """
    Динамічна клавіатура з кнопками для кожного рівня.
    levels_list — список рівнів, наприклад [86700, 88614, 90088]
    """
    keyboard = [[str(lvl)] for lvl in levels_list]
    keyboard.append(["⬅️ Назад"])
    return {
        "keyboard": keyboard,
        "resize_keyboard": True
    }
