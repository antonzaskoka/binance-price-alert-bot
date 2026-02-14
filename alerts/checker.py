"""
Перевірка алертів
"""
import logging
from datetime import datetime

from config import SYMBOLS, CHECKS, LEVEL_LOOKBACK_MIN
from database.models import can_alert, record_alert, load_last_bars
from alerts.alert_types import check_threshold_alert, check_level_touch_alert
from alerts.alert_formatter import format_threshold_alert, format_level_touch_alert
from charts.alert_chart import build_alert_chart
from telegram.client import send_alert_chart
from alerts.level_proximity import was_near_level
from alerts.levels_manager import load_levels

logger = logging.getLogger(__name__)


def check_alerts(conn, symbol, admin_chat_id, cfg=None):
    """
    Перевіряє алерти для символа
    
    Args:
        conn: з'єднання з БД
        symbol: символ токена
        admin_chat_id: chat_id для алертів
        cfg: конфігурація токена (якщо None - береться з SYMBOLS)
    """
    
    # ✅ ВИПРАВЛЕНО: cfg може бути переданий ззовні
    if cfg is None:
        cfg = SYMBOLS.get(symbol)
    
    if not cfg:
        return

    # ✅ ВИПРАВЛЕНО: threshold alerts тільки для токенів з symbols.json
    # Перевіряємо чи є threshold конфігурація
    has_thresholds = all(
        f"{name}_threshold" in cfg 
        for name, _ in CHECKS
    )

    # ===== TYPE 1: THRESHOLD ALERTS (тільки для symbols.json) =====
    if has_thresholds:
        for threshold_name, minutes in CHECKS:
            threshold_key = f"{threshold_name}_threshold"
            
            alert_data = check_threshold_alert(conn, symbol, cfg, minutes, threshold_key)
        
        if alert_data:
            alert_type = f"threshold_{threshold_name}"
            
            # ✅ Cooldown 30 хвилин для threshold
            if not can_alert(conn, symbol, alert_type, 30):
                logger.info(f"BLOCKED by cooldown: {symbol} {threshold_name} (15 min)")
                continue

            # ✅ Перевірка близькості до рівнів
            df_period = load_last_bars(conn, symbol, minutes)
            
            if df_period is None or len(df_period) == 0:
                logger.debug(f"BLOCKED: {symbol} {threshold_name} - no data")
                continue
            
            # Рівні для токена
            levels_map = load_levels()
            symbol_levels = levels_map.get(symbol, [])
            
            # Фільтр: алерт тільки якщо ціна була біля рівня
            if symbol_levels:
                min_price = df_period["low"].min()
                max_price = df_period["high"].max()
                
                logger.info(
                    f"{symbol} {threshold_name} alert candidate: "
                    f"price range [{min_price:.2f} - {max_price:.2f}], "
                    f"levels: {symbol_levels}"
                )
                
                if not was_near_level(df_period, symbol_levels):
                    logger.warning(f"BLOCKED by proximity: {symbol} {threshold_name}")
                    continue
                else:
                    logger.info(f"PASSED proximity filter: {symbol} {threshold_name}")
            else:
                logger.warning(f"BLOCKED: {symbol} {threshold_name} - no levels")
                continue

            # Завантажуємо df для ATR і графіка
            df = load_last_bars(conn, symbol, LEVEL_LOOKBACK_MIN)
            if df is None:
                logger.warning(f"BLOCKED: {symbol} {threshold_name} - no df")
                continue

            # Форматуємо повідомлення
            msg, valid_levels = format_threshold_alert(alert_data, df)
            if not msg:
                logger.warning(f"BLOCKED: {symbol} {threshold_name} - no msg")
                continue

            try:
                logger.info(f"Building chart for {symbol} {threshold_name}...")
                chart_path = build_alert_chart(df, symbol, valid_levels)
                
                # logger.info(f"Sending alert to Telegram for {symbol} {threshold_name}...")
                
                # ✅ Відправляємо і перевіряємо результат
                success = send_alert_chart(
                    chat_id=admin_chat_id,
                    symbol=symbol,
                    timeframe="1m",
                    chart_path=chart_path,
                    price=alert_data["open_price"],
                    reason=msg
                )
                
                # ✅ Записуємо в БД ТІЛЬКИ якщо Telegram повернув успіх
                if success:
                    record_alert(conn, symbol, alert_type)
                    # logger.info(f"✅ Threshold alert sent: {symbol} {threshold_name}")
                else:
                    logger.error(f"❌ Telegram rejected alert for {symbol} {threshold_name}")
            
            except Exception as e:
                logger.error(f"❌ Failed to send threshold alert {symbol} {threshold_name}: {e}")
                logger.exception("Full traceback:")

    # ===== TYPE 2: LEVEL TOUCH ALERTS =====
    alert_data = check_level_touch_alert(conn, symbol, cfg)
    
    if alert_data:
        touched_level = alert_data["touched_level"]
        alert_type = f"level_touch_{touched_level}"
        
        # ✅ Cooldown 60 хвилин для level touch
        if not can_alert(conn, symbol, alert_type, 60):
            logger.info(f"BLOCKED by cooldown: {symbol} level {touched_level} (60 min)")
            return

        # Завантажуємо df для ATR і графіка
        df = load_last_bars(conn, symbol, LEVEL_LOOKBACK_MIN)
        if df is None:
            logger.warning(f"BLOCKED: {symbol} level {touched_level} - no df")
            return

        # Форматуємо повідомлення
        msg, valid_levels = format_level_touch_alert(alert_data, df)
        if not msg:
            logger.warning(f"BLOCKED: {symbol} level {touched_level} - no msg")
            return

        # ✅ Відправка з try-except
        try:
            logger.info(f"Building chart for {symbol} level {touched_level}...")
            chart_path = build_alert_chart(df, symbol, valid_levels)
            
            # logger.info(f"Sending level touch alert to Telegram...")
            
            # ✅ Відправляємо і перевіряємо результат
            success = send_alert_chart(
                chat_id=admin_chat_id,
                symbol=symbol,
                timeframe="1m",
                chart_path=chart_path,
                price=alert_data["open_price"],
                reason=msg
            )
            
            # ✅ Записуємо в БД ТІЛЬКИ якщо успіх
            if success:
                record_alert(conn, symbol, alert_type)
                # logger.info(f"✅ Level touch alert sent: {symbol} level {touched_level}")
            else:
                logger.error(f"❌ Telegram rejected level touch for {symbol} level {touched_level}")
        
        except Exception as e:
            logger.error(f"❌ Failed to send level touch alert {symbol} {touched_level}: {e}")
            logger.exception("Full traceback:")