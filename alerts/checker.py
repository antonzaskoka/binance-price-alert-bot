"""
Перевірка алертів
"""
import logging
from datetime import datetime

from config import SYMBOLS, CHECKS, LEVEL_LOOKBACK_MIN
from database.models import can_alert, load_last_bars
from alerts.alert_types import check_threshold_alert, check_level_touch_alert
from alerts.alert_formatter import format_threshold_alert, format_level_touch_alert
from charts.alert_chart import build_alert_chart
from telegram.client import send_alert_chart
from alerts.level_proximity import was_near_level  # ✅ ДОДАНО
from alerts.levels_manager import load_levels  # ✅ ДОДАНО

logger = logging.getLogger(__name__)


def check_alerts(conn, symbol, admin_chat_id):
    """Перевіряє алерти для символа"""
    
    cfg = SYMBOLS.get(symbol)
    if not cfg:
        return

    # ===== TYPE 1: THRESHOLD ALERTS =====
    for threshold_name, minutes in CHECKS:
        threshold_key = f"{threshold_name}_threshold"
        
        alert_data = check_threshold_alert(conn, symbol, cfg, minutes, threshold_key)
        
        if alert_data:
            alert_type = f"threshold_{threshold_name}"
            alert_data["minutes"] = minutes
            
            # Cooldown 15 хвилин
            if not can_alert(conn, symbol, alert_type, 15):
                logger.info(f"BLOCKED by cooldown: {symbol} {threshold_name} (15 min cooldown)")
                continue

            # ✅ ДОДАНО: Перевірка близькості до рівнів
            # Завантажуємо дані за період руху (minutes барів)
            df_period = load_last_bars(conn, symbol, minutes)
            
            if df_period is None or len(df_period) == 0:
                logger.debug(f"Skipping {symbol} {threshold_name}: no data for period check")
                continue
            
            # Рівні для токена
            levels_map = load_levels()
            symbol_levels = levels_map.get(symbol, [])
            
            # ✅ ДЕТАЛЬНЕ ЛОГУВАННЯ
            if symbol_levels:
                min_price = df_period["low"].min()
                max_price = df_period["high"].max()
                
                logger.info(
                    f"{symbol} {threshold_name} alert candidate: "
                    f"price range [{min_price:.2f} - {max_price:.2f}], "
                    f"levels: {symbol_levels}"
                )
                
                # Фільтр: алерт тільки якщо ціна була біля рівня
                if not was_near_level(df_period, symbol_levels):
                    logger.warning(
                        f"BLOCKED by proximity filter: {symbol} {threshold_name} - "
                        f"price was not near any level"
                    )
                    continue
                else:
                    logger.info(f"PASSED proximity filter: {symbol} {threshold_name}")
            else:
                # ✅ ЯКЩО НЕМАЄ РІВНІВ - ПРОПУСКАЄМО АЛЕРТ
                logger.warning(f"BLOCKED: {symbol} {threshold_name} - no levels defined in levels.json")
                continue

            # Завантажуємо df для ATR і графіка
            df = load_last_bars(conn, symbol, LEVEL_LOOKBACK_MIN)
            if df is None:
                logger.warning(f"BLOCKED: {symbol} {threshold_name} - failed to load df for chart")
                return

            # Форматуємо повідомлення (передаємо df для ATR)
            msg, valid_levels = format_threshold_alert(alert_data, df)
            if not msg:
                return

            try:
                # Будуємо графік
                logger.info(f"Building chart for {symbol} {threshold_name}...")
                chart_path = build_alert_chart(df, symbol, valid_levels)
                
                logger.info(f"Sending alert to Telegram for {symbol} {threshold_name}...")
                send_alert_chart(
                    chat_id=admin_chat_id,
                    symbol=symbol,
                    timeframe="1m",
                    chart_path=chart_path,
                    price=alert_data["open_price"],
                    reason=msg
                )
                
                # ✅ ДОДАТИ: Записуємо в БД ТІЛЬКИ ПІСЛЯ успішної відправки
                from database.models import record_alert
                record_alert(conn, symbol, alert_type)
                
                logger.info(f"✅ Threshold alert sent: {symbol} {threshold_name}")
            except Exception as e:
                logger.error(f"❌ Failed to send threshold alert for {symbol} {threshold_name}: {e}")
                logger.exception("Full traceback:")

    # ===== TYPE 2: LEVEL TOUCH ALERTS =====
    alert_data = check_level_touch_alert(conn, symbol, cfg)
    
    if alert_data:
        touched_level = alert_data["touched_level"]
        alert_type = f"level_touch_{touched_level}"
        
        # Cooldown 60 хвилин
        if not can_alert(conn, symbol, alert_type, 60):
            logger.info(f"BLOCKED by cooldown: {symbol} level {touched_level} (60 min cooldown)")
            return
        
        # Завантажуємо df для ATR і графіка
        df = load_last_bars(conn, symbol, LEVEL_LOOKBACK_MIN)
        if df is None:
            logger.warning(f"BLOCKED: {symbol} {threshold_name} - failed to load df for chart")
            return

        # Форматуємо повідомлення
        msg, valid_levels = format_threshold_alert(alert_data, df)
        if not msg:
            logger.warning(f"BLOCKED: {symbol} {threshold_name} - format_threshold_alert returned None")
            return  

        try:
            # Будуємо графік
            chart_path = build_alert_chart(df, symbol, valid_levels)
            send_alert_chart(
                chat_id=admin_chat_id,
                symbol=symbol,
                timeframe="1m",
                chart_path=chart_path,
                price=alert_data["open_price"],
                reason=msg
            )
            
            # ✅ ДОДАТИ: Записуємо в БД ТІЛЬКИ ПІСЛЯ успішної відправки
            from database.models import record_alert
            record_alert(conn, symbol, alert_type)
            
            logger.info(f"Level touch alert sent: {symbol} level {touched_level}")
        except Exception as e:
            logger.error(f"❌ Failed to send level touch alert for {symbol} level {touched_level}: {e}")
            logger.exception("Full traceback:")

        # # Завантажуємо df для ATR і графіка
        # df = load_last_bars(conn, symbol, LEVEL_LOOKBACK_MIN)
        # if df is None:
        #     return

        # # Форматуємо повідомлення (передаємо df для ATR)
        # msg, valid_levels = format_level_touch_alert(alert_data, df)
        # if not msg:
        #     logger.warning(f"BLOCKED: {symbol} {threshold_name} - format_threshold_alert returned None")
        #     return

        # # Будуємо графік
        # chart_path = build_alert_chart(df, symbol, valid_levels)
        # send_alert_chart(
        #     chat_id=admin_chat_id,
        #     symbol=symbol,
        #     timeframe="1m",
        #     chart_path=chart_path,
        #     price=alert_data["open_price"],
        #     reason=msg
        # )
        # logger.info(f"Level touch alert sent: {symbol} level {touched_level}")