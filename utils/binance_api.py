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