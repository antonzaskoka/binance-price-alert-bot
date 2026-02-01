"""
Побудова графіків для меню
"""
import matplotlib.pyplot as plt
import os
from datetime import datetime

from config import CHART_DIR


def build_menu_chart(df, symbol, timeframe, detected_level=None, custom_price=None):
    """
    Будує графік для меню зі свічками, об'ємом та виявленим рівнем
    
    Args:
        df: DataFrame з даними
        symbol: Назва токена
        timeframe: Таймфрейм
        detected_level: dict з {'level': float, 'touches': int} або None
    """
    fig = plt.figure(figsize=(10, 6))

    gs = fig.add_gridspec(2, 1, height_ratios=[3, 1], hspace=0)
    ax_price = fig.add_subplot(gs[0])
    ax_vol = fig.add_subplot(gs[1], sharex=ax_price)

    # Свічки
    for i, row in df.iterrows():
        color = "green" if row["close"] >= row["open"] else "red"
        ax_price.plot([i, i], [row["low"], row["high"]], color=color, linewidth=1)
        ax_price.bar(
            i,
            abs(row["close"] - row["open"]),
            bottom=min(row["open"], row["close"]),
            color=color,
            width=0.6
        )

    # Виявлений рівень (зелена лінія)
    if detected_level:
        level_price = detected_level['level']
        ax_price.axhline(
            level_price,
            color="limegreen",
            linestyle="--",
            linewidth=2,
            label=f"Level: {level_price:.4f}"
        )
        ax_price.legend(loc='upper left', fontsize=8)

    # ✅ Custom price (пурпурова лінія)
    if custom_price:
        ax_price.axhline(
            custom_price,
            color="purple",
            linestyle="-",
            linewidth=2,
            label=f"Custom: {custom_price:.4f}"
        )
        ax_price.legend(loc='upper left', fontsize=8)

    ax_price.set_ylabel("Price")
    ax_price.grid(True, alpha=0.3)
    ax_price.set_xticks([])

    # Об'єм
    ax_vol.bar(range(len(df)), df["volume"], color="gray", alpha=0.7)
    ax_vol.set_ylabel("Volume")
    ax_vol.set_xlabel("Time")
    
    # Підписи часу
    step = max(1, len(df) // 10)
    ax_vol.set_xticks(range(0, len(df), step))
    
    # Форматуємо мітки часу залежно від типу
    time_labels = []
    for i in range(0, len(df), step):
        time_val = df["open_time"].iloc[i]
        if hasattr(time_val, 'strftime'):
            time_labels.append(time_val.strftime('%H:%M'))
        else:
            time_labels.append(str(time_val)[11:16])
    
    ax_vol.set_xticklabels(time_labels, rotation=45)

    plt.title(f"{symbol} | {timeframe}", fontsize=12, fontweight='bold')

    filename = os.path.join(
        CHART_DIR,
        f"{symbol}_{timeframe}_{int(datetime.utcnow().timestamp())}.png"
    )

    plt.savefig(filename, dpi=150, bbox_inches="tight")
    plt.close()

    return filename