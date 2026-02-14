"""
Запити до Binance API
"""
import requests
import pandas as pd
import logging

from config import BINANCE_KLINES_URL, BINANCE_INTERVAL_MAP

logger = logging.getLogger(__name__)


def fetch_last_bars(symbol, timeframe, limit=90):
    """Завантажує останні N барів з Binance"""
    interval = BINANCE_INTERVAL_MAP.get(timeframe)
    if not interval:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    r = requests.get(
        BINANCE_KLINES_URL,
        params={
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        },
        timeout=10
    )
    r.raise_for_status()

    data = r.json()

    df = pd.DataFrame(
        data,
        columns=[
            "open_time",
            "open", "high", "low", "close",
            "volume",
            "_", "_", "_", "_", "_", "_"
        ]
    )

    df = df[["open_time", "open", "high", "low", "close", "volume"]]
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    df[["open", "high", "low", "close", "volume"]] = df[
        ["open", "high", "low", "close", "volume"]
    ].astype(float)

    return df

def fetch_klines(symbol, interval, start_time, end_time, limit=1000):
    """
    Завантажує klines (свічки) з Binance
    
    Args:
        symbol: наприклад "BTCUSDT"
        interval: "1m", "1h", "1d" тощо
        start_time: timestamp в мілісекундах
        end_time: timestamp в мілісекундах
        limit: максимальна кількість барів (до 1000)
    
    Returns:
        list of lists: [[timestamp, open, high, low, close, volume, ...], ...]
    """
    url = "https://api.binance.com/api/v3/klines"
    
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": start_time,
        "endTime": end_time,
        "limit": limit
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching klines for {symbol}: {e}")
        return []

def fetch_futures_klines(symbol, interval, start_time, end_time, limit=500):
    """
    Завантажує klines з Binance Futures API
    """
    from config import BINANCE_KLINES_URL
    
    try:
        r = requests.get(
            BINANCE_KLINES_URL,
            params={
                "symbol": symbol,
                "interval": interval,
                "startTime": start_time,
                "endTime": end_time,
                "limit": limit
            },
            timeout=10
        )
        r.raise_for_status()
        return r.json()
    except requests.exceptions.HTTPError as e:
        # Тихо повертаємо [] для 400 (токен не існує)
        if e.response.status_code == 400:
            return []
        logger.error(f"Futures API error for {symbol}: {e}")
        return []
    except Exception as e:
        logger.error(f"Error fetching Futures klines for {symbol}: {e}")
        return []