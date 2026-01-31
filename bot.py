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
from datetime import datetime, timezone, timedelta
import os
import json
import pandas as pd
import matplotlib.pyplot as plt
import tempfile                                 #temporary for PC only
from telegram_client import send_telegram_photo

from telegram_client import send_telegram_message

# ==============================
# CONFIG
# ==============================
DB_PATH = "database.db"
LEVELS_FILE = "levels.json"
BINANCE_KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"

SHORT_TIME = 2
MIDDLE_TIME = 20
LONG_TIME = 55

LEVEL_LOOKBACK_MIN = 90        # 1.5 години
LEVEL_RANGE_PCT = 0.003        # ±0.3%

#Dir for images
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHART_DIR = os.path.join(BASE_DIR, "charts")
os.makedirs(CHART_DIR, exist_ok=True)

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
# ALIVE HEARTBEAT
# ==============================
LAST_ALIVE_PING = None
ALIVE_INTERVAL = timedelta(hours=12)

# ==============================
# LEVELS AUTO-RELOAD
# ==============================
_LEVELS_CACHE = {}
_LEVELS_MTIME = None
# ==============================
# LEVELS
# ==============================

def load_levels():
    global _LEVELS_CACHE, _LEVELS_MTIME

    if not os.path.exists(LEVELS_FILE):
        return {}

    mtime = os.path.getmtime(LEVELS_FILE)
    if _LEVELS_MTIME != mtime:
        with open(LEVELS_FILE, "r") as f:
            _LEVELS_CACHE = json.load(f)
        _LEVELS_MTIME = mtime
        logger.info("Levels reloaded")

    return _LEVELS_CACHE

def filter_levels_for_range(levels, ref_price):
    low = ref_price * (1 - LEVEL_RANGE_PCT)
    high = ref_price * (1 + LEVEL_RANGE_PCT)
    return [lvl for lvl in levels if low <= lvl <= high]

def find_nearest_level(levels, price):
    if not levels:
        return None
    return min(levels, key=lambda x: abs(x - price))


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
            f"INSERT OR IGNORE INTO {table(symbol)} VALUES (?,?,?,?,?,?,?)",
            (ts, utc, float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5]))
        )
        rows += 1

    conn.commit()
    return rows


# ==============================
# ALERTS
# ==============================
def load_last_bars(conn, symbol, limit=90):
    cur = conn.execute(
        f"""
        SELECT open_time_utc, open, high, low, close, volume
        FROM {table(symbol)}
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

def build_chart(df, symbol, levels=None):
    fig = plt.figure(figsize=(10, 6))
    levels = levels or []

    gs = fig.add_gridspec(2, 1, height_ratios=[3, 1], hspace=0)
    ax_price = fig.add_subplot(gs[0])
    ax_vol = fig.add_subplot(gs[1], sharex=ax_price)

    # Свічки
    for i, row in df.iterrows():
        color = "green" if row["close"] >= row["open"] else "red"
        ax_price.plot([i, i], [row["low"], row["high"]], color=color)
        ax_price.bar(
            i,
            abs(row["close"] - row["open"]),
            bottom=min(row["open"], row["close"]),
            color=color,
            width=0.6
        )

    for lvl in levels:
        ax_price.axhline(lvl, color="blue", linestyle="--", linewidth=1)

    ax_price.set_ylabel("Price")
    ax_price.grid(True)
    ax_price.set_xticks([])

    # Фейковий обʼєм (пропорційний тілу свічки)
    ax_vol.bar(range(len(df)), df["volume"], color="gray")
    ax_vol.set_ylabel("volume")

    file_path = os.path.join(CHART_DIR, f"{symbol}_chart.png")

    plt.savefig(file_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    return file_path

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

    levels_map = load_levels()
    symbol_levels = levels_map.get(symbol, [])

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

        df = load_last_bars(conn, symbol, LEVEL_LOOKBACK_MIN)
        if df is None:
            continue
        ref_price = df["close"].iloc[0]

        valid_levels = filter_levels_for_range(symbol_levels, ref_price)
        nearest = find_nearest_level(valid_levels, price)

        min_price = df.low.min()
        max_price = df.high.max()

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
            f"MIN_PRICE: {min_price:.2f}\n"
            f"MAX_PRICE: {max_price:.2f}\n"
            f"<b>{side} setup</b>\n"
            f"{arroww} SL SMALL: {sl_small:.4f}\n"
            f"Size: <b>{cfg['risk_usdt']/sl_small:.4f}</b>\n\n"
            f"{arrowww} SL BIG: {sl_big:.4f}\n"
            f"Size: <b>{cfg['risk_usdt']/sl_big:.4f}</b>"
        )
        if nearest:
            diff_abs = nearest - price
            diff_pct = diff_abs / price * 100
            msg += (
                f"\n\n 🔵 Nearest level: {nearest:.2f}\n"
                f"Δ: {diff_abs:.2f} ({diff_pct:.2f}%)"
            )

        df = load_last_bars(conn, symbol, 90)

        if df is not None:
            chart_path = build_chart(df, symbol, valid_levels)
            send_telegram_photo(chart_path, msg)
        else:
            send_telegram_message(msg)

        logger.warning(msg)

# ==============================
# MAIN
# ==============================
def send_alive_ping():
    global LAST_ALIVE_PING

    now = datetime.now(timezone.utc)

    if LAST_ALIVE_PING and now - LAST_ALIVE_PING < ALIVE_INTERVAL:
        return

    msg = (
        "✅ <b>Bot is alive</b>\n"
        f"🕒 UTC time: {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"📡 Monitoring: {', '.join(SYMBOLS.keys())}"
    )

    send_telegram_message(msg)
    logger.info("Alive ping sent")

    LAST_ALIVE_PING = now

def sleep_to_next_minute():
    time.sleep(60 - time.time() % 60)


def main():
    logger.info("Bot started")

    conn = get_conn()
    for s in SYMBOLS:
        ensure_tables(conn, s)

    while True:
        try:
            send_alive_ping()
            
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

