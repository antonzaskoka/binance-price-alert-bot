"""
Telegram клавіатури
"""
# Закріплені токени (завжди перші в списку)
PINNED_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XAUUSDT", "XAGUSDT"]


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
            ["📊 Об'єми токенів", "✏️ Виправити рівні"],
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

def volume_thresholds_menu():
    """
    Кнопки з діапазонами avg об'єму з VOLUME_THRESHOLDS
    """
    from alerts.volume_thresholds import VOLUME_THRESHOLDS

    keyboard = []
    # Будуємо пари діапазонів з VOLUME_THRESHOLDS
    # Сортуємо від більшого до меншого
    sorted_thresholds = sorted(VOLUME_THRESHOLDS, key=lambda x: x[0], reverse=True)

    for i in range(len(sorted_thresholds)):
        upper = sorted_thresholds[i][0]
        if i + 1 < len(sorted_thresholds):
            lower = sorted_thresholds[i + 1][0]
        else:
            lower = 0

        if upper == 0:
            continue  # Пропускаємо нульовий поріг

        label = f"${upper // 1_000_000}M+"
        keyboard.append([label])

    keyboard.append(["⬅️ Назад"])
    return {
        "keyboard": keyboard,
        "resize_keyboard": True
    }


def volume_multipliers_menu(avg_threshold):
    """
    Кнопки з мультиплікаторами (стандартний набір)
    """
    # ✅ Стандартні мультиплікатори
    multipliers = [1.3, 1.5, 2, 3, 4, 5, 6, 10, 15]

    # Кнопки в 3 колонки
    keyboard = []
    for i in range(0, len(multipliers), 3):
        row = []
        for j in range(3):
            if i + j < len(multipliers):
                mult = multipliers[i + j]
                # Форматуємо: 1.3, 1.5 з десятковою, решта без
                if mult < 2:
                    row.append(f"{mult}x")
                else:
                    row.append(f"{int(mult)}x")
        keyboard.append(row)

    keyboard.append(["⬅️ Назад"])
    return {
        "keyboard": keyboard,
        "resize_keyboard": True
    }