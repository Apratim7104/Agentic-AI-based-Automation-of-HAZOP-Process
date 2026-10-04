#!/usr/bin/env python3
"""stage5_images.py -- Generate HAZOP summary image cards."""
import sys
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path
from ..pipeline_utils import load_config, get_logger, ensure_dirs, latest_file

RISK_COLORS = {
    "OK": "#2ecc71",
    "WARNING": "#f1c40f",
    "CRITICAL": "#e67e22",
    "HAZARDOUS": "#e74c3c",
    "CATASTROPHIC": "#8e44ad",
    "ERROR": "#95a5a6",
}

RISK_ORDER = ["OK", "WARNING", "CRITICAL", "HAZARDOUS", "CATASTROPHIC", "ERROR"]

def _draw_summary_card(df: pd.DataFrame, out_path: Path, title: str):
    """Draw a summary card table image."""
    cols_show = [c for c in ["scenario", "risk_level", "primary_hazard"] if c in df.columns]
    df_show = df[cols_show].copy()
    df_show["risk_level"] = df_show["risk_level"].astype(str).str.upper()

    n_rows = len(df_show)
    fig_h = max(4.0, 0.35 * n_rows + 1.5)
    fig, ax = plt.subplots(figsize=(14, fig_h))
    ax.set_axis_off()

    header_y = 0.97
    ax.text(
        0.5, header_y, title,
        transform=ax.transAxes, ha="center", va="top",
        fontsize=14, fontweight="bold"
    )

    sep_y = header_y - 0.04
    ax.plot(
        [0.0, 1.0], [sep_y, sep_y],
        transform=ax.transAxes,
        color="black", linewidth=1.5, clip_on=False
    )

    cell_colors = []
    for _, row in df_show.iterrows():
        risk = str(row.get("risk_level", "OK")).upper()
        c = RISK_COLORS.get(risk, "#95a5a6")
        row_c = ["#f8f8f8"] * len(cols_show)
        if "risk_level" in cols_show:
            row_c[cols_show.index("risk_level")] = c
        cell_colors.append(row_c)

    tbl = ax.table(
        cellText=df_show.values.tolist(),
        colLabels=[c.replace("_", " ").title() for c in cols_show],
        cellLoc="left",
        loc="center",
        cellColours=cell_colors,
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(8)
    tbl.auto_set_column_width(col=list(range(len(cols_show))))

    plt.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

def generate_images(config: dict, csv_path: str = None, plots_dir: str = None) -> str:
    log = get_logger("stage5_images", config.get("log_dir"))
    out_dir = Path(config.get("output_dir", "pipeline_output"))
    img_dir = out_dir / "images"
    ensure_dirs(str(img_dir))

    if csv_path is None:
        csv_path = latest_file(str(out_dir), "scenario_results_summary*.csv")
    log.info(f"Reading: {csv_path}")
    df = pd.read_csv(csv_path)
    df["risk_level"] = df["risk_level"].astype(str).str.upper()

    risk_num = {r: i for i, r in enumerate(RISK_ORDER)}
    df["_risk_num"] = df["risk_level"].map(risk_num).fillna(0).astype(int)

    # Card 1: All scenarios
    _draw_summary_card(
        df.sort_values("_risk_num", ascending=False),
        img_dir / "all_scenarios_summary.png",
        "HAZOP Scenario Summary -- All Scenarios"
    )
    log.info("Saved: all_scenarios_summary.png")

    # Card 2: Critical and above
    crit_level_idx = risk_num.get("CRITICAL", 2)
    high_risk = df[df["_risk_num"] >= crit_level_idx]
    if not high_risk.empty:
        _draw_summary_card(
            high_risk.sort_values("_risk_num", ascending=False),
            img_dir / "high_risk_scenarios.png",
            "HAZOP -- CRITICAL / HAZARDOUS / CATASTROPHIC Scenarios"
        )
        log.info("Saved: high_risk_scenarios.png")
    else:
        log.info("No high-risk scenarios -- skipping high_risk_scenarios.png")

    # Card 3: Risk distribution pie chart
    counts = df["risk_level"].value_counts()
    fig, ax = plt.subplots(figsize=(7, 7))
    colors = [_color(lvl) for lvl in counts.index]
    ax.pie(
        counts.values,
        labels=counts.index,
        autopct="%1.1f%%",
        colors=colors,
        startangle=140,
        textprops={"fontsize": 11, "fontweight": "bold"}
    )
    ax.set_title("HAZOP Scenarios Risk Breakdown", fontsize=14, fontweight="bold")
    plt.tight_layout()
    fig.savefig(img_dir / "risk_pie_chart.png", dpi=150)
    plt.close(fig)
    log.info("Saved: risk_pie_chart.png")

    return str(img_dir)

if __name__ == "__main__":
    cfg = load_config("config.json")
    generate_images(cfg)
