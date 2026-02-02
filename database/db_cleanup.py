"""
Очищення бази даних від старих записів
"""
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def cleanup_old_data(conn, days_to_keep=30):
    """
    Видаляє дані старше заданої кількості днів
    
    Args:
        conn: з'єднання з БД
        days_to_keep: скільки днів зберігати (за замовчуванням 30)
    """
    cutoff_timestamp = int((datetime.now() - timedelta(days=days_to_keep)).timestamp() * 1000)
    
    # Отримуємо список всіх таблиць
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'alerts'"
    )
    
    tables = [row[0] for row in cursor.fetchall()]
    
    total_deleted = 0
    
    for table in tables:
        try:
            # Видаляємо старі записи
            cursor = conn.execute(
                f"DELETE FROM {table} WHERE open_time_ms < ?",
                (cutoff_timestamp,)
            )
            
            deleted = cursor.rowcount
            total_deleted += deleted
            
            if deleted > 0:
                logger.info(f"Cleaned {table}: deleted {deleted} rows")
        
        except Exception as e:
            logger.error(f"Error cleaning {table}: {e}")
    
    # Оптимізуємо базу
    conn.execute("VACUUM")
    conn.commit()
    
    logger.info(f"Database cleanup complete: {total_deleted} rows deleted, {len(tables)} tables processed")
    
    return total_deleted