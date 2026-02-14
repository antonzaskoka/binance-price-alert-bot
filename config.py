"""
Конфігурація бота
"""
import os
import shutil
import logging
from dotenv import load_dotenv

load_dotenv()

# Налаштування логування
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)

# ==============================
# TELEGRAM
# ==============================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TG_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
ADMIN_CHAT_ID = 1671163907

# ==============================
# PATHS
# ==============================
# ✅ Папка для даних (персистентна в Railway Volume)
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
# Створюємо папку якщо не існує
os.makedirs(DATA_DIR, exist_ok=True)
# Файли даних у Volume
LEVELS_FILE = os.path.join(DATA_DIR, "levels.json")
SYMBOLS_FILE = os.path.join(DATA_DIR, "symbols.json")
DB_PATH = os.path.join(DATA_DIR, "binance_bot.db")

# Ініціалізація файлів з шаблонів якщо не існують
def init_data_files():
    """Створює levels.json та symbols.json з templates якщо не існують"""
    # ✅ Template файли в корені проекту
    levels_example = "/app/levels.json.example"
    symbols_example = "/app/symbols.json.example"
    
    # ✅ Реальні файли у Volume /app/data
    if not os.path.exists(LEVELS_FILE) and os.path.exists(levels_example):
        shutil.copy(levels_example, LEVELS_FILE)
        logger.info(f"Created {LEVELS_FILE} from template")
    
    if not os.path.exists(SYMBOLS_FILE) and os.path.exists(symbols_example):
        shutil.copy(symbols_example, SYMBOLS_FILE)
        logger.info(f"Created {SYMBOLS_FILE} from template")
init_data_files()

CHART_DIR = os.path.join(DATA_DIR, "charts_output")
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

# ===== ФІЛЬТР АЛЕРТІВ: БЛИЗЬКІСТЬ ДО РІВНІВ =====
# Алерт надсилається тільки якщо ціна була біля рівня ±LEVEL_PROXIMITY_PCT%
LEVEL_PROXIMITY_PCT = 0.3  # 0.3% = діапазон ±0.3% від рівня