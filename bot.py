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
from telegram.client import send_telegram_message, send_alert_chart
from telegram.menu_handler import handle_text, handle_callback, show_main_menu
from charts.menu_chart import build_menu_chart
from utils.binance_api import fetch_last_bars
from charts.level_detector import detect_support_resistance, format_detected_level_info
from alerts.alert_types import calculate_range_pct
from alerts.volume_alert import check_volume_alert, format_volume_alert
from charts.volume_alert_chart import build_volume_alert_chart
from database.db_manager import sync_hourly_klines
from config import VOLUME_CHECK_INTERVAL
from database.db_cleanup import cleanup_old_data
from utils.binance_markets import fetch_all_usdt_symbols

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
        custom_price = result.get("custom_price")

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
                    caption += f"\n🚀 Position (small): <b>{size_big_sl:.4f} {symbol[:-4]}</b> @ {price_small:.4f}"
            # Виявлений рівень
            if detected_level:
                caption += format_detected_level_info(detected_level, current_price)

            chart_path = build_menu_chart(
                df=df,
                symbol=symbol,
                timeframe=timeframe,
                detected_level=detected_level,
                custom_price=custom_price
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

    if text == "/backup":
        import json
        import os
        from config import LEVELS_FILE, SYMBOLS_FILE
        
        try:
            msg = "📦 <b>Backup даних:</b>\n\n"
            
            # Levels
            if os.path.exists(LEVELS_FILE):
                with open(LEVELS_FILE, "r", encoding="utf-8") as f:
                    levels_data = json.load(f)
                msg += f"<b>levels.json</b> ({len(levels_data)} токенів):\n"
                msg += f"<pre>{json.dumps(levels_data, indent=2, ensure_ascii=False)}</pre>\n\n"
            else:
                msg += "<b>levels.json</b>: файл не знайдено\n\n"
            
            # Symbols
            if os.path.exists(SYMBOLS_FILE):
                with open(SYMBOLS_FILE, "r", encoding="utf-8") as f:
                    symbols_data = json.load(f)
                msg += f"<b>symbols.json</b> ({len(symbols_data)} токенів):\n"
                msg += f"<pre>{json.dumps(symbols_data, indent=2, ensure_ascii=False)}</pre>"
            else:
                msg += "<b>symbols.json</b>: файл не знайдено"
            
            send_telegram_message(chat_id, msg)
            logger.info(f"/backup command executed for chat {chat_id}")
            
        except Exception as e:
            logger.error(f"/backup error: {e}")
            send_telegram_message(chat_id, f"❌ Помилка при отриманні backup: {e}")
        
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

    from database.db_manager import ensure_alerts_table
    ensure_alerts_table(conn)

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
    last_volume_check = 0
    last_cleanup = 0
    last_markets_update = 0  
    binance_symbols = []  # ✅ Список всіх токенів з Binance

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
                import alerts.levels_manager as lm
                lm._LEVELS_CACHE = {}
                lm._LEVELS_MTIME = None

                levels_map = load_levels()

                all_symbols = set(SYMBOLS.keys()) | set(levels_map.keys())

                for s in all_symbols:
                    ensure_tables(conn, s)

                    added = sync_klines(conn, s)
                    if added:
                        logger.info(f"{s}: synced {added} rows")

                    check_alerts(conn, s, ADMIN_CHAT_ID)

                last_alert_check = current_time
            
            # ✅ TYPE 3: Volume alerts (кожну годину)
            if current_time - last_volume_check >= VOLUME_CHECK_INTERVAL:
                logger.info("Checking volume alerts...")
                
                # ✅ Оновлюємо список токенів з Binance кожні 6 годин
                if current_time - last_markets_update >= 21600:  # 6 годин
                    binance_symbols = fetch_all_usdt_symbols()  # ✅ Без фільтрів
                    last_markets_update = current_time
                    logger.info(f"Updated markets list: {len(binance_symbols)} USDT pairs")
                
                # ✅ Перевіряємо ВСІ токени з Binance (не тільки з symbols.json)
                excluded_symbols = ["XAUUSDT", "XAGUSDT"]
                
                for s in binance_symbols:
                    if s in excluded_symbols:
                        continue
                    
                    # ✅ Для volume alerts cfg не обов'язковий
                    cfg = SYMBOLS.get(s, {
                        "sl_small_pct": 0.01,
                        "sl_big_pct": 0.02
                    })
                    
                    added_hourly = sync_hourly_klines(conn, s)
                    if added_hourly:
                        logger.info(f"{s}: synced {added_hourly} hourly bars")
                    
                    alert_data = check_volume_alert(conn, s, cfg)
                    
                    if alert_data:
                        msg = format_volume_alert(alert_data)
                        
                        from database.models import load_hourly_bars
                        df = load_hourly_bars(conn, s, limit=90)
                        
                        if df is not None:
                            from alerts.volume_alert import calculate_volume_usdt
                            df = calculate_volume_usdt(df)
                            
                            chart_path = build_volume_alert_chart(df, s)
                            
                            send_alert_chart(
                                chat_id=ADMIN_CHAT_ID,
                                symbol=s,
                                timeframe="1h",
                                chart_path=chart_path,
                                price=alert_data["current_price"],
                                reason=msg
                            )
                            
                            logger.info(f"Volume alert sent: {s}")
                    
                    # ✅ ЗАТРИМКА між токенами (захист від rate limit)
                    import time
                    time.sleep(0.5)  # 500мс між токенами
                    
                    cfg = SYMBOLS.get(s)
                    if not cfg:
                        continue
                    
                    # Синхронізуємо годинні дані
                    added_hourly = sync_hourly_klines(conn, s)
                    if added_hourly:
                        logger.info(f"{s}: synced {added_hourly} hourly bars")
                    
                    # Перевіряємо volume alert
                    alert_data = check_volume_alert(conn, s, cfg)
                    
                    if alert_data:
                        msg = format_volume_alert(alert_data)
                        
                        # Будуємо графік
                        from database.models import load_hourly_bars
                        df = load_hourly_bars(conn, s, limit=90)
                        
                        if df is not None:
                            from alerts.volume_alert import calculate_volume_usdt
                            df = calculate_volume_usdt(df)
                            
                            chart_path = build_volume_alert_chart(df, s)
                            
                            from telegram.client import send_alert_chart
                            send_alert_chart(
                                chat_id=ADMIN_CHAT_ID,
                                symbol=s,
                                timeframe="1h",
                                chart_path=chart_path,
                                price=alert_data["current_price"],
                                reason=msg
                            )
                            
                            logger.info(f"Volume alert sent: {s}")
                
                last_volume_check = current_time

            # ✅ ОЧИЩЕННЯ БД (раз на добу)
            if current_time - last_cleanup >= 86400:  # 24 години
                logger.info("Starting database cleanup...")
                try:
                    deleted = cleanup_old_data(conn, days_to_keep=30)
                    logger.info(f"Database cleanup finished: {deleted} rows deleted")
                except Exception as e:
                    logger.error(f"Database cleanup error: {e}")
                
                last_cleanup = current_time

        except Exception:
            logger.exception("Main loop error")


if __name__ == "__main__":
    main()
