"""
Telegram клавіатури
"""
# Закріплені токени (завжди перші в списку)
PINNED_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XAUUSDT", "XAGUSDT", "XPTUSDT", "XPDUSDT", "TSLAUSDT", "PLTRUSDT", "AMZNUSDT", "COINUSDT", "CRCLUSDT", "HOODUSDT", "MSTRUSDT"]


def sort_with_pinned(symbols_list):
    """
    Сортує список: закріплені першими, решта алфавітно.
    """
    pinned = [s for s in PINNED_SYMBOLS if s in symbols_list]
    rest = sorted([s for s in symbols_list if s not in PINNED_SYMBOLS])
    return pinned + rest

def main_menu():
    return {
        "keyboard": [
            ["📊 Подивитися котирування", "👁️ Переглянути рівні"],
            ["✏️ Виправити рівні", "⚙️ Параметри токенів", "🎯 Досягнуті рівні"]
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
    Кнопки відображаються у 2 стовпчики.
    """
    #keyboard = [[s] for s in sorted(symbols_list)]
    symbols = sorted(symbols_list)
    keyboard = []

    for i in range(0, len(symbols), 2):
        row = symbols[i:i + 2]
        keyboard.append(row)
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

def dynamic_levels_keyboard_two_columns(levels_list):
    """
    Динамічна клавіатура з рівнями в 2 стовпчики
    """
    keyboard = []
    for i in range(0, len(levels_list), 2):
        row = [str(levels_list[i])]
        if i + 1 < len(levels_list):
            row.append(str(levels_list[i + 1]))
        keyboard.append(row)
    keyboard.append(["⬅️ Назад"])
    return {
        "keyboard": keyboard,
        "resize_keyboard": True
    }

def dynamic_levels_keyboard_three_columns(levels_list):
    """
    Динамічна клавіатура з рівнями в 3 стовпчики
    """
    keyboard = []
    for i in range(0, len(levels_list), 3):
        row = [str(levels_list[i])]
        if i + 1 < len(levels_list):
            row.append(str(levels_list[i + 1]))
        if i + 2 < len(levels_list):
            row.append(str(levels_list[i + 2]))
        keyboard.append(row)
    keyboard.append(["⬅️ Назад"])
    return {
        "keyboard": keyboard,
        "resize_keyboard": True
    }

def reached_levels_period_menu():
    """Меню вибору періоду для досягнутих рівнів"""
    keyboard = [
        ["⏱️ За 4 години"],
        ["⏱️ За 12 годин"],
        ["⏱️ За 24 години"],
        ["⬅️ Назад"]
    ]
    return {"keyboard": keyboard, "resize_keyboard": True}

def numeric_keyboard():
    """Клавіатура з цифрами для введення ціни"""
    keyboard = [
        ["1", "2", "3"],
        ["4", "5", "6"],
        ["7", "8", "9"],
        [".", "0", "⌫"],
        ["✅ Готово", "⬅️ Назад"]
    ]
    return {"keyboard": keyboard, "resize_keyboard": True}