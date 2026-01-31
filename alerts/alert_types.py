"""
Типи алертів та їх логіка спрацювання
"""
import logging
from datetime import datetime

from config import LEVEL_RANGE_PCT
from database.models import get_range_data, get_last_close, load_last_bars
from alerts.levels_manager import load_levels, filter_levels_for_range, find_nearest_level

logger = logging.getLogger(__name__)


def check_threshold_alert(conn, symbol, cfg, minutes, threshold_key):
    """
    Перевіряє алерт по порогу руху ціни (TYPE 1)
    
    Returns:
        dict або None - дані для алерта
    """
    low, high, cnt, first_open, last_close = get_range_data(conn, symbol, minutes)
    
    if not low or cnt < minutes:
        return None

    pct = (high - low) / low * 100
    threshold = cfg[threshold_key]
    
    if pct < threshold:
        return None

    # Завантажуємо останній бар для open_price
    df_last = load_last_bars(conn, symbol, limit=1)
    if df_last is None:
        return None
    
    open_price = df_last["open"].iloc[-1]

    # Завантажуємо рівні
    levels_map = load_levels()
    symbol_levels = levels_map.get(symbol, [])

    return {
        "type": "threshold",
        "symbol": symbol,
        "minutes": minutes,
        "threshold_name": threshold_key.replace("_threshold", "").upper(),
        "pct": pct,
        "price": last_close,
        "open_price": open_price,              # ✅ open останнього бара
        "min_price": low,
        "max_price": high,
        "first_open": first_open,
        "last_close": last_close,
        "levels": symbol_levels,
        "cfg": cfg
    }


def check_level_touch_alert(conn, symbol, cfg):
    """
    Перевіряє алерт по торканню рівня (TYPE 2)
    
    Returns:
        dict або None - дані для алерта
    """
    df = load_last_bars(conn, symbol, limit=3)
    if df is None or len(df) < 3:
        return None

    levels_map = load_levels()
    symbol_levels = levels_map.get(symbol, [])
    
    if not symbol_levels:
        return None

    last_bar = df.iloc[-1]
    prev_bar = df.iloc[-2]
    
    open_price = last_bar["open"]              # ✅ open останнього бара
    last_high = last_bar["high"]
    last_low = last_bar["low"]
    
    prev_high = prev_bar["high"]
    prev_low = prev_bar["low"]

    for level in symbol_levels:
        touch_range = level * 0.002  # ±0.2%
        level_low = level - touch_range
        level_high = level + touch_range

        current_touch = (last_low <= level_high and last_high >= level_low)
        prev_touch = (prev_low <= level_high and prev_high >= level_low)
        
        crossed_up = prev_high < level_low and last_high >= level_low
        crossed_down = prev_low > level_high and last_low <= level_high

        if current_touch or crossed_up or crossed_down:
            df_55 = load_last_bars(conn, symbol, limit=55)
            df_20 = load_last_bars(conn, symbol, limit=20)
            df_2 = load_last_bars(conn, symbol, limit=2)
            
            long_pct = calculate_range_pct(df_55, open_price) if df_55 is not None else 0
            middle_pct = calculate_range_pct(df_20, open_price) if df_20 is not None else 0
            short_pct = calculate_range_pct(df_2, open_price) if df_2 is not None else 0

            return {
                "type": "level_touch",
                "symbol": symbol,
                "price": open_price,
                "open_price": open_price,      # ✅ open останнього бара
                "touched_level": level,
                "crossed_up": crossed_up,
                "crossed_down": crossed_down,
                "long_pct": long_pct,
                "middle_pct": middle_pct,
                "short_pct": short_pct,
                "levels": symbol_levels,
                "cfg": cfg
            }

    return None


def calculate_range_pct(df, current_price):
    """
    Розраховує максимальний рух ціни у відсотках
    max{ |price - max| / max, |price - min| / min }
    """
    if df is None or len(df) == 0:
        return 0
    
    max_price = df["high"].max()
    min_price = df["low"].min()
    
    pct_from_max = abs((current_price - max_price) / max_price * 100)
    pct_from_min = abs((current_price - min_price) / min_price * 100)
    
    return max(pct_from_max, pct_from_min)
