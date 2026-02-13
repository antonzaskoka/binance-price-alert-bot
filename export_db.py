"""
Експорт hourly даних з БД в CSV
"""
import sqlite3
import csv
import sys

# Шлях до БД (скачаної з Railway або локальної)
DB_PATH = "binance_bot.db"

def export_table_to_csv(symbol):
    """Експортує таблицю токена в CSV"""
    conn = sqlite3.connect(DB_PATH)
    table = f"kline_{symbol.lower()}_1h"
    
    try:
        cursor = conn.execute(f"""
            SELECT open_time_utc, open, high, low, close, volume, 
                   volume_usdt, volume_24h, volume_avg_14d, ratio
            FROM {table}
            ORDER BY open_time_ms ASC
        """)
        
        rows = cursor.fetchall()
        
        if not rows:
            print(f"⚠️ Немає даних для {symbol}")
            return
        
        # Записуємо CSV
        filename = f"{symbol}_hourly_data.csv"
        
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Заголовки
            writer.writerow([
                "timestamp", "open", "high", "low", "close", "volume",
                "volume_usdt", "volume_24h", "volume_avg_14d", "ratio"
            ])
            
            # Дані
            writer.writerows(rows)
        
        print(f"✅ Експортовано {len(rows)} барів в {filename}")
        
    except Exception as e:
        print(f"❌ Помилка: {e}")
    
    finally:
        conn.close()


def list_tables():
    """Показує всі hourly таблиці"""
    conn = sqlite3.connect(DB_PATH)
    
    cursor = conn.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' 
        AND name LIKE 'kline_%_1h'
        ORDER BY name
    """)
    
    tables = [row[0] for row in cursor.fetchall()]
    
    print(f"📊 Знайдено {len(tables)} таблиць:\n")
    
    for table in tables[:20]:  # Перші 20
        symbol = table.replace("kline_", "").replace("_1h", "").upper()
        
        # Кількість барів
        cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        
        print(f"• {symbol}: {count} bars")
    
    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("📊 Використання:")
        print("  python export_db.py list              # Показати всі таблиці")
        print("  python export_db.py BTC               # Експортувати BTCUSDT")
        print("  python export_db.py ETH               # Експортувати ETHUSDT")
        sys.exit(1)
    
    command = sys.argv[1].upper()
    
    if command == "LIST":
        list_tables()
    else:
        export_table_to_csv(command)