# ==============================
# LOGGING
# ==============================
from logging_config import setup_logging
setup_logging()

import logging
logger = logging.getLogger(__name__)

# ==============================
# IMPORTS
# ==============================
import time
import sqlite3
import requests
from datetime import datetime, timezone

from telegram_client import send_telegram_message

# ==============================
# CONFIG
# ==============================
DB_PATH = "database.db"
BINANCE_KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"

SHORT_TIME = 2
MIDDLE_TIME = 20
LONG_TIME = 55

SYMBOLS = {
    "BTCUSDT": {
        "short_threshold": 0.25,
        "middle_threshold": 0.5,
        "long_threshold": 1.0,
        "risk_usdt": 1.0,
        "sl_small_pct": 0.001,
        "sl_big_pct": 0.002
    },
    "ETHUSDT": {
        "short_threshold": 0.55,
        "middle_threshold": 1.25,
        "long_threshold": 2.5,
        "risk_usdt": 1.0,
        "sl_small_pct": 0.0025,
        "sl_big_pct": 0.005
    },
    "SOLUSDT": {
        "short_threshold": 0.6,
        "middle_threshold": 1.5,
        "long_threshold": 3.0,
        "risk_usdt": 1.0,
        "sl_small_pct": 0.003,
        "sl_big_pct": 0.006
    },
    "XAUUSDT": {
        "short_threshold": 0.14,
        "middle_threshold": 0.28,
        "long_threshold": 0.55,
        "risk_usdt": 1.0,
        "sl_small_pct": 0.0007,
        "sl_big_pct": 0.0014
    },
    "XAGUSDT": {
        "short_threshold": 0.45,
        "middle_threshold": 0.9,
        "long_threshold": 1.75,
        "risk_usdt": 1.0,
        "sl_small_pct": 0.0033,
        "sl_big_pct": 0.0066
    }
}

CHECKS = [
    ("short", SHORT_TIME),
    ("middle", MIDDLE_TIME),
    ("long", LONG_TIME),
]

# ==============================
# DB
# ==============================
def get_conn():
    return sqlite3.connect(DB_PATH)


def table(symbol):
    return symbol.lower()


def ensure_tables(conn, symbol):
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {table(symbol)} (
            open_time_ms INTEGER PRIMARY KEY,
            open_time_utc TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL
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


def last_open_ms(conn, symbol):
    cur = conn.execute(f"SELECT MAX(open_time_ms) FROM {table(symbol)}")
    r = cur.fetchone()
    return r[0] if r and r[0] else None


# ==============================
# BINANCE
# ==============================
def fetch_klines(symbol, start_ms, end_ms):
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


# ==============================
# SYNC
# ==============================
def sync_klines(conn, symbol):
    now_ms = int(time.time() * 1000)
    last_ms = last_open_ms(conn, symbol)

    start_ms = last_ms + 60_000 if last_ms else now_ms - 2 * 60 * 60 * 1000
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
            f"INSERT OR IGNORE INTO {table(symbol)} VALUES (?,?,?,?,?,?)",
            (ts, utc, float(k[1]), float(k[2]), float(k[3]), float(k[4]))
        )
        rows += 1

    conn.commit()
    return rows


# ==============================
# ALERTS
# ==============================
def get_range_data(conn, symbol, minutes):
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
        FROM {table(symbol)}
        WHERE open_time_ms >= ?
        """,
        (since,)
    )
    return cur.fetchone()


def can_alert(conn, symbol, alert_type, cooldown_min):
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


def check_alerts(conn, symbol):
    cfg = SYMBOLS[symbol]

    cur = conn.execute(
        f"SELECT close FROM {table(symbol)} ORDER BY open_time_ms DESC LIMIT 1"
    )
    row = cur.fetchone()
    if not row:
        return

    price = row[0]

    for t, minutes in CHECKS:
        low, high, cnt, first_open, last_close = get_range_data(conn, symbol, minutes)
        if not low or cnt < minutes:
            continue

        pct = (high - low) / low * 100
        if pct < cfg[f"{t}_threshold"]:
            continue

        direction = "UP" if last_close > first_open else "DOWN"
        alert_type = f"{t}_{direction}"

        if not can_alert(conn, symbol, alert_type, minutes):
            continue

        sl_big = price * cfg["sl_big_pct"]
        sl_small = price * cfg["sl_small_pct"]

        if sl_big <= 0 or sl_small <= 0:
            logger.warning(f"{symbol}: invalid SL values")
            continue

        arrow = "📈" if direction == "UP" else "📉"
        side = "SHORT" if direction == "UP" else "LONG"
        arroww = "⏬" if direction == "UP" else "⏫"
        arrowww = "🔽" if direction == "UP" else "🔼"

        msg = (
            f"{arrow} <b>{symbol} MOVES {direction}</b>\n"
            f"🕒 {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"<u>{minutes}m range</u>  △={pct:.2f}%\n"
            f"Price: {price:.2f}\n\n"
            f"<b>{side} setup</b>\n"
            f"{arroww} SL SMALL: {sl_small:.4f}\n"
            f"Size: <b>{cfg['risk_usdt']/sl_small:.4f}</b>\n\n"
            f"{arrowww} SL BIG: {sl_big:.4f}\n"
            f"Size: <b>{cfg['risk_usdt']/sl_big:.4f}</b>"
        )

        send_telegram_message(msg)
        logger.warning(msg)


# ==============================
# MAIN
# ==============================
def sleep_to_next_minute():
    time.sleep(60 - time.time() % 60)


def main():
    logger.info("Bot started")

    conn = get_conn()
    for s in SYMBOLS:
        ensure_tables(conn, s)

    while True:
        try:
            for s in SYMBOLS:
                added = sync_klines(conn, s)
                if added:
                    logger.info(f"{s}: synced {added} rows")
                check_alerts(conn, s)
        
        except Exception:
            logger.exception("Main loop error")

        sleep_to_next_minute()


if __name__ == "__main__":
    main()




# # ==============================
# # LOGGING
# # ==============================
# from logging_config import setup_logging
# setup_logging()

# import logging
# logger = logging.getLogger(__name__)

# # ==============================
# # IMPORTS
# # ==============================
# import time
# import sqlite3
# import requests
# from datetime import datetime, timezone

# from telegram_client import send_telegram_message

# # ==============================
# # CONFIG
# # ==============================
# DB_PATH = "database.db"
# BINANCE_KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"

# SHORT_TIME = 2
# MIDDLE_TIME = 20
# LONG_TIME = 55

# SYMBOLS = {
#     "BTCUSDT": {
#         "short_threshold": 0.3,
#         "middle_threshold": 0.5,
#         "long_threshold": 1.0,
#         "risk_usdt": 1.0,
#         "sl_small_pct": 0.001,
#         "sl_big_pct": 0.002
#     },
#     "ETHUSDT": {
#         "short_threshold": 0.55,
#         "middle_threshold": 1.25,
#         "long_threshold": 2.5,
#         "risk_usdt": 1.0,
#         "sl_small_pct": 0.0025,
#         "sl_big_pct": 0.005
#     },
#     "SOLUSDT": {
#         "short_threshold": 0.6,
#         "middle_threshold": 1.5,
#         "long_threshold": 3.0,
#         "risk_usdt": 1.0,
#         "sl_small_pct": 0.003,
#         "sl_big_pct": 0.00
#     }
# }

# CHECKS = [


#     ("short", SHORT_TIME),
#     ("middle", MIDDLE_TIME),
#     ("long", LONG_TIME),
# ]

# # ==============================
# # DB
# # ==============================
# def get_conn():
#     return sqlite3.connect(DB_PATH)


# def table(symbol):
#     return symbol.lower()


# def ensure_tables(conn, symbol):
#     conn.execute(f"""
#         CREATE TABLE IF NOT EXISTS {table(symbol)} (
#             open_time_ms INTEGER PRIMARY KEY,
#             open_time_utc TEXT,
#             open REAL,
#             high REAL,
#             low REAL,
#             close REAL
#         )
#     """)
#     conn.execute("""
#         CREATE TABLE IF NOT EXISTS alert_state (
#             symbol TEXT,
#             alert_type TEXT,
#             last_trigger_ms INTEGER,
#             PRIMARY KEY (symbol, alert_type)
#         )
#     """)
#     conn.commit()


# def last_open_ms(conn, symbol):
#     cur = conn.execute(f"SELECT MAX(open_time_ms) FROM {table(symbol)}")
#     r = cur.fetchone()
#     return r[0] if r and r[0] else None


# # ==============================
# # BINANCE
# # ==============================
# def fetch_klines(symbol, start_ms, end_ms):
#     r = requests.get(
#         BINANCE_KLINES_URL,
#         params={
#             "symbol": symbol,
#             "interval": "1m",
#             "startTime": start_ms,
#             "endTime": end_ms,
#             "limit": 1500
#         },
#         timeout=10
#     )
#     r.raise_for_status()
#     return r.json()


# # ==============================
# # SYNC LOGIC (CORE)
# # ==============================
# def sync_klines(conn, symbol):
#     now_ms = int(time.time() * 1000)
#     last_ms = last_open_ms(conn, symbol)

#     if last_ms:
#         start_ms = last_ms + 60_000
#     else:
#         start_ms = now_ms - 2 * 60 * 60 * 1000  # 2h initial

#     if start_ms >= now_ms:
#         return 0

#     try:
#         klines = fetch_klines(symbol, start_ms, now_ms)
#     except requests.exceptions.RequestException as e:
#         logger.warning(f"{symbol} Binance unreachable: {e}")
#         return 0

#     rows = 0
#     for k in klines:
#         ts = k[0]
#         utc = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
#         conn.execute(
#             f"INSERT OR IGNORE INTO {table(symbol)} VALUES (?,?,?,?,?,?)",
#             (ts, utc, float(k[1]), float(k[2]), float(k[3]), float(k[4]))
#         )
#         rows += 1

#     conn.commit()
#     return rows


# # ==============================
# # ALERTS
# # ==============================
# def get_range(conn, symbol, minutes):
#     since = int(time.time() * 1000) - minutes * 60 * 1000
#     cur = conn.execute(
#         f"SELECT MIN(low), MAX(high), COUNT(*) FROM {table(symbol)} WHERE open_time_ms>=?",
#         (since,)
#     )
#     return cur.fetchone()


# def can_alert(conn, symbol, alert_type, cooldown):
#     now = int(time.time() * 1000)
#     cd = cooldown * 60 * 1000

#     cur = conn.execute(
#         "SELECT last_trigger_ms FROM alert_state WHERE symbol=? AND alert_type=?",
#         (symbol, alert_type)
#     )
#     r = cur.fetchone()
#     if r and now - r[0] < cd:
#         return False

#     conn.execute("""
#         INSERT INTO alert_state VALUES (?,?,?)
#         ON CONFLICT(symbol,alert_type)
#         DO UPDATE SET last_trigger_ms=excluded.last_trigger_ms
#     """, (symbol, alert_type, now))
#     conn.commit()
#     return True


# def check_alerts(conn, symbol):
#     cfg = SYMBOLS[symbol]

#     cur = conn.execute(f"SELECT close FROM {table(symbol)} ORDER BY open_time_ms DESC LIMIT 1")
#     price = cur.fetchone()
#     if not price:
#         return
#     price = price[0]

#     for t, minutes in CHECKS:
#         low, high, cnt = get_range(conn, symbol, minutes)
#         if cnt < minutes:
#             continue

#         pct = (high - low) / low * 100
#         if pct < cfg[f"{t}_threshold"]:
#             continue

#         if not can_alert(conn, symbol, t, minutes):
#             continue

#         sl_big = price * cfg["sl_big_pct"]
#         sl_small = price * cfg["sl_small_pct"]

# ### Check if SL equalls zero to avoid division on 0
#         if not sl_big or sl_big <= 0:
#             logger.warning(f"{symbol}: sl_big invalid ({sl_big}), skip alert")
#             return

#         if not sl_smal or sl_small <= 0:
#             logger.warning(f"{symbol}: sl_small invalid ({sl_small}), skip alert")
#             return

#         current_time = datetime.now().strftime("%H:%M:%S")

#         msg = (
#             f"🚨\n <b><u>{symbol}</u></b>\n 🕒 {current_time}\n\n"
#             f"<u>{minutes}m</u> Δ {pct:.2f}%\n"
#             f"Price {price:.2f}\n\n"
#             f"⏫ SL SMALL (big position): {sl_small:.4f} \n Size <b>{cfg['risk_usdt']/sl_small:.4f}</b>\n\n"
#             f"🔼 SL BIG (small position): {sl_big:.4f} \n Size <b>{cfg['risk_usdt']/sl_big:.4f}</b>\n"      
#         )

#         send_telegram_message(msg)
#         logger.warning(msg)


# # ==============================
# # MAIN LOOP
# # ==============================
# def sleep_to_next_minute():
#     time.sleep(60 - time.time() % 60)


# def main():
#     logger.info("Bot started")

#     conn = get_conn()
#     for s in SYMBOLS:
#         ensure_tables(conn, s)

#     while True:
#         try:
#             for s in SYMBOLS:
#                 added = sync_klines(conn, s)
#                 if added:
#                     logger.info(f"{s}: synced {added} rows")
#                 check_alerts(conn, s)

#         except Exception:
#             logger.exception("Main loop error")

#         sleep_to_next_minute()


# if __name__ == "__main__":
#     main()
