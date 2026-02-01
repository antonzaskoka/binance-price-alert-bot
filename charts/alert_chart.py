"""
Побудова графіків для алертів
"""
import matplotlib.pyplot as plt
import os

from config import CHART_DIR


def build_alert_chart(df, symbol, levels=None):
    """Будує графік алерта зі свічками та рівнями"""
    fig = plt.figure(figsize=(10, 6))
    levels = levels or []

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

    # ✅ ДИНАМІЧНИЙ МАСШТАБ Y
    min_price = df["low"].min()
    max_price = df["high"].max()
    price_range = max_price - min_price
    
    y_min = min_price - 0.1 * price_range
    y_max = max_price + 0.1 * price_range
    
    ax_price.set_ylim(y_min, y_max)

    # Рівні
    for lvl in levels:
        ax_price.axhline(lvl, color="blue", linestyle="--", linewidth=1)

    ax_price.set_ylabel("Price")
    ax_price.grid(True, alpha=0.3)
    ax_price.set_xticks([])

    # Об'єм
    ax_vol.bar(range(len(df)), df["volume"], color="gray", alpha=0.7)
    ax_vol.set_ylabel("Volume")
    ax_vol.set_xlabel("Time")
    
    step = max(1, len(df) // 10)
    ax_vol.set_xticks(range(0, len(df), step))
    
    time_labels = []
    for i in range(0, len(df), step):
        time_val = df["time"].iloc[i]
        if hasattr(time_val, 'strftime'):
            time_labels.append(time_val.strftime('%H:%M'))
        else:
            time_labels.append(str(time_val)[11:16])
    
    ax_vol.set_xticklabels(time_labels, rotation=45)

    file_path = os.path.join(CHART_DIR, f"{symbol}_alert_chart.png")

    plt.savefig(file_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    return file_path