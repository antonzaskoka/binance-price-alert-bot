"""
Перевірка близькості ціни до рівнів
"""
import logging
from config import LEVEL_PROXIMITY_PCT

logger = logging.getLogger(__name__)


def was_near_level(df, levels):
    """
    Перевіряє чи ціна була біля якогось рівня протягом періоду df.
    
    Args:
        df: DataFrame з колонками 'high', 'low'
        levels: список рівнів
    
    Returns:
        bool: True якщо діапазон [min_price, max_price] перетинається 
              з діапазоном [level*0.999, level*1.001] хоча б для одного рівня
    """
    if not levels or len(df) == 0:
        return False
    
    # Діапазон руху ціни за період
    min_price = df["low"].min()
    max_price = df["high"].max()

    # ✅ ЛОГУВАННЯ
    logger.debug(f"Proximity check: price range [{min_price:.2f} - {max_price:.2f}]")
    
    # Перевіряємо кожен рівень
    for level in levels:
        # Діапазон рівня ±0.1%
        level_min = level * (1 - LEVEL_PROXIMITY_PCT / 100)
        level_max = level * (1 + LEVEL_PROXIMITY_PCT / 100)
        
        # Перевірка перетину діапазонів
        # Діапазони перетинаються якщо:
        # max_price >= level_min AND min_price <= level_max
        if max_price >= level_min and min_price <= level_max:
            return True
    
    logger.debug("No levels matched")
    return False