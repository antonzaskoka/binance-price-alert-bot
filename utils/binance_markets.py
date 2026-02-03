"""
Завантаження списку торгових пар з Binance
"""
import requests
import logging

logger = logging.getLogger(__name__)


def fetch_all_usdt_symbols():
    """
    Завантажує ВСІ USDT торгові пари з Binance (без фільтрів)
    
    Returns:
        list: список символів, наприклад ["BTCUSDT", "ETHUSDT", ...]
    """
    try:
        # Отримуємо інформацію про всі торгові пари
        url = "https://api.binance.com/api/v3/exchangeInfo"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        symbols = []
        
        for symbol_info in data['symbols']:
            symbol = symbol_info['symbol']
            status = symbol_info['status']
            
            # Фільтруємо: тільки USDT пари та активні
            if symbol.endswith('USDT') and status == 'TRADING':
                symbols.append(symbol)
        
        logger.info(f"Fetched {len(symbols)} active USDT trading pairs from Binance")
        
        return sorted(symbols)
    
    except Exception as e:
        logger.error(f"Error fetching Binance symbols: {e}")
        return []