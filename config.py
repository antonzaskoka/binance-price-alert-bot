"""
Конфігурація бота
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ==============================
# TELEGRAM
# ==============================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TG_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
ADMIN_CHAT_ID = 1671163907

# ==============================
# PATHS
# ==============================
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")
LEVELS_FILE = os.path.join(BASE_DIR, "levels.json")
SYMBOLS_FILE = os.path.join(BASE_DIR, "symbols.json")
# Ініціалізація файлів з шаблонів якщо не існують
def init_data_files():
    """Створює levels.json та symbols.json з шаблонів якщо їх немає"""
    import shutil
    
    levels_example = os.path.join(BASE_DIR, "levels.json.example")
    symbols_example = os.path.join(BASE_DIR, "symbols.json.example")
    
    if not os.path.exists(LEVELS_FILE) and os.path.exists(levels_example):
        shutil.copy(levels_example, LEVELS_FILE)
        print(f"Created {LEVELS_FILE} from template")
    
    if not os.path.exists(SYMBOLS_FILE) and os.path.exists(symbols_example):
        shutil.copy(symbols_example, SYMBOLS_FILE)
        print(f"Created {SYMBOLS_FILE} from template")

init_data_files()

CHART_DIR = os.path.join(BASE_DIR, "charts")

os.makedirs(CHART_DIR, exist_ok=True)

# ==============================
# BINANCE
# ==============================
BINANCE_KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"

# ==============================
# TIMEFRAMES
# ==============================
SHORT_TIME = 2
MIDDLE_TIME = 20
LONG_TIME = 55

LEVEL_LOOKBACK_MIN = 90        # 1.5 години
LEVEL_RANGE_PCT = 0.0001        # ±0.01%
RISK_USDT = 1.0 

# ==============================
# SYMBOLS CONFIG (DYNAMIC LOAD)
# ==============================
import json

def load_symbols():
    """Завантажує налаштування токенів з JSON"""
    if not os.path.exists(SYMBOLS_FILE):
        # Створюємо файл за замовчуванням
        default_symbols = {
            "BTCUSDT": {
                "short_threshold": 0.25,
                "middle_threshold": 0.5,
                "long_threshold": 1.0,
                "risk_usdt": 1.0,
                "sl_small_pct": 0.001,
                "sl_big_pct": 0.002
            }
        }
        with open(SYMBOLS_FILE, "w") as f:
            json.dump(default_symbols, f, indent=2)
        return default_symbols
    
    with open(SYMBOLS_FILE, "r") as f:
        return json.load(f)

SYMBOLS = load_symbols()

CHECKS = [
    ("short", SHORT_TIME),
    ("middle", MIDDLE_TIME),
    ("long", LONG_TIME),
]

# ==============================
# HEARTBEAT
# ==============================
from datetime import timedelta
ALIVE_INTERVAL = timedelta(hours=12)

# ==============================
# BINANCE INTERVAL MAP
# ==============================
BINANCE_INTERVAL_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}

# Volume alerts
VOLUME_CHECK_INTERVAL = 3600  # Перевірка кожну годину (секунди)