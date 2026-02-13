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
import requests
import config

from datetime import datetime, timezone
from alerts.symbols_manager import load_symbols as reload_symbols
from alerts.checker import check_alerts
from alerts.alert_types import calculate_range_pct
from alerts.alert_formatter import calculate_atr
from alerts.volume_alert import check_volume_alert, format_volume_alert
from alerts.levels_manager import load_levels
import alerts.levels_manager as lm
from config import SYMBOLS, ADMIN_CHAT_ID, ALIVE_INTERVAL, RISK_USDT, LEVELS_FILE, SYMBOLS_FILE
from charts.menu_chart import build_menu_chart
from charts.level_detector import detect_support_resistance, format_detected_level_info
from charts.volume_alert_chart import build_volume_alert_chart
from database.db_manager import get_conn, ensure_tables, sync_klines, sync_hourly_klines, ensure_alerts_table
from database.db_cleanup import cleanup_old_data
from database.models import load_hourly_bars
from telegram.client import send_telegram_message, send_alert_chart, send_menu_chart
from telegram.menu_handler import handle_text, handle_callback, show_main_menu
from utils.binance_api import fetch_last_bars
from utils.binance_markets import fetch_all_usdt_symbols

logger = logging.getLogger(__name__)

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
    
    # ===== CALLBACK QUERY =====
    if "callback_query" in update:
        callback = update["callback_query"]
        chat_id = callback["message"]["chat"]["id"]
        data = callback["data"]

        result = handle_callback(chat_id, data, send_telegram_message)

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
            tf_to_minutes = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}
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
                
                if atr:
                    if atr < sl_small:
                        atr_emoji = "🟢"
                    elif atr < sl_big:
                        atr_emoji = "🟡"
                    else:
                        atr_emoji = "🔴"
                    
                    atr_pct = (atr / current_price) * 100
                    caption += f"\n\n📐 ATR (90 bars {timeframe}): {atr_emoji} <b>{atr:.4f}</b> ({atr_pct:.2f}%)"
                
                if sl_small > 0 and sl_big > 0:
                    size_small_sl = RISK_USDT / sl_small
                    size_big_sl = RISK_USDT / sl_big
                    
                    caption += f"\n\n🔻 SL SMALL: <b>${sl_small:.4f}</b>"
                    caption += f"\n   Position: <b>{size_small_sl:.4f} {symbol[:-4]}</b>"
                    caption += f"\n\n🔺 SL BIG: <b>${sl_big:.4f}</b>"
                    caption += f"\n   Position: <b>{size_big_sl:.4f} {symbol[:-4]}</b>"

            if detected_level:
                caption += format_detected_level_info(detected_level, current_price)

            chart_path = build_menu_chart(
                df=df,
                symbol=symbol,
                timeframe=timeframe,
                detected_level=detected_level,
                custom_price=custom_price
            )

            send_menu_chart(chat_id=chat_id, chart_path=chart_path, caption=caption)
            show_main_menu(chat_id, send_telegram_message)

        except Exception:
            logger.exception("Menu chart error")
            send_telegram_message(chat_id, "❌ Не вдалося побудувати графік")
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
            with open(LEVELS_FILE, "r") as f:
                levels_content = f.read()
            
            with open(SYMBOLS_FILE, "r") as f:
                symbols_content = f.read()
            
            full_msg = (
                f"📋 <b>BACKUP</b>\n\n"
                f"<b>levels.json:</b>\n<pre>{levels_content}</pre>\n\n"
                f"<b>symbols.json:</b>\n<pre>{symbols_content}</pre>"
            )
            
            max_length = 4000
            
            if len(full_msg) <= max_length:
                send_telegram_message(chat_id, full_msg)
            else:
                levels_msg = f"📋 <b>levels.json:</b>\n<pre>{levels_content}</pre>"
                
                if len(levels_msg) <= max_length:
                    send_telegram_message(chat_id, levels_msg)
                else:
                    chunks = [levels_content[i:i+3800] for i in range(0, len(levels_content), 3800)]
                    for i, chunk in enumerate(chunks, 1):
                        send_telegram_message(
                            chat_id, 
                            f"📋 <b>levels.json (частина {i}/{len(chunks)}):</b>\n<pre>{chunk}</pre>"
                        )
                
                symbols_msg = f"📋 <b>symbols.json:</b>\n<pre>{symbols_content}</pre>"
                send_telegram_message(chat_id, symbols_msg)
            
        except Exception as e:
            logger.exception("Backup error")
            send_telegram_message(chat_id, f"❌ Помилка backup: {e}")
        
        return

    if text == "/cooldowns":
        try:
            cursor = conn.execute(
                """
                SELECT symbol, alert_type, last_trigger_ms 
                FROM alert_state 
                ORDER BY last_trigger_ms DESC 
                LIMIT 20
                """
            )
            
            rows = cursor.fetchall()
            
            if rows:
                msg = "📋 <b>Останні 20 алертів:</b>\n\n"
                for symbol, alert_type, last_trigger_ms in rows:
                    dt = datetime.fromtimestamp(last_trigger_ms / 1000)
                    time_str = dt.strftime('%Y-%m-%d %H:%M:%S')
                    
                    msg += f"• {symbol} - <code>{alert_type}</code>\n  {time_str}\n\n"
            else:
                msg = "⚠️ Немає записів в базі алертів"
            
            send_telegram_message(chat_id, msg)
        except Exception as e:
            logger.exception("Cooldowns error")
            send_telegram_message(chat_id, f"❌ Помилка: {e}")
        
        return

    if text == "/test":
        try:
            send_telegram_message(chat_id, "✅ Text message works!")
            
            df = fetch_last_bars("BTCUSDT", "1m", 90)
            chart_path = build_menu_chart(df, "BTCUSDT", "1m")
            
            send_alert_chart(
                chat_id=chat_id,
                symbol="BTCUSDT",
                timeframe="1m",
                chart_path=chart_path,
                price=df["close"].iloc[-1],
                reason="🧪 Test alert from /test command"
            )
            
            logger.info("Test alert sent")
            
        except Exception as e:
            logger.exception("Test command error")
            send_telegram_message(chat_id, f"❌ Test failed: {e}")
        
        return

    if text == "/export_db":
        try:
            import csv
            import io
            import zipfile
            from datetime import datetime
            
            send_telegram_message(chat_id, "📦 Експортую дані для BTC, ETH, XAU...")
            
            # ✅ Список токенів для експорту
            symbols_to_export = ["BTCUSDT", "ETHUSDT", "XAUUSDT"]
            
            # Створюємо ZIP архів в пам'яті
            zip_buffer = io.BytesIO()
            
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                exported_count = 0
                
                for symbol in symbols_to_export:
                    table = f"kline_{symbol.lower()}_1h"
                    
                    try:
                        # Читаємо дані з таблиці
                        cursor = conn.execute(f"""
                            SELECT open_time_utc, open, high, low, close, volume, 
                                   volume_usdt, volume_24h, volume_avg_14d, ratio
                            FROM {table}
                            ORDER BY open_time_ms ASC
                        """)
                        
                        rows = cursor.fetchall()
                        
                        if not rows:
                            logger.warning(f"No data for {symbol}")
                            continue
                        
                        # Створюємо CSV в пам'яті
                        csv_buffer = io.StringIO()
                        writer = csv.writer(csv_buffer)
                        
                        # Заголовки
                        writer.writerow([
                            "timestamp", "open", "high", "low", "close", "volume",
                            "volume_usdt", "volume_24h", "volume_avg_14d", "ratio"
                        ])
                        
                        # Дані
                        writer.writerows(rows)
                        
                        # Додаємо CSV в ZIP
                        csv_content = csv_buffer.getvalue()
                        zip_file.writestr(
                            f"{symbol}_hourly_data.csv",
                            csv_content.encode('utf-8')
                        )
                        
                        exported_count += 1
                        logger.info(f"Exported {symbol}: {len(rows)} bars")
                        
                    except Exception as e:
                        logger.error(f"Error exporting {symbol}: {e}")
                        continue
            
            if exported_count == 0:
                send_telegram_message(chat_id, "⚠️ Немає даних для експорту")
                return
            
            # Надсилаємо ZIP файл
            zip_buffer.seek(0)
            
            from config import TG_API
            import requests
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"hourly_data_{timestamp}.zip"
            
            files = {
                'document': (filename, zip_buffer.read(), 'application/zip')
            }
            
            data = {
                'chat_id': chat_id,
                'caption': (
                    f"📊 Hourly data export\n\n"
                    f"📦 Files: {exported_count}\n"
                    f"🪙 Tokens: {', '.join(symbols_to_export)}"
                )
            }
            
            response = requests.post(
                f"{TG_API}/sendDocument",
                data=data,
                files=files,
                timeout=60
            )
            
            if response.status_code == 200:
                send_telegram_message(chat_id, "✅ Експорт завершено!")
            else:
                logger.error(f"Telegram sendDocument error: {response.text}")
                send_telegram_message(chat_id, f"❌ Помилка відправки: {response.text}")
        
        except Exception as e:
            logger.exception("Export DB error")
            send_telegram_message(chat_id, f"❌ Помилка: {e}")
        
        return

    if text == "/test_levels":
        try:
            from alerts.levels_manager import load_levels
            
            send_telegram_message(chat_id, "🔍 Перевіряю level touch для levels.json...")
            
            lm._LEVELS_CACHE = {}
            lm._LEVELS_MTIME = None
            levels_map = load_levels()
            
            # Токени тільки з levels.json
            levels_only_symbols = set(levels_map.keys()) - set(SYMBOLS.keys())
            
            msg = f"📊 <b>Токени з levels.json:</b> {len(levels_only_symbols)}\n\n"
            
            checked = 0
            found_alerts = 0
            
            for s in list(levels_only_symbols)[:10]:  # Перші 10 для тесту
                ensure_tables(conn, s)
                
                # Синхронізуємо дані
                added = sync_klines(conn, s)
                
                # Перевіряємо алерти
                cfg = {"sl_small_pct": 0.01, "sl_big_pct": 0.02}
                
                # ✅ Викликаємо з cfg
                from alerts.checker import check_alerts
                
                # Тимчасово патчимо для тесту
                from alerts.alert_types import check_level_touch_alert
                alert_data = check_level_touch_alert(conn, s, cfg)
                
                if alert_data:
                    touched_level = alert_data["touched_level"]
                    msg += f"✅ {s}: level {touched_level} touched!\n"
                    found_alerts += 1
                
                checked += 1
            
            msg += f"\n📈 Перевірено: {checked}\n🔔 Знайдено торкань: {found_alerts}"
            
            send_telegram_message(chat_id, msg)
            
        except Exception as e:
            logger.exception("Test levels error")
            send_telegram_message(chat_id, f"❌ Помилка: {e}")
        
        return

    handle_text(chat_id, text, send_telegram_message)


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

    def refresh_symbols():
        """Перезавантажує список токенів"""
        config.SYMBOLS = reload_symbols()

    updates = get_telegram_updates()
    for update in updates:
        handle_update(update, conn)

    last_alert_check = 0
    last_markets_update = 0
    binance_symbols = []

    while True:
        try:
            current_time = time.time()
            current_datetime = datetime.now()
            current_minute = current_datetime.minute
            
            # ===== 1. TELEGRAM =====
            updates = get_telegram_updates()
            for update in updates:
                handle_update(update, conn)

            # ===== 2. ХВИЛИННІ БАРИ SYMBOLS.JSON =====
            if current_time - last_alert_check >= 60:
                refresh_symbols()
                
                for s in SYMBOLS.keys():
                    ensure_tables(conn, s)
                    added = sync_klines(conn, s)
                    if added:
                        logger.info(f"{s}: synced {added} 1m bars")
                    
                    check_alerts(conn, s, ADMIN_CHAT_ID)
                
                last_alert_check = current_time
            
            # ===== 3. ХВИЛИННІ БАРИ LEVELS.JSON =====
            if current_minute == 15 or current_minute == 45:
                if not hasattr(main, 'last_levels_minute') or main.last_levels_minute != current_minute:
                    main.last_levels_minute = current_minute
                    
                    logger.info(f"Loading bars for levels.json tokens (minute {current_minute})")
                    
                    lm._LEVELS_CACHE = {}
                    lm._LEVELS_MTIME = None
                    levels_map = load_levels()
                    
                    levels_only_symbols = set(levels_map.keys()) - set(SYMBOLS.keys())
                    
                    for s in levels_only_symbols:
                        ensure_tables(conn, s)
                        added = sync_klines(conn, s)
                        if added:
                            logger.info(f"{s}: synced {added} 1m bars (levels)")
                        
                        check_alerts(conn, s, ADMIN_CHAT_ID, cfg=cfg)
            
            # ===== 4. ГОДИННІ БАРИ VOLUME ALERTS =====
            if current_minute == 3:
                if not hasattr(main, 'last_volume_hour') or main.last_volume_hour != current_datetime.hour:
                    main.last_volume_hour = current_datetime.hour
                    
                    logger.info(f"Loading hourly bars for volume alerts (hour {current_datetime.hour})")
                    
                    if current_time - last_markets_update >= 21600:
                        binance_symbols = fetch_all_usdt_symbols()
                        last_markets_update = current_time
                        logger.info(f"Updated markets list: {len(binance_symbols)} USDT pairs")
                    
                    excluded_symbols = ["XAUUSDT", "XAGUSDT"]
                    
                    for s in binance_symbols:
                        if s in excluded_symbols:
                            continue
                        
                        cfg = SYMBOLS.get(s, {"sl_small_pct": 0.01, "sl_big_pct": 0.02})
                        
                        added_hourly = sync_hourly_klines(conn, s)
                        if added_hourly:
                            logger.info(f"{s}: synced {added_hourly} hourly bars")
                        
                        alert_data = check_volume_alert(conn, s, cfg)

                        if alert_data:
                            msg = format_volume_alert(alert_data)
                            
                            # ✅ Завантажуємо df тільки для графіка
                            df = load_hourly_bars(conn, s, limit=90)
                            
                            if df is not None:
                                chart_path = build_volume_alert_chart(df, s)
                                
                                success = send_alert_chart(
                                    chat_id=ADMIN_CHAT_ID,
                                    symbol=s,
                                    timeframe="1h",
                                    chart_path=chart_path,
                                    price=alert_data["current_price"],
                                    reason=msg
                                )
                                
                                if success:
                                    logger.info(f"Volume alert sent: {s}")
                                else:
                                    logger.error(f"Failed to send volume alert: {s}")
                        
                        time.sleep(0.5)

            # ===== 5. CLEANUP БД =====
            if current_datetime.hour == 3 and current_minute == 0:
                if not hasattr(main, 'last_cleanup_day') or main.last_cleanup_day != current_datetime.day:
                    main.last_cleanup_day = current_datetime.day
                    
                    logger.info("Starting database cleanup...")
                    try:
                        deleted = cleanup_old_data(conn, days_to_keep=30)
                        logger.info(f"Database cleanup finished: {deleted} rows deleted")
                    except Exception as e:
                        logger.error(f"Database cleanup error: {e}")
            
            # ===== 6. ALIVE PING =====
            send_alive_ping(ADMIN_CHAT_ID)
            
            time.sleep(0.1)

        except Exception:
            logger.exception("Main loop error")
            time.sleep(5)


if __name__ == "__main__":
    main()