"""
Менеджер бази даних SQLite
"""
import sqlite3
import requests
import logging
import pandas as pd
from datetime import datetime, timezone

from config import DB_PATH, BINANCE_KLINES_URL

logger = logging.getLogger(__name__)


def get_conn():
    """Повертає з'єднання з БД"""
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def table_name(symbol):
    """Повертає назву таблиці для символа"""
    name = symbol.lower()
    return f'"{name}"'


def ensure_tables(conn, symbol):
    """Створює таблиці для символа, якщо їх немає"""
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {table_name(symbol)} (
            open_time_ms INTEGER PRIMARY KEY,
            open_time_utc TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alert_state (
            symbol TEXT,
            alert_type TEXT,
            last_trigger_ms INTEGER,
            PRIMARY KEY (symbol, alert_type)
        )
    """)
    conn.commit()


def ensure_alerts_table(conn):
    """
    Створює таблицю для відстеження алертів (cooldown)
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            triggered_at_utc TEXT NOT NULL
        )
    """)
    
    # Індекс для швидкого пошуку
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_alerts_symbol_type 
        ON alerts(symbol, alert_type)
    """)
    
    conn.commit()


def last_open_ms(conn, symbol):
    """Повертає останній timestamp у БД для символа"""
    cur = conn.execute(f"SELECT MAX(open_time_ms) FROM {table_name(symbol)}")
    r = cur.fetchone()
    return r[0] if r and r[0] else None


def fetch_klines(symbol, start_ms, end_ms):
    """Завантажує klines з Binance"""
    r = requests.get(
        BINANCE_KLINES_URL,
        params={
            "symbol": symbol,
            "interval": "1m",
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": 1500
        },
        timeout=10
    )
    r.raise_for_status()
    return r.json()


def sync_klines(conn, symbol):
    """Синхронізує дані з Binance"""
    import time
    
    now_ms = int(time.time() * 1000)
    last_ms = last_open_ms(conn, symbol)

    start_ms = last_ms + 60_000 if last_ms else now_ms - 3 * 60 * 60 * 1000
    if start_ms >= now_ms:
        return 0

    try:
        klines = fetch_klines(symbol, start_ms, now_ms)
    except requests.exceptions.RequestException as e:
        logger.warning(f"{symbol} Binance unreachable: {e}")
        return 0

    rows = 0
    for k in klines:
        ts = k[0]
        utc = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            f"INSERT OR IGNORE INTO {table_name(symbol)} VALUES (?,?,?,?,?,?,?)",
            (ts, utc, float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5]))
        )
        rows += 1

    conn.commit()
    return rows


def sync_hourly_klines(conn, symbol):
    """
    Синхронізує годинні бари (1h) для volume alerts
    Завантажує останні 720 годин (~30 днів)
    """
    table = f"kline_{symbol.lower()}_1h"
    
    # ✅ Створюємо таблицю з новими колонками
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {table} (
            open_time_ms INTEGER PRIMARY KEY,
            open_time_utc TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            volume_usdt REAL,
            volume_24h REAL,
            volume_avg_14d REAL,
            ratio REAL
        )
    """)
    
    # ✅ МІГРАЦІЯ: додаємо нові колонки якщо їх немає
    cursor = conn.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'volume_usdt' not in columns:
        logger.info(f"Adding volume_usdt column to {table}")
        conn.execute(f"ALTER TABLE {table} ADD COLUMN volume_usdt REAL")
    
    if 'volume_24h' not in columns:
        logger.info(f"Adding volume_24h column to {table}")
        conn.execute(f"ALTER TABLE {table} ADD COLUMN volume_24h REAL")
    
    if 'volume_avg_14d' not in columns:
        logger.info(f"Adding volume_avg_14d column to {table}")
        conn.execute(f"ALTER TABLE {table} ADD COLUMN volume_avg_14d REAL")
    
    if 'ratio' not in columns:
        logger.info(f"Adding ratio column to {table}")
        conn.execute(f"ALTER TABLE {table} ADD COLUMN ratio REAL")
    
    conn.commit()
    
    # Знаходимо останній запис
    cur = conn.execute(f"SELECT MAX(open_time_ms) FROM {table}")
    last_ms = cur.fetchone()[0]
    
    if last_ms:
        start_time = last_ms + 3600000  # +1 година
    else:
        # Перше завантаження: 720 годин назад
        start_time = int((datetime.now().timestamp() - 720 * 3600) * 1000)
    
    end_time = int(datetime.now().timestamp() * 1000)
    
    # Завантажуємо з Binance
    from utils.binance_api import fetch_klines as fetch_klines_util
    
    klines = fetch_klines_util(
        symbol=symbol,
        interval="1h",
        start_time=start_time,
        end_time=end_time,
        limit=1000
    )
    
    if not klines:
        return 0
    
    # Записуємо з розрахунком volume_usdt
    added = 0
    for k in klines:
        open_time_ms = k[0]
        open_time_utc = datetime.fromtimestamp(open_time_ms / 1000).isoformat()
        open_price = float(k[1])
        high = float(k[2])
        low = float(k[3])
        close = float(k[4])
        volume = float(k[5])
        
        # ✅ Розраховуємо volume_usdt
        volume_usdt = open_price * volume
        
        conn.execute(
            f"""
            INSERT OR IGNORE INTO {table}
            (open_time_ms, open_time_utc, open, high, low, close, volume, volume_usdt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (open_time_ms, open_time_utc, open_price, high, low, close, volume, volume_usdt)
        )
        added += 1
    
    conn.commit()
    
    # ✅ Розраховуємо volume_24h, volume_avg_14d, ratio
    if added > 0:
        calculate_and_store_volume_metrics(conn, symbol)
    
    return added


def calculate_and_store_volume_metrics(conn, symbol):
    """
    Розраховує і зберігає volume_24h, volume_avg_14d, ratio для кожного бару
    """
    table = f"kline_{symbol.lower()}_1h"
    
    # Завантажуємо всі дані
    cursor = conn.execute(f"""
        SELECT open_time_ms, volume_usdt 
        FROM {table} 
        ORDER BY open_time_ms ASC
    """)
    
    rows = cursor.fetchall()
    
    if len(rows) < 24:
        return
    
    df = pd.DataFrame(rows, columns=["open_time_ms", "volume_usdt"])
    
    # Розраховуємо volume_24h для кожного рядка (rolling sum)
    df["volume_24h"] = df["volume_usdt"].rolling(window=24, min_periods=1).sum()
    
    # Розраховуємо volume_avg_14d для кожного рядка
    volumes_14d = []
    
    for idx in range(len(df)):
        day_volumes = []
        
        for day in range(14):
            day_idx = idx - (day * 24)
            
            if day_idx < 0:
                break
            
            if day_idx >= 24:
                # Беремо суму за 24 години для цього дня
                start_idx = day_idx - 23
                day_volume = df["volume_usdt"].iloc[start_idx:day_idx+1].sum()
                day_volumes.append(day_volume)
        
        if day_volumes:
            volumes_14d.append(sum(day_volumes) / len(day_volumes))
        else:
            volumes_14d.append(None)
    
    df["volume_avg_14d"] = volumes_14d
    
    # Розраховуємо ratio
    df["ratio"] = df.apply(
        lambda row: row["volume_24h"] / row["volume_avg_14d"] if row["volume_avg_14d"] and row["volume_avg_14d"] > 0 else None,
        axis=1
    )
    
    # Зберігаємо в БД
    for _, row in df.iterrows():
        conn.execute(f"""
            UPDATE {table}
            SET volume_24h = ?, volume_avg_14d = ?, ratio = ?
            WHERE open_time_ms = ?
        """, (row["volume_24h"], row["volume_avg_14d"], row["ratio"], row["open_time_ms"]))
    
    conn.commit()
    
    logger.info(f"{symbol}: calculated volume metrics for {len(df)} bars")