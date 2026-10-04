#!/usr/bin/env python3
"""stage4_analyze.py -- Analyze scenario results CSV and produce plots."""
import sys
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path
from ..pipeline_utils import load_config, get_logger, ensure_dirs, latest_file

COL_ACID = "Acetic Acid Feed.mass_flow_kgh"
COL_BICARB = "Sodium bicarbonate Feed.mass_flow_kgh"
COL_PUMP_A = "pump_a_bar"
COL_PUMP_B = "pump_b_bar"
COL_RISK = "risk_level"
COL_NAME = "scenario"

RISK_COLORS = {
    "OK": "#2ecc71",
    "WARNING": "#f1c40f",
    "CRITICAL": "#e67e22",
    "HAZARDOUS": "#e74c3c",
    "CATASTROPHIC": "#8e44ad",
    "ERROR": "#95a5a6",
}

RISK_ORDER = ["OK", "WARNING", "CRITICAL", "HAZARDOUS", "CATASTROPHIC", "ERROR"]

def _color(level):
    return RISK_COLORS.get(str(level).upper(), "#95a5a6")

def analyze_results(config: dict, csv_path: str = None) -> str:
    log = get_logger("stage4_analyze", config.get("log_dir"))
    out_dir = Path(config.get("output_dir", "pipeline_output"))
    plots = out_dir / "plots"
    ensure_dirs(str(plots))

    if csv_path is None:
        csv_path = latest_file(str(out_dir), "scenario_results_summary*.csv")
    log.info(f"Reading: {csv_path}")
    df = pd.read_csv(csv_path)
    df[COL_RISK] = df[COL_RISK].astype(str).str.upper()

    # Plot 1: Risk distribution bar chart
    counts = df[COL_RISK].value_counts().reindex(RISK_ORDER, fill_value=0)
    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.bar(
        counts.index,
        counts.values,
        color=[_color(r) for r in counts.index],
        edgecolor="black",
        linewidth=0.7
    )
    ax.bar_label(bars, padding=3, fontsize=10)
    ax.set_title("HAZOP Scenario Risk Distribution", fontsize=14, fontweight="bold")
    ax.set_xlabel("Risk Level")
    ax.set_ylabel("Number of Scenarios")
    ax.set_ylim(0, max(counts.max() * 1.2 + 1, 5))
    plt.tight_layout()
    fig.savefig(plots / "risk_distribution.png", dpi=150)
    plt.close(fig)
    log.info("Saved: risk_distribution.png")

    # Plot 2: Feed A vs Feed B scatter
    if COL_ACID in df.columns and COL_BICARB in df.columns:
        fig, ax = plt.subplots(figsize=(9, 6))
        for level in RISK_ORDER:
            grp = df[df[COL_RISK] == level]
            if grp.empty:
                continue
            ax.scatter(
                grp[COL_ACID],
                grp[COL_BICARB],
                c=_color(level),
                label=level,
                s=80,
                edgecolors="black",
                linewidths=0.5,
                zorder=3
            )
        ax.set_xlabel("Acetic Acid Feed (kg/h)")
        ax.set_ylabel("NaHCO3 Feed (kg/h)")
        ax.set_title("Feed Flow Deviation Map -- Risk Classification", fontsize=13, fontweight="bold")
        ax.legend(title="Risk Level", bbox_to_anchor=(1.01, 1), loc="upper left")
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        fig.savefig(plots / "feed_flow_risk_map.png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        log.info("Saved: feed_flow_risk_map.png")
    else:
        log.warning("Columns not found -- skipping feed scatter plot")

    # Plot 3: Pump pressure risk map
    if COL_PUMP_A in df.columns:
        fig, ax = plt.subplots(figsize=(9, 5))
        pump_b_col = df[COL_PUMP_B] if COL_PUMP_B in df.columns else df[COL_PUMP_A]
        for level in RISK_ORDER:
            grp = df[df[COL_RISK] == level]
            if grp.empty:
                continue
            ax.scatter(
                grp[COL_PUMP_A],
                grp[COL_PUMP_B] if COL_PUMP_B in df.columns else grp[COL_PUMP_A],
                c=_color(level),
                label=level,
                s=80,
                edgecolors="black",
                linewidths=0.5,
                zorder=3
            )
        ax.set_xlabel("Pump A Pressure (bar_abs)")
        ax.set_ylabel("Pump B Pressure (bar_abs)")
        ax.set_title("Pump Pressure Risk Map", fontsize=13, fontweight="bold")
        ax.legend(title="Risk Level", bbox_to_anchor=(1.01, 1), loc="upper left")
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        fig.savefig(plots / "pump_pressure_risk_map.png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        log.info("Saved: pump_pressure_risk_map.png")

    # Generate hazard register
    reg = df[df[COL_RISK] != "OK"].copy()
    reg_path = out_dir / "hazard_register.csv"
    reg.to_csv(reg_path, index=False)
    log.info(f"Hazard register saved: {reg_path} ({len(reg)} entries)")

    return str(reg_path)

if __name__ == "__main__":
    cfg = load_config("config.json")
    analyze_results(cfg)
