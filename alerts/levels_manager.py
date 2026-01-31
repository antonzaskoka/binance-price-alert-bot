"""
Менеджер рівнів (levels.json)
"""
import os
import json
import logging

from config import LEVELS_FILE

logger = logging.getLogger(__name__)

# Кеш рівнів
_LEVELS_CACHE = {}
_LEVELS_MTIME = None


def load_levels():
    """Завантажує рівні з файлу (з кешуванням)"""
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


def filter_levels_for_range(levels, ref_price, range_pct):
    """Фільтрує рівні в діапазоні ±range_pct від ціни"""
    low = ref_price * (1 - range_pct)
    high = ref_price * (1 + range_pct)
    return [lvl for lvl in levels if low <= lvl <= high]


def find_nearest_level(levels, price):
    """Знаходить найближчий рівень до ціни"""
    if not levels:
        return None
    return min(levels, key=lambda x: abs(x - price))