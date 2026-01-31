"""
Менеджер налаштувань токенів (symbols.json)
"""
import os
import json
import logging

from config import SYMBOLS_FILE

logger = logging.getLogger(__name__)


def normalize_symbol(symbol):
    """Нормалізує назву токена (додає USDT)"""
    symbol = symbol.upper().strip()
    if not symbol.endswith("USDT"):
        symbol += "USDT"
    return symbol


def load_symbols():
    """Завантажує налаштування токенів"""
    if not os.path.exists(SYMBOLS_FILE):
        return {}
    
    with open(SYMBOLS_FILE, "r") as f:
        return json.load(f)


def save_symbols(data):
    """Зберігає налаштування токенів"""
    with open(SYMBOLS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def add_symbol(symbol, params):
    """Додає новий токен"""
    symbol = normalize_symbol(symbol)
    data = load_symbols()
    data[symbol] = params
    save_symbols(data)
    logger.info(f"Symbol {symbol} added")


def update_symbol(symbol, params):
    """Оновлює параметри токена"""
    symbol = normalize_symbol(symbol)
    data = load_symbols()
    if symbol in data:
        data[symbol] = params
        save_symbols(data)
        logger.info(f"Symbol {symbol} updated")
        return True
    return False


def delete_symbol(symbol):
    """Видаляє токен"""
    symbol = normalize_symbol(symbol)
    data = load_symbols()
    if symbol in data:
        del data[symbol]
        save_symbols(data)
        logger.info(f"Symbol {symbol} deleted")
        return True
    return False


def get_symbol_params(symbol):
    """Отримує параметри токена"""
    symbol = normalize_symbol(symbol)
    data = load_symbols()
    return data.get(symbol)