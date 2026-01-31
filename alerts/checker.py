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
            
            # Cooldown 30 хвилин
            if not can_alert(conn, symbol, alert_type, 30):
                continue

            # Завантажуємо df для ATR і графіка
            df = load_last_bars(conn, symbol, LEVEL_LOOKBACK_MIN)
            if df is None:
                continue

            # Форматуємо повідомлення (передаємо df для ATR)
            msg, valid_levels = format_threshold_alert(alert_data, df)
            if not msg:
                continue

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
            logger.info(f"Threshold alert sent: {symbol} {threshold_name}")

    # ===== TYPE 2: LEVEL TOUCH ALERTS =====
    alert_data = check_level_touch_alert(conn, symbol, cfg)
    
    if alert_data:
        touched_level = alert_data["touched_level"]
        alert_type = f"level_touch_{touched_level}"
        
        # Cooldown 60 хвилин
        if not can_alert(conn, symbol, alert_type, 60):
            return

        # Завантажуємо df для ATR і графіка
        df = load_last_bars(conn, symbol, LEVEL_LOOKBACK_MIN)
        if df is None:
            return

        # Форматуємо повідомлення (передаємо df для ATR)
        msg, valid_levels = format_level_touch_alert(alert_data, df)
        if not msg:
            return

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
        logger.info(f"Level touch alert sent: {symbol} level {touched_level}")
