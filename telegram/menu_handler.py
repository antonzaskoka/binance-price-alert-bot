"""
Обробка меню та станів користувача
"""
from collections import defaultdict
import logging
import json
import os
import re

from telegram.keyboards import (
    main_menu, back_menu, timeframe_menu, levels_menu,
    symbols_menu, param_names_readable,
    dynamic_symbols_keyboard, dynamic_levels_keyboard_three_columns
)
from config import LEVELS_FILE
from alerts.symbols_manager import (
    normalize_symbol, load_symbols, add_symbol,
    update_symbol, delete_symbol, get_symbol_params
)
from alerts.levels_manager import load_levels

logger = logging.getLogger(__name__)

# Стан користувачів
user_state = defaultdict(dict)


def show_main_menu(chat_id, send):
    """Показує головне меню"""
    user_state[chat_id] = {"step": "main"}
    send(chat_id, "🔘 Головне меню", reply_markup=main_menu())


def handle_text(chat_id, text, send):
    """Обробка текстових повідомлень"""
    state = user_state.get(chat_id, {"step": "main"})
    step = state.get("step")

    # ---- MAIN MENU ----
    if step == "main":
        if text == "📊 Подивитися котирування":
            user_state[chat_id]["step"] = "enter_symbol"
            send(chat_id, "✍️ Введи назву токена (наприклад BTC)", reply_markup=back_menu())
            return

        if text == "✏️ Виправити рівні":
            user_state[chat_id] = {"step": "levels_menu"}
            send(
                chat_id,
                "✏️ <b>Виправити рівні</b>",
                reply_markup=levels_menu()
            )
            return

        if text == "⚙️ Параметри токенів":
            user_state[chat_id] = {"step": "symbols_menu"}
            send(
                chat_id,
                "⚙️ <b>Параметри токенів</b>",
                reply_markup=symbols_menu()
            )
            return

        if text == "👁️ Переглянути рівні":
            levels_map = load_levels()
            tokens_with_levels = sorted(levels_map.keys())

            if tokens_with_levels:
                user_state[chat_id] = {"step": "view_levels_symbol"}
                send(
                    chat_id,
                    "📌 Обери токен для перегляду рівнів:",
                    reply_markup=dynamic_symbols_keyboard(tokens_with_levels)
                )
            else:
                send(chat_id, "⚠️ Немає токенів з рівнями", reply_markup=main_menu())
            return

    # ---- ENTER SYMBOL ----
    if step == "enter_symbol":
        if text == "⬅️ Назад":
            show_main_menu(chat_id, send)
            return

        # Парсинг: "btc" або "btc, 81050"
        custom_price = None
        match = re.match(r'^([a-zA-Z0-9]+)\s*,\s*([0-9.]+)$', text.strip())
        
        if match:
            symbol_text = match.group(1)
            custom_price = float(match.group(2))
        else:
            symbol_text = text.strip()

        symbol = normalize_symbol(symbol_text)

        user_state[chat_id]["symbol"] = symbol
        user_state[chat_id]["custom_price"] = custom_price
        user_state[chat_id]["step"] = "select_tf"

        send(
            chat_id,
            f"⏱ Обери таймфрейм для <b>{symbol}</b>",
            reply_markup=timeframe_menu()
        )
        return

    # ---- SELECT TF ----
    if step == "select_tf":
        if text == "⬅️ Назад":
            user_state[chat_id]["step"] = "enter_symbol"
            send(chat_id, "✍️ Введи назву токена (наприклад BTC)", reply_markup=back_menu())
            return

    # ---- LEVELS MENU ----
    if step == "levels_menu":
        if text == "⬅️ Назад":
            show_main_menu(chat_id, send)
            return

        if text == "➕ Додати рівень":
            # Динамічні кнопки з токенами з levels.json + symbols.json
            levels_map = load_levels()
            symbols_map = load_symbols()
            all_tokens = sorted(set(levels_map.keys()) | set(symbols_map.keys()))

            if all_tokens:
                user_state[chat_id] = {"step": "level_add_symbol"}
                send(
                    chat_id,
                    "📌 Обери токен або введи новий:",
                    reply_markup=dynamic_symbols_keyboard(all_tokens)
                )
            else:
                user_state[chat_id] = {"step": "level_add_symbol"}
                send(chat_id, "✍️ Введи назву токена (наприклад BTC)", reply_markup=back_menu())
            return

        if text == "🗑 Видалити рівень":
            # Динамічні кнопки тільки з tokens, які є в levels.json
            levels_map = load_levels()
            tokens_with_levels = sorted(levels_map.keys())

            if tokens_with_levels:
                user_state[chat_id] = {"step": "level_del_symbol"}
                send(
                    chat_id,
                    "📌 Обери токен:",
                    reply_markup=dynamic_symbols_keyboard(tokens_with_levels)
                )
            else:
                send(chat_id, "⚠️ Немає токенів з рівнями", reply_markup=levels_menu())
            return

    # ---- ADD LEVEL: SYMBOL ----
    if step == "level_add_symbol":
        if text == "⬅️ Назад":
            user_state[chat_id] = {"step": "levels_menu"}
            send(chat_id, "✏️ Виправити рівні", reply_markup=levels_menu())
            return

        symbol = normalize_symbol(text)

        user_state[chat_id] = {
            "step": "level_add_price",
            "symbol": symbol
        }
        send(chat_id, f"💰 Введи ціну рівня для <b>{symbol}</b>")
        return

    # ---- ADD LEVEL: PRICE ----
    if step == "level_add_price":
        try:
            price = float(text)
        except ValueError:
            send(chat_id, "❌ Некоректна ціна, введи число")
            return

        symbol = user_state[chat_id]["symbol"]

        if os.path.exists(LEVELS_FILE):
            with open(LEVELS_FILE, "r") as f:
                data = json.load(f)
        else:
            data = {}

        data.setdefault(symbol, [])
        data[symbol].append(price)
        data[symbol] = sorted(set(data[symbol]))

        with open(LEVELS_FILE, "w") as f:
            json.dump(data, f, indent=2)

        send(
            chat_id,
            f"✅ Рівень {price} для {symbol} додано",
            reply_markup=levels_menu()
        )
        user_state[chat_id] = {"step": "levels_menu"}
        return

    # ---- DELETE LEVEL: SYMBOL ----
    if step == "level_del_symbol":
        if text == "⬅️ Назад":
            user_state[chat_id] = {"step": "levels_menu"}
            send(chat_id, "✏️ Виправити рівні", reply_markup=levels_menu())
            return

        symbol = normalize_symbol(text)

        user_state[chat_id] = {
            "step": "level_del_price",
            "symbol": symbol
        }

        if os.path.exists(LEVELS_FILE):
            with open(LEVELS_FILE, "r") as f:
                data = json.load(f)
            levels = data.get(symbol, [])

            if levels:
                # Динамічні кнопки з рівнями
                send(
                    chat_id,
                    f"📋 Рівні для <b>{symbol}</b>:",
                    reply_markup=dynamic_levels_keyboard_three_columns(levels)
                )
            else:
                send(chat_id, f"⚠️ Немає рівнів для {symbol}", reply_markup=levels_menu())
                user_state[chat_id] = {"step": "levels_menu"}
        else:
            send(chat_id, "⚠️ Файл рівнів не знайдено", reply_markup=levels_menu())
            user_state[chat_id] = {"step": "levels_menu"}
        return

    # ---- DELETE LEVEL: PRICE ----
    if step == "level_del_price":
        if text == "⬅️ Назад":
            user_state[chat_id] = {"step": "levels_menu"}
            send(chat_id, "✏️ Виправити рівні", reply_markup=levels_menu())
            return

        try:
            price = float(text)
        except ValueError:
            send(chat_id, "❌ Некоректна ціна, введи число")
            return

        symbol = user_state[chat_id]["symbol"]

        if os.path.exists(LEVELS_FILE):
            with open(LEVELS_FILE, "r") as f:
                data = json.load(f)
        else:
            data = {}

        if symbol in data and price in data[symbol]:
            data[symbol].remove(price)

            # ✅ Видалити токен якщо немає рівнів
            if not data[symbol]:
                del data[symbol]

            with open(LEVELS_FILE, "w") as f:
                json.dump(data, f, indent=2)

            send(
                chat_id,
                f"✅ Рівень {price} для {symbol} видалено",
                reply_markup=levels_menu()
            )
        else:
            send(
                chat_id,
                f"❌ Рівень {price} не знайдено для {symbol}",
                reply_markup=levels_menu()
            )

        user_state[chat_id] = {"step": "levels_menu"}
        return

    # ---- VIEW LEVELS: SYMBOL ----
    if step == "view_levels_symbol":
        if text == "⬅️ Назад":
            show_main_menu(chat_id, send)
            return

        symbol = normalize_symbol(text)

        if os.path.exists(LEVELS_FILE):
            with open(LEVELS_FILE, "r") as f:
                data = json.load(f)
            levels = data.get(symbol, [])

            if levels:
                send(
                    chat_id,
                    f"📋 <b>Рівні для {symbol}</b>:",
                    reply_markup=dynamic_levels_keyboard_three_columns(levels)
                )
                user_state[chat_id] = {"step": "view_levels_show"}
            else:
                send(chat_id, f"⚠️ Немає рівнів для {symbol}", reply_markup=main_menu())
                user_state[chat_id] = {"step": "main"}
        else:
            send(chat_id, "⚠️ Файл рівнів не знайдено", reply_markup=main_menu())
            user_state[chat_id] = {"step": "main"}
        return

    # ---- VIEW LEVELS: SHOW (обробка кнопок рівнів або Назад) ----
    if step == "view_levels_show":
        if text == "⬅️ Назад":
            show_main_menu(chat_id, send)
            return
        # Якщо натиснув на рівень - просто ігноруємо
        return

    # ---- SYMBOLS MENU ----
    if step == "symbols_menu":
        if text == "⬅️ Назад":
            show_main_menu(chat_id, send)
            return

        if text == "➕ Додати токен":
            user_state[chat_id] = {"step": "symbol_add_name"}
            send(chat_id, "✍️ Введи назву нового токена (наприклад BTC)", reply_markup=back_menu())
            return

        if text == "✏️ Редагувати токен":
            # Динамічні кнопки з existing tokens
            symbols_map = load_symbols()
            tokens = sorted(symbols_map.keys())

            if tokens:
                user_state[chat_id] = {"step": "symbol_edit_name"}
                send(
                    chat_id,
                    "📌 Обери токен для редагування:",
                    reply_markup=dynamic_symbols_keyboard(tokens)
                )
            else:
                send(chat_id, "⚠️ Немає токенів для редагування", reply_markup=symbols_menu())
            return

        if text == "🗑 Видалити токен":
            # Динамічні кнопки з existing tokens
            symbols_map = load_symbols()
            tokens = sorted(symbols_map.keys())

            if tokens:
                user_state[chat_id] = {"step": "symbol_delete_name"}
                send(
                    chat_id,
                    "📌 Обери токен для видалення:",
                    reply_markup=dynamic_symbols_keyboard(tokens)
                )
            else:
                send(chat_id, "⚠️ Немає токенів для видалення", reply_markup=symbols_menu())
            return

    # ---- ADD SYMBOL: NAME ----
    if step == "symbol_add_name":
        if text == "⬅️ Назад":
            user_state[chat_id] = {"step": "symbols_menu"}
            send(chat_id, "⚙️ Параметри токенів", reply_markup=symbols_menu())
            return

        symbol = normalize_symbol(text)

        if get_symbol_params(symbol):
            send(chat_id, f"⚠️ Токен {symbol} вже існує. Використай редагування.")
            return

        user_state[chat_id] = {
            "step": "symbol_add_params",
            "symbol": symbol,
            "params": {},
            "current_param": "short_threshold"
        }

        send(chat_id, f"📝 <b>{symbol}</b>\n\nВведи значення для <b>Short threshold</b> (0.25):")
        return

    # ---- ADD SYMBOL: PARAMS ----
    if step == "symbol_add_params":
        try:
            value = float(text)
        except ValueError:
            send(chat_id, "❌ Некоректне значення, введи число")
            return

        symbol = user_state[chat_id]["symbol"]
        params = user_state[chat_id]["params"]
        current_param = user_state[chat_id]["current_param"]

        params[current_param] = value

        # Порядок параметрів (без risk_usdt)
        param_order = [
            ("short_threshold", "Short threshold", "0.25"),
            ("middle_threshold", "Middle threshold", "0.5"),
            ("long_threshold", "Long threshold", "1.0"),
            ("sl_small_pct", "Stop Loss Small, %", "0.001"),
            ("sl_big_pct", "Stop Loss Big, %", "0.002")
        ]

        current_index = next(i for i, (key, _, _) in enumerate(param_order) if key == current_param)

        if current_index < len(param_order) - 1:
            next_param, next_name, next_default = param_order[current_index + 1]
            user_state[chat_id]["current_param"] = next_param
            send(chat_id, f"Введи значення для <b>{next_name}</b> ({next_default}):")
        else:
            add_symbol(symbol, params)

            from config import load_symbols as cfg_load
            import config
            config.SYMBOLS = cfg_load()

            send(
                chat_id,
                f"✅ Токен <b>{symbol}</b> додано\n\n"
                f"Short threshold: {params['short_threshold']}\n"
                f"Middle threshold: {params['middle_threshold']}\n"
                f"Long threshold: {params['long_threshold']}\n"
                f"SL Small %: {params['sl_small_pct']}\n"
                f"SL Big %: {params['sl_big_pct']}",
                reply_markup=symbols_menu()
            )
            user_state[chat_id] = {"step": "symbols_menu"}
        return

    # ---- EDIT SYMBOL: NAME ----
    if step == "symbol_edit_name":
        if text == "⬅️ Назад":
            user_state[chat_id] = {"step": "symbols_menu"}
            send(chat_id, "⚙️ Параметри токенів", reply_markup=symbols_menu())
            return

        symbol = normalize_symbol(text)
        params = get_symbol_params(symbol)

        if not params:
            send(chat_id, f"⚠️ Токен {symbol} не знайдено")
            return

        user_state[chat_id] = {
            "step": "symbol_edit_params",
            "symbol": symbol,
            "params": params.copy(),
            "current_param": "short_threshold"
        }

        send(
            chat_id,
            f"📝 <b>{symbol}</b>\n\n"
            f"Поточні параметри:\n"
            f"Short threshold: {params['short_threshold']}\n"
            f"Middle threshold: {params['middle_threshold']}\n"
            f"Long threshold: {params['long_threshold']}\n"
            f"SL Small %: {params['sl_small_pct']}\n"
            f"SL Big %: {params['sl_big_pct']}\n\n"
            f"Введи нове значення для <b>Short threshold</b> ({params['short_threshold']}):"
        )
        return

    # ---- EDIT SYMBOL: PARAMS ----
    if step == "symbol_edit_params":
        try:
            value = float(text)
        except ValueError:
            send(chat_id, "❌ Некоректне значення, введи число")
            return

        symbol = user_state[chat_id]["symbol"]
        params = user_state[chat_id]["params"]
        current_param = user_state[chat_id]["current_param"]

        params[current_param] = value

        # Порядок параметрів (без risk_usdt)
        param_order = [
            ("short_threshold", "Short threshold"),
            ("middle_threshold", "Middle threshold"),
            ("long_threshold", "Long threshold"),
            ("sl_small_pct", "Stop Loss Small, %"),
            ("sl_big_pct", "Stop Loss Big, %")
        ]

        current_index = next(i for i, (key, _) in enumerate(param_order) if key == current_param)

        if current_index < len(param_order) - 1:
            next_param, next_name = param_order[current_index + 1]
            user_state[chat_id]["current_param"] = next_param
            send(chat_id, f"Введи нове значення для <b>{next_name}</b> ({params[next_param]}):")
        else:
            update_symbol(symbol, params)

            from config import load_symbols as cfg_load
            import config
            config.SYMBOLS = cfg_load()

            send(
                chat_id,
                f"✅ Токен <b>{symbol}</b> оновлено\n\n"
                f"Short threshold: {params['short_threshold']}\n"
                f"Middle threshold: {params['middle_threshold']}\n"
                f"Long threshold: {params['long_threshold']}\n"
                f"SL Small %: {params['sl_small_pct']}\n"
                f"SL Big %: {params['sl_big_pct']}",
                reply_markup=symbols_menu()
            )
            user_state[chat_id] = {"step": "symbols_menu"}
        return

    # ---- DELETE SYMBOL ----
    if step == "symbol_delete_name":
        if text == "⬅️ Назад":
            user_state[chat_id] = {"step": "symbols_menu"}
            send(chat_id, "⚙️ Параметри токенів", reply_markup=symbols_menu())
            return

        symbol = normalize_symbol(text)

        if delete_symbol(symbol):
            from config import load_symbols as cfg_load
            import config
            config.SYMBOLS = cfg_load()

            send(
                chat_id,
                f"✅ Токен <b>{symbol}</b> видалено",
                reply_markup=symbols_menu()
            )
        else:
            send(
                chat_id,
                f"❌ Токен <b>{symbol}</b> не знайдено",
                reply_markup=symbols_menu()
            )

        user_state[chat_id] = {"step": "symbols_menu"}
        return


def handle_callback(chat_id, data, send_msg):
    """Обробка callback кнопок"""
    if data.startswith("tf:"):
        timeframe = data.split(":")[1]

        state = user_state.get(chat_id)
        symbol = state.get("symbol") if state else None
        custom_price = state.get("custom_price") if state else None

        if not symbol:
            send_msg(chat_id, "❌ Символ не вибрано")
            return None

        return {
            "action": "view_chart",
            "symbol": symbol,
            "timeframe": timeframe
        }

    if data == "back":
        user_state[chat_id] = {"step": "enter_symbol"}
        send_msg(chat_id, "✍️ Введи назву токена (наприклад BTC)", reply_markup=back_menu())
        return None

    return None
