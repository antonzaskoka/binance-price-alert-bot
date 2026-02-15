"""
Отримання списку досягнутих рівнів за період
"""
import logging
from datetime import datetime, timedelta
from database.db_manager import get_conn
from config import SYMBOLS

logger = logging.getLogger(__name__)


def get_reached_levels(hours):
    """
    Повертає список токенів які торкнулись рівнів за останні N годин
    
    Args:
        hours: кількість годин (4, 12, 24)
    
    Returns:
        str: форматоване повідомлення
    """
    conn = get_conn()
    
    # Час N годин тому
    cutoff_time = datetime.now() - timedelta(hours=hours)
    cutoff_ms = int(cutoff_time.timestamp() * 1000)
    
    try:
        # Отримуємо всі level_touch алерти за період
        cursor = conn.execute(
            """
            SELECT symbol, alert_type, last_trigger_ms
            FROM alert_state
            WHERE alert_type LIKE 'level_touch_%'
            AND last_trigger_ms >= ?
            ORDER BY last_trigger_ms DESC
            """,
            (cutoff_ms,)
        )
        
        rows = cursor.fetchall()
        
        if not rows:
            return f"⚠️ За останні {hours} год не було торкань рівнів"
        
        # Фільтруємо токени з symbols.json
        symbols_to_exclude = set(SYMBOLS.keys())
        
        results = []
        
        for symbol, alert_type, last_trigger_ms in rows:
            # Виключаємо токени з symbols.json
            if symbol in symbols_to_exclude:
                continue
            
            # Парсимо рівень з alert_type
            # Формат: level_touch_67000 або level_touch_0.03514
            level_str = alert_type.replace("level_touch_", "")
            
            try:
                level = float(level_str)
            except ValueError:
                logger.error(f"Failed to parse level from {alert_type}")
                continue
            
            # Час досягнення
            touched_time = datetime.fromtimestamp(last_trigger_ms / 1000)
            
            results.append({
                "symbol": symbol,
                "level": level,
                "time": touched_time
            })
        
        if not results:
            return (
                f"⚠️ За останні {hours} год не було торкань рівнів\n"
                f"(виключено токени з symbols.json)"
            )
        
        # Формуємо повідомлення
        msg = (
            f"🎯 <b>Досягнуті рівні за {hours} год</b>\n"
            f"Знайдено: <b>{len(results)}</b> торкань\n"
            f"{'─' * 30}\n\n"
        )
        
        for item in results:
            symbol = item["symbol"]
            level = item["level"]
            touched_time = item["time"]
            
            # Час у форматі "14:23" або "вчора 14:23"
            now = datetime.now()
            if touched_time.date() == now.date():
                time_str = touched_time.strftime("%H:%M")
            elif touched_time.date() == (now - timedelta(days=1)).date():
                time_str = "вчора " + touched_time.strftime("%H:%M")
            else:
                time_str = touched_time.strftime("%d.%m %H:%M")
            
            msg += f"<b>{symbol}</b>\n"
            msg += f"  🔵 Level: <b>{level:.6f}</b>\n"
            msg += f"  🕒 Час: {time_str}\n\n"
        
        return msg
    
    except Exception as e:
        logger.exception("Error getting reached levels")
        return f"❌ Помилка: {e}"
