"""
SQL-запити та моделі даних
"""
import pandas as pd
import logging
from datetime import datetime

from database.db_manager import table_name

logger = logging.getLogger(__name__)


def load_last_bars(conn, symbol, limit=90):
    """Завантажує останні N барів з БД"""
    cur = conn.execute(
        f"""
        SELECT open_time_utc, open, high, low, close, volume
        FROM {table_name(symbol)}
        ORDER BY open_time_ms DESC
        LIMIT ?
        """,
        (limit,)
    )

    rows = cur.fetchall()
    if len(rows) < limit:
        return None

    df = pd.DataFrame(
        rows[::-1],
        columns=["time", "open", "high", "low", "close", "volume"]
    )
    return df


def get_range_data(conn, symbol, minutes):
    """Повертає дані про діапазон ціни за останні N хвилин"""
    import time
    
    since = int(time.time() * 1000) - minutes * 60 * 1000
    cur = conn.execute(
        f"""
        SELECT 
            MIN(low),
            MAX(high),
            COUNT(*),
            FIRST_VALUE(open) OVER (ORDER BY open_time_ms),
            LAST_VALUE(close) OVER (
                ORDER BY open_time_ms
                ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
            )
        FROM {table_name(symbol)}
        WHERE open_time_ms >= ?
        """,
        (since,)
    )
    return cur.fetchone()


def get_last_close(conn, symbol):
    """Повертає останню ціну закриття"""
    cur = conn.execute(
        f"SELECT close FROM {table_name(symbol)} ORDER BY open_time_ms DESC LIMIT 1"
    )
    row = cur.fetchone()
    return row[0] if row else None


def can_alert(conn, symbol, alert_type, cooldown_min):
    """
    Перевіряє чи можна надіслати алерт (тільки перевірка, НЕ записує)
    
    Returns:
        bool: True якщо cooldown минув
    """
    import time
    
    now = int(time.time() * 1000)
    cooldown_ms = cooldown_min * 60 * 1000

    cur = conn.execute(
        "SELECT last_trigger_ms FROM alert_state WHERE symbol=? AND alert_type=?",
        (symbol, alert_type)
    )
    r = cur.fetchone()
    
    if r and now - r[0] < cooldown_ms:
        return False
    
    return True


def record_alert(conn, symbol, alert_type):
    """
    Записує алерт в БД (викликається ПІСЛЯ успішної відправки)
    """
    import time
    
    now = int(time.time() * 1000)
    
    conn.execute("""
        INSERT INTO alert_state VALUES (?,?,?)
        ON CONFLICT(symbol,alert_type)
        DO UPDATE SET last_trigger_ms=excluded.last_trigger_ms
    """, (symbol, alert_type, now))
    conn.commit()

def record_alert(conn, symbol, alert_type):
    """
    Записує алерт в БД (викликається ПІСЛЯ успішної відправки)
    """
    import time
    
    now = int(time.time() * 1000)
    
    conn.execute("""
        INSERT INTO alert_state VALUES (?,?,?)
        ON CONFLICT(symbol,alert_type)
        DO UPDATE SET last_trigger_ms=excluded.last_trigger_ms
    """, (symbol, alert_type, now))
    conn.commit()
