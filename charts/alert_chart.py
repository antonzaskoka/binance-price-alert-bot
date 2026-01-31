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
        ax_price.plot([i, i], [row["low"], row["high"]], color=color)
        ax_price.bar(
            i,
            abs(row["close"] - row["open"]),
            bottom=min(row["open"], row["close"]),
            color=color,
            width=0.6
        )

    # Рівні
    for lvl in levels:
        ax_price.axhline(lvl, color="blue", linestyle="--", linewidth=1)

    ax_price.set_ylabel("Price")
    ax_price.grid(True)
    ax_price.set_xticks([])

    # Об'єм
    ax_vol.bar(range(len(df)), df["volume"], color="gray")
    ax_vol.set_ylabel("volume")
    ax_vol.set_xticks(range(0, len(df), 10))
    ax_vol.set_xticklabels(
        [df["time"].iloc[i][11:16] for i in range(0, len(df), 10)],
        rotation=45
    )

    file_path = os.path.join(CHART_DIR, f"{symbol}_alert_chart.png")

    plt.savefig(file_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    return file_path