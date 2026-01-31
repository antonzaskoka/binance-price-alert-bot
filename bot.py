"""
Головний файл бота
"""
# ==============================
# LOGGING
# ==============================
from utils.logging_config import setup_logging
setup_logging()

import logging
logger = logging.getLogger(__name__)

# ==============================
# IMPORTS
# ==============================
import time
import requests
from datetime import datetime, timezone

from config import SYMBOLS, ADMIN_CHAT_ID, ALIVE_INTERVAL, RISK_USDT
from alerts.symbols_manager import load_symbols as reload_symbols
from database.db_manager import get_conn, ensure_tables, sync_klines
from alerts.checker import check_alerts
from telegram.client import send_telegram_message
from telegram.menu_handler import handle_text, handle_callback, show_main_menu
from charts.menu_chart import build_menu_chart
from utils.binance_api import fetch_last_bars
from charts.level_detector import detect_support_resistance, format_detected_level_info
from alerts.alert_types import calculate_range_pct

# ==============================
# TELEGRAM UPDATES
# ==============================
LAST_UPDATE_ID = 0

def get_telegram_updates():
    """Отримує оновлення від Telegram"""
    global LAST_UPDATE_ID

    from config import TG_API

    try:
        resp = requests.get(
            f"{TG_API}/getUpdates",
            params={
                "timeout": 5,
                "offset": LAST_UPDATE_ID + 1,
                "allowed_updates": ["message", "callback_query"]
            },
            timeout=10
        ).json()
    except requests.exceptions.RequestException as e:
        logger.warning(f"Telegram getUpdates timeout: {e}")
        return []

    updates = resp.get("result", [])
    if updates:
        LAST_UPDATE_ID = updates[-1]["update_id"]

    return updates


def handle_update(update, conn):
    """Обробка одного оновлення від Telegram"""
    logger.info(f"UPDATE RECEIVED: {update}")

    # ===== CALLBACK QUERY =====
    if "callback_query" in update:
        callback = update["callback_query"]
        chat_id = callback["message"]["chat"]["id"]
        data = callback["data"]

        result = handle_callback(
            chat_id,
            data,
            send_telegram_message
        )

        if not result or result.get("action") != "view_chart":
            return

        symbol = result["symbol"]
        timeframe = result["timeframe"]

        send_telegram_message(chat_id, "⏳ Будую графік...")

        try:
            df = fetch_last_bars(symbol, timeframe, 90)

            detected_level = detect_support_resistance(df, tolerance_pct=0.0001)

            current_price = df["open"].iloc[-1]

            caption = f"📊 <b>{symbol}</b> | {timeframe}\n"
            caption += f"💰 Price (last bar open): <b>{current_price:.4f}</b>"

            # Конвертуємо таймфрейм у хвилини
            tf_to_minutes = {
                "1m": 1,
                "5m": 5,
                "15m": 15,
                "1h": 60,
                "4h": 240,
                "1d": 1440
            }

            minutes_per_bar = tf_to_minutes.get(timeframe, 1)

            bars_55m = min(55 // minutes_per_bar, len(df))
            bars_20m = min(20 // minutes_per_bar, len(df))
            bars_2m = min(2 // minutes_per_bar, len(df))

            caption += f"\n\n📊 Price movement:"

            if bars_55m > 0:
                df_55 = df.tail(bars_55m)
                long_pct = calculate_range_pct(df_55, current_price)
                caption += f"\n   Long (~55m): <b>{long_pct:.2f}%</b>"

            if bars_20m > 0:
                df_20 = df.tail(bars_20m)
                middle_pct = calculate_range_pct(df_20, current_price)
                caption += f"\n   Middle (~20m): <b>{middle_pct:.2f}%</b>"

            if bars_2m > 0:
                df_2 = df.tail(bars_2m)
                short_pct = calculate_range_pct(df_2, current_price)
                caption += f"\n   Short (~2m): <b>{short_pct:.2f}%</b>"

            # Розрахунок SL та позицій (використовуємо глобальний RISK_USDT)
            # Розрахунок SL та позицій (використовуємо глобальний RISK_USDT)
            cfg = SYMBOLS.get(symbol)
            if cfg:
                sl_small = current_price * cfg["sl_small_pct"]
                sl_big = current_price * cfg["sl_big_pct"]

                if sl_small > 0 and sl_big > 0:
                    size_small_sl = RISK_USDT / sl_small
                    size_big_sl = RISK_USDT / sl_big

                    # Ціни входу для позицій
                    price_big = current_price + sl_small       # велика позиція = маленький SL
                    price_small = current_price + sl_big       # мала позиція = великий SL

                    caption += f"\n\n💲  SL Small: <b>${sl_small:.4f}</b>"
                    caption += f"\n🌎🚀 Position (big): <b>{size_small_sl:.4f} {symbol[:-4]}</b> @ {price_big:.4f}"
                    caption += f"\n\n💲💸 SL Big: <b>${sl_big:.4f}</b>"
                    caption += f"\n،🚀 Position (small): <b>{size_big_sl:.4f} {symbol[:-4]}</b> @ {price_small:.4f}"
            # Виявлений рівень
            if detected_level:
                caption += format_detected_level_info(detected_level, current_price)

            chart_path = build_menu_chart(
                df=df,
                symbol=symbol,
                timeframe=timeframe,
                detected_level=detected_level
            )

            from telegram.client import send_menu_chart
            send_menu_chart(
                chat_id=chat_id,
                chart_path=chart_path,
                caption=caption
            )

            show_main_menu(chat_id, send_telegram_message)

        except Exception:
            logger.exception("Menu chart error")
            send_telegram_message(
                chat_id,
                "❌ Не вдалося побудувати графік"
            )
            show_main_menu(chat_id, send_telegram_message)

        return

    # ===== TEXT MESSAGE =====
    if "message" not in update:
        return

    message = update["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    if not text:
        return

    if text in ("/start", "/menu"):
        show_main_menu(chat_id, send_telegram_message)
        return

    handle_text(
        chat_id,
        text,
        send_telegram_message
    )


# ==============================
# ALIVE HEARTBEAT
# ==============================
LAST_ALIVE_PING = None


def send_alive_ping(chat_id):
    """Надсилає heartbeat повідомлення"""
    global LAST_ALIVE_PING

    now = datetime.now(timezone.utc)

    if LAST_ALIVE_PING and now - LAST_ALIVE_PING < ALIVE_INTERVAL:
        return

    msg = (
        "✅ <b>Bot is alive</b>\n"
        f"🕒 UTC time: {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"📡 Monitoring: {', '.join(SYMBOLS.keys())}"
    )

    send_telegram_message(chat_id, msg)
    logger.info("Alive ping sent")

    LAST_ALIVE_PING = now


# ==============================
# MAIN
# ==============================
def main():
    """Головний цикл бота"""
    logger.info("Bot started")

    conn = get_conn()
    for s in SYMBOLS:
        ensure_tables(conn, s)

    # Динамічне оновлення SYMBOLS при зміні файлу
    def refresh_symbols():
        """Перезавантажує список токенів"""
        import config
        config.SYMBOLS = reload_symbols()

    # Обробка накопичених повідомлень
    updates = get_telegram_updates()
    for update in updates:
        handle_update(update, conn)

    last_alert_check = 0

    while True:
        try:
            # 1. ЗАВЖДИ ОБРОБЛЯЄМО TELEGRAM ОНОВЛЕННЯ
            updates = get_telegram_updates()
            for update in updates:
                handle_update(update, conn)

            # 2. ПЕРЕВІРЯЄМО АЛЕРТИ ТІЛЬКИ РАЗ НА ХВИЛИНУ
            current_time = time.time()

            if current_time - last_alert_check >= 60:
                refresh_symbols()

                from alerts.levels_manager import load_levels
                levels_map = load_levels()

                all_symbols = set(SYMBOLS.keys()) | set(levels_map.keys())

                for s in all_symbols:
                    ensure_tables(conn, s)

                    added = sync_klines(conn, s)
                    if added:
                        logger.info(f"{s}: synced {added} rows")

                    check_alerts(conn, s, ADMIN_CHAT_ID)

                last_alert_check = current_time

        except Exception:
            logger.exception("Main loop error")


if __name__ == "__main__":
    main()
