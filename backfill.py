import requests
import sqlite3
import time
from datetime import datetime, timezone

# config
DB_PATH = "database.db"

# db helpers
def get_conn():
    return sqlite3.connect(DB_PATH)

def ensure_klines_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS btc_1m_klines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            open_time_ms INTEGER UNIQUE NOT NULL,
            open_time_utc TEXT NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume REAL NOT NULL,
            volume_usdt REAL NOT NULL
        );
    """)
    conn.commit()

# ==============================
# CONFIG
# ==============================
DB_PATH = "database.db"
SYMBOL = "BTCUSDT"
INTERVAL = "1m"
BINANCE_FUTURES_KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"

# Binance обмеження: max 1500 свічок за запит
MAX_LIMIT = 1500

# якщо БД пуста — беремо останні 2 години
DEFAULT_LOOKBACK_MINUTES = 120


# ==============================
# DB
# ==============================
def get_db_connection():
    return sqlite3.connect(DB_PATH)


def get_last_open_time_ms(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(open_time_ms) FROM btc_1m_klines;")
    result = cursor.fetchone()[0]
    return result


def insert_klines(conn, rows):
    sql = """
    INSERT OR IGNORE INTO btc_1m_klines (
        open_time_ms,
        open_time_utc,
        open,
        high,
        low,
        close,
        volume,
        volume_usdt
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """
    cursor = conn.cursor()
    cursor.executemany(sql, rows)
    conn.commit()


# ==============================
# BINANCE
# ==============================
def fetch_klines(start_ms, end_ms):
    params = {
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "startTime": start_ms,
        "endTime": end_ms,
        "limit": MAX_LIMIT
    }

    response = requests.get(BINANCE_FUTURES_KLINES_URL, params=params, timeout=10)
    response.raise_for_status()
    return response.json()


# ==============================
# UTILS
# ==============================
def ms_to_utc_string(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def now_ms() -> int:
    return int(time.time() * 1000)


# ==============================
# MAIN LOGIC
# ==============================
def backfill_history():
    conn = get_conn()
    ensure_klines_table(conn)

    last_ms = get_last_open_time_ms(conn)
    current_ms = now_ms()

    if last_ms is None:
        print("DB is empty. Fetching initial history...")
        start_ms = current_ms - DEFAULT_LOOKBACK_MINUTES * 60 * 1000
    else:
        start_ms = last_ms + 60_000  # наступна хвилина

    while start_ms < current_ms:
        end_ms = min(
            start_ms + MAX_LIMIT * 60 * 1000,
            current_ms
        )

        klines = fetch_klines(start_ms, end_ms)

        if not klines:
            break

        rows = []
        for k in klines:
            open_time_ms = k[0]
            open_price = float(k[1])
            high = float(k[2])
            low = float(k[3])
            close = float(k[4])
            volume = float(k[5])

            rows.append((
                open_time_ms,
                ms_to_utc_string(open_time_ms),
                open_price,
                high,
                low,
                close,
                volume,
                volume * open_price
            ))

        insert_klines(conn, rows)

        print(f"Inserted {len(rows)} rows up to {ms_to_utc_string(rows[-1][0])}")

        start_ms = rows[-1][0] + 60_000
        time.sleep(0.2)  # захист від rate limit

    conn.close()
    print("Backfill completed.")


if __name__ == "__main__":
    backfill_history()
