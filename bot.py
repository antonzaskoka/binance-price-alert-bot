"""
Головний файл бота
"""
# ==============================
# LOGGING
# ==============================
from utils.logging_config import setup_logging
setup_logging()

import os
import time
import logging
logger = logging.getLogger(__name__)

# ==============================
# IMPORTS
# ==============================
import time
import requests
import config

from datetime import datetime, timezone
from alerts.symbols_manager import load_symbols as reload_symbols
from alerts.checker import check_alerts
from alerts.alert_types import calculate_range_pct
from alerts.alert_formatter import calculate_atr
from alerts.volume_alert import check_volume_alert, format_volume_alert, calculate_volume_usdt
from alerts.levels_manager import load_levels
import alerts.levels_manager as lm
from config import SYMBOLS, ADMIN_CHAT_ID, ALIVE_INTERVAL, RISK_USDT
from config import VOLUME_CHECK_INTERVAL
from config import LEVELS_FILE, SYMBOLS_FILE
from charts.menu_chart import build_menu_chart
from charts.level_detector import detect_support_resistance, format_detected_level_info
from charts.volume_alert_chart import build_volume_alert_chart
from database.db_manager import get_conn, ensure_tables, sync_klines
from database.db_manager import sync_hourly_klines
from database.db_cleanup import cleanup_old_data
from database.models import load_hourly_bars
from database.db_manager import ensure_alerts_table
from telegram.client import send_telegram_message, send_alert_chart, send_menu_chart
from telegram.menu_handler import handle_text, handle_callback, show_main_menu
from utils.binance_api import fetch_last_bars
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

            # Розрахунок ATR за 90 барів обраного таймфрейму     
            # Беремо останні 90 барів (незалежно від таймфрейму)
            atr_bars = min(90, len(df))
            
            if atr_bars > 0:
                df_atr = df.tail(atr_bars)
                atr = calculate_atr(df_atr)
            else:
                atr = None
            
            # Розраховуємо SL та позицію
            cfg = SYMBOLS.get(symbol)
            if cfg:
                sl_small = current_price * cfg["sl_small_pct"]
                sl_big = current_price * cfg["sl_big_pct"]
                
                # ✅ ДОДАНО: ATR з кольоровим емоджі
                if atr:
                    # Визначаємо колір емоджі
                    if atr < sl_small:
                        atr_emoji = "🟢"  # green - маленький ATR
                    elif atr < sl_big:
                        atr_emoji = "🟡"  # yellow - середній ATR
                    else:
                        atr_emoji = "🔴"  # red - великий ATR
                    
                    # Розраховуємо ATR як відсоток від ціни
                    atr_pct = (atr / current_price) * 100
                    
                    caption += f"\n\n📐 ATR (90 bars {timeframe}): {atr_emoji} <b>{atr:.4f}</b> ({atr_pct:.2f}%)"
                
                if sl_small > 0 and sl_big > 0:
                    size_small_sl = RISK_USDT / sl_small
                    size_big_sl = RISK_USDT / sl_big
                    
                    caption += f"\n\n🔻 SL SMALL: <b>${sl_small:.4f}</b>"
                    caption += f"\n   Position: <b>{size_small_sl:.4f} {symbol[:-4]}</b>"
                    caption += f"\n\n🔺 SL BIG: <b>${sl_big:.4f}</b>"
                    caption += f"\n   Position: <b>{size_big_sl:.4f} {symbol[:-4]}</b>"

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
        try:
            # Читаємо levels.json
            with open(LEVELS_FILE, "r") as f:
                levels_content = f.read()
            
            # Читаємо symbols.json
            with open(SYMBOLS_FILE, "r") as f:
                symbols_content = f.read()
            
            # Формуємо повідомлення
            full_msg = (
                f"📋 <b>BACKUP</b>\n\n"
                f"<b>levels.json:</b>\n<pre>{levels_content}</pre>\n\n"
                f"<b>symbols.json:</b>\n<pre>{symbols_content}</pre>"
            )
            
            # Розбиваємо на частини по 4000 символів (безпечний ліміт)
            max_length = 4000
            
            if len(full_msg) <= max_length:
                send_telegram_message(chat_id, full_msg)
            else:
                # Відправляємо окремо levels.json
                levels_msg = f"📋 <b>levels.json:</b>\n<pre>{levels_content}</pre>"
                
                if len(levels_msg) <= max_length:
                    send_telegram_message(chat_id, levels_msg)
                else:
                    # Розбиваємо levels на частини
                    chunks = [levels_content[i:i+3800] for i in range(0, len(levels_content), 3800)]
                    for i, chunk in enumerate(chunks, 1):
                        send_telegram_message(
                            chat_id, 
                            f"📋 <b>levels.json (частина {i}/{len(chunks)}):</b>\n<pre>{chunk}</pre>"
                        )
                
                # Відправляємо symbols.json
                symbols_msg = f"📋 <b>symbols.json:</b>\n<pre>{symbols_content}</pre>"
                send_telegram_message(chat_id, symbols_msg)
            
        except Exception as e:
            logger.exception("Backup error")
            send_telegram_message(chat_id, f"❌ Помилка backup: {e}")
        
        return

    if text == "/cooldowns":
        try:
            from database.db_manager import get_conn
            conn = get_conn()
            
            cursor = conn.execute(
                """
                SELECT symbol, alert_type, triggered_at_utc 
                FROM alerts 
                ORDER BY triggered_at_utc DESC 
                LIMIT 20
                """
            )
            
            rows = cursor.fetchall()
            
            if rows:
                msg = "📋 <b>Останні 20 алертів:</b>\n\n"
                for symbol, alert_type, triggered_at in rows:
                    msg += f"• {symbol} - <code>{alert_type}</code>\n  {triggered_at}\n\n"
            else:
                msg = "⚠️ Немає записів в базі алертів"
            
            send_telegram_message(chat_id, msg)
        except Exception as e:
            logger.exception("Cooldowns error")
            send_telegram_message(chat_id, f"❌ Помилка: {e}")
        
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

    ensure_alerts_table(conn)

    for s in SYMBOLS:
        ensure_tables(conn, s)

    # таймери для контролю часу
    last_alert_check = 0
    last_volume_check = 0
    last_cleanup = 0
    last_data_sync = 0  # Новий таймер для синхронізації даних
    
    # Змінні для контролю завантаження
    data_sync_duration = 20  # Завантажуємо дані 20 секунд
    data_sync_cooldown = 60  # Раз на хвилину
    is_syncing = False

    # Динамічне оновлення SYMBOLS при зміні файлу
    def refresh_symbols():
        """Перезавантажує список токенів"""
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
            current_time = time.time()
            current_datetime = datetime.now()
            current_minute = current_datetime.minute
            
            # ===== 1. ЗАВЖДИ ОБРОБЛЯЄМО TELEGRAM =====
            updates = get_telegram_updates()
            for update in updates:
                handle_update(update, conn)

            # ===== 2. ХВИЛИННІ БАРИ ДЛЯ SYMBOLS.JSON (щохвилини) =====
            if current_time - last_alert_check >= 60:
                refresh_symbols()
                
                # Тільки токени з symbols.json
                for s in SYMBOLS.keys():
                    ensure_tables(conn, s)
                    
                    added = sync_klines(conn, s)
                    if added:
                        logger.info(f"{s}: synced {added} 1m bars")
                    
                    # Перевіряємо threshold alerts
                    check_alerts(conn, s, ADMIN_CHAT_ID)
                
                last_alert_check = current_time
            
            # ===== 3. ХВИЛИННІ БАРИ ДЛЯ LEVELS.JSON (15-та і 45-та хвилини) =====
            if current_minute == 15 or current_minute == 45:
                # Перевіряємо чи вже обробили цю хвилину
                if not hasattr(main, 'last_levels_minute') or main.last_levels_minute != current_minute:
                    main.last_levels_minute = current_minute
                    
                    logger.info(f"Loading bars for levels.json tokens (minute {current_minute})")
                    
                    lm._LEVELS_CACHE = {}
                    lm._LEVELS_MTIME = None
                    levels_map = load_levels()
                    
                    # Тільки токени з levels.json (виключаємо ті що вже в symbols.json)
                    levels_only_symbols = set(levels_map.keys()) - set(SYMBOLS.keys())
                    
                    for s in levels_only_symbols:
                        ensure_tables(conn, s)
                        
                        added = sync_klines(conn, s)
                        if added:
                            logger.info(f"{s}: synced {added} 1m bars (levels)")
                        
                        # Перевіряємо level touch alerts
                        cfg = SYMBOLS.get(s, {"sl_small_pct": 0.01, "sl_big_pct": 0.02})
                        check_alerts(conn, s, ADMIN_CHAT_ID)
            
            # ===== 4. ГОДИННІ БАРИ ДЛЯ VOLUME ALERTS (3-тя хвилина кожної години) =====
            if current_minute == 3:
                # Перевіряємо чи вже обробили цю хвилину
                if not hasattr(main, 'last_volume_hour') or main.last_volume_hour != current_datetime.hour:
                    main.last_volume_hour = current_datetime.hour
                    
                    logger.info(f"Loading hourly bars for volume alerts (hour {current_datetime.hour})")
                    
                    # Оновлюємо список токенів з Binance кожні 6 годин
                    if current_time - last_markets_update >= 21600:
                        binance_symbols = fetch_all_usdt_symbols()
                        last_markets_update = current_time
                        logger.info(f"Updated markets list: {len(binance_symbols)} USDT pairs")
                    
                    excluded_symbols = ["XAUUSDT", "XAGUSDT"]
                    
                    for s in binance_symbols:
                        if s in excluded_symbols:
                            continue
                        
                        cfg = SYMBOLS.get(s, {"sl_small_pct": 0.01, "sl_big_pct": 0.02})
                        
                        # Синхронізуємо годинні дані
                        added_hourly = sync_hourly_klines(conn, s)
                        if added_hourly:
                            logger.info(f"{s}: synced {added_hourly} hourly bars")
                        
                        # Перевіряємо volume alert
                        alert_data = check_volume_alert(conn, s, cfg)
                        
                        if alert_data:
                            msg = format_volume_alert(alert_data)
                            
                            df = load_hourly_bars(conn, s, limit=90)
                            
                            if df is not None:
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
                        
                        time.sleep(0.5)  # Затримка між токенами

            # ===== 5. ОЧИЩЕННЯ БД (раз на добу, о 03:00) =====
            if current_datetime.hour == 3 and current_minute == 0:
                if not hasattr(main, 'last_cleanup_day') or main.last_cleanup_day != current_datetime.day:
                    main.last_cleanup_day = current_datetime.day
                    
                    logger.info("Starting database cleanup...")
                    try:
                        deleted = cleanup_old_data(conn, days_to_keep=30)
                        logger.info(f"Database cleanup finished: {deleted} rows deleted")
                    except Exception as e:
                        logger.error(f"Database cleanup error: {e}")
            
            # Невелика затримка між ітераціями
            time.sleep(0.1)

        except Exception:
            logger.exception("Main loop error")
            time.sleep(5)


if __name__ == "__main__":
    main()
