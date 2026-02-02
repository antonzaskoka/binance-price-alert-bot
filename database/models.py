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
    """Перевіряє, чи можна відправити алерт (cooldown)"""
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

    conn.execute("""
        INSERT INTO alert_state VALUES (?,?,?)
        ON CONFLICT(symbol,alert_type)
        DO UPDATE SET last_trigger_ms=excluded.last_trigger_ms
    """, (symbol, alert_type, now))
    conn.commit()
    return True

def load_hourly_bars(conn, symbol, limit=400):
    """
    Завантажує останні N годинних барів
    
    Returns:
        DataFrame або None
    """
    table = f"{symbol.lower()}_1h"
    
    try:
        cur = conn.execute(
            f"""
            SELECT open_time_utc, open, high, low, close, volume
            FROM {table}
            ORDER BY open_time_ms DESC
            LIMIT ?
            """,
            (limit,)
        )
        
        rows = cur.fetchall()
        
        if not rows:
            return None
        
        df = pd.DataFrame(
            rows,
            columns=["open_time", "open", "high", "low", "close", "volume"]
        )
        
        df = df.iloc[::-1].reset_index(drop=True)
        df["open_time"] = pd.to_datetime(df["open_time"])
        
        return df
        
    except Exception as e:
        logger.error(f"Error loading hourly bars for {symbol}: {e}")
        return None


def can_alert_volume(conn, symbol, cooldown_hours):
    """
    Перевіряє чи можна надіслати volume alert (cooldown)
    
    Returns:
        bool
    """
    alert_type = "volume_breakout"
    
    cur = conn.execute(
        """
        SELECT triggered_at_utc
        FROM alerts
        WHERE symbol = ? AND alert_type = ?
        ORDER BY triggered_at_utc DESC
        LIMIT 1
        """,
        (symbol, alert_type)
    )
    
    row = cur.fetchone()
    
    if not row:
        # Перший алерт
        conn.execute(
            """
            INSERT INTO alerts (symbol, alert_type, triggered_at_utc)
            VALUES (?, ?, datetime('now'))
            """,
            (symbol, alert_type)
        )
        conn.commit()
        return True
    
    last_alert = datetime.fromisoformat(row[0])
    now = datetime.utcnow()
    
    if (now - last_alert).total_seconds() / 3600 >= cooldown_hours:
        conn.execute(
            """
            INSERT INTO alerts (symbol, alert_type, triggered_at_utc)
            VALUES (?, ?, datetime('now'))
            """,
            (symbol, alert_type)
        )
        conn.commit()
        return True
    
    return False