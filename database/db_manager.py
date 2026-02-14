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
