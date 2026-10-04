#!/usr/bin/env python3
"""stage6_report.py -- Generate HAZOP HTML/PDF report from scenario results."""
import sys
import json
import pandas as pd
from pathlib import Path
from datetime import datetime
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

def _risk_badge(level: str) -> str:
    color = RISK_COLORS.get(str(level).upper(), "#95a5a6")
    return (
        f'<span style="background:{color};color:#fff;padding:2px 8px;'
        f'border-radius:4px;font-weight:bold;font-size:0.85em;">'
        f'{level}</span>'
    )

def _df_to_html_table(df: pd.DataFrame, risk_col: str = "risk_level") -> str:
    rows = []
    for _, row in df.iterrows():
        cells = []
        for col in df.columns:
            val = row[col]
            if col == risk_col:
                cells.append(f"<td>{_risk_badge(str(val))}</td>")
            else:
                if isinstance(val, float):
                    cells.append(f"<td>{val:.4g}</td>")
                else:
                    cells.append(f"<td>{val}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")

    headers = "".join(
        f'<th style="background:#2c3e50;color:#fff;padding:6px 10px;text-align:left;">'
        f'{c.replace("_", " ").title()}</th>'
        for c in df.columns
    )
    body = "\n".join(rows)
    return f"""
<table style="border-collapse:collapse;width:100%;font-size:0.82em;" border="1">
<thead><tr>{headers}</tr></thead>
<tbody>{body}</tbody>
</table>"""

def generate_report(config: dict, csv_path: str = None,
                    plots_dir: str = None, images_dir: str = None,
                    reg_path: str = None) -> str:
    log = get_logger("stage6_report", config.get("log_dir"))
    out_dir = Path(config.get("output_dir", "pipeline_output"))
    report_dir = Path(config.get("report_dir", "reports"))
    ensure_dirs(str(out_dir), str(report_dir))

    if csv_path is None:
        csv_path = latest_file(str(out_dir), "scenario_results_summary*.csv")
    log.info(f"Reading results: {csv_path}")
    df = pd.read_csv(csv_path)
    df["risk_level"] = df["risk_level"].astype(str).str.upper()

    risk_num = {r: i for i, r in enumerate(RISK_ORDER)}
    df["_risk_num"] = df["risk_level"].map(risk_num).fillna(0).astype(int)

    # Hazard register
    register_path = Path(reg_path) if reg_path else (out_dir / "hazard_register.csv")
    if register_path.exists():
        reg = pd.read_csv(register_path)
        log.info(f"Loaded hazard register: {register_path}")
    else:
        reg = df[df["risk_level"] != "OK"].copy()

    # Summary statistics
    total = len(df)
    counts = df["risk_level"].value_counts().reindex(RISK_ORDER, fill_value=0)
    high_risk = df[df["_risk_num"] >= risk_num.get("CRITICAL", 2)]
    run_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    plots_path = Path(plots_dir) if plots_dir else out_dir / "plots"
    images_path = Path(images_dir) if images_dir else out_dir / "images"

    def _img_tag(folder: Path, fname: str, width: str = "100%") -> str:
        p = folder / fname
        if p.exists():
            rel = p.relative_to(out_dir) if p.is_relative_to(out_dir) else p
            return f'<div style="margin:10px 0;"><img src="{rel}" style="max-width:{width};border:1px solid #ccc;border-radius:4px;"/></div>'
        return ""

    # Build HTML content
    html_parts = [
        "<!DOCTYPE html>",
        "<html><head><meta charset='utf-8'><title>DWSIM HAZOP Study Report</title>",
        "<style>",
        "body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; margin: 30px; color: #333; line-height: 1.5; }",
        "h1, h2, h3 { color: #2c3e50; }",
        "table { margin-bottom: 20px; border: 1px solid #ddd; border-collapse: collapse; }",
        "th, td { padding: 8px 12px; border: 1px solid #ddd; }",
        ".metric-box { display: inline-block; padding: 15px 25px; margin: 10px 10px 10px 0; background: #f8f9fa; border-left: 4px solid #3498db; border-radius: 4px; }",
        ".metric-value { font-size: 1.8em; font-weight: bold; color: #2c3e50; }",
        ".metric-label { font-size: 0.9em; color: #7f8c8d; }",
        "</style></head><body>",
        f"<h1>Automated HAZOP Analysis Report</h1>",
        f"<p><strong>Generated:</strong> {run_ts} | <strong>System:</strong> Batch Reactor PD-BR-001 (Acetic Acid + NaHCO3)</p>",
        "<hr/>",
        "<h2>1. Executive Summary</h2>",
        f"<div class='metric-box'><div class='metric-value'>{total}</div><div class='metric-label'>Total Scenarios</div></div>",
        f"<div class='metric-box'><div class='metric-value' style='color:#e74c3c;'>{len(high_risk)}</div><div class='metric-label'>Critical / High-Risk</div></div>",
        f"<div class='metric-box'><div class='metric-value' style='color:#f1c40f;'>{counts.get('WARNING', 0)}</div><div class='metric-label'>Warnings</div></div>",
        f"<div class='metric-box'><div class='metric-value' style='color:#2ecc71;'>{counts.get('OK', 0)}</div><div class='metric-label'>Normal (OK)</div></div>",
        "<h2>2. Risk Visualizations</h2>",
        _img_tag(plots_path, "risk_distribution.png", "80%"),
        _img_tag(plots_path, "feed_flow_risk_map.png", "80%"),
        _img_tag(plots_path, "pump_pressure_risk_map.png", "80%"),
        _img_tag(images_path, "high_risk_scenarios.png", "100%"),
        _img_tag(images_path, "risk_pie_chart.png", "60%"),
        "<h2>3. Action-Required Hazard Register</h2>",
        f"<p>Identified {len(reg)} scenarios with deviations requiring review or mitigation:</p>",
        _df_to_html_table(reg.drop(columns=["_risk_num"], errors="ignore").head(40)),
        "<h2>4. Complete Scenarios Table</h2>",
        _df_to_html_table(df.drop(columns=["_risk_num"], errors="ignore")),
        "</body></html>"
    ]

    html_content = "\n".join(html_parts)
    html_out = out_dir / "hazop_report.html"
    html_out.write_text(html_content, encoding="utf-8")
    log.info(f"Saved HTML report: {html_out}")

    # Also write markdown version
    md_lines = [
        "# Automated HAZOP Analysis Report",
        f"**Generated:** {run_ts} | **System:** Batch Reactor PD-BR-001 (Acetic Acid + NaHCO3)",
        "",
        "## Executive Summary",
        f"- **Total Scenarios Analyzed:** {total}",
        f"- **High-Risk (Critical / Hazardous / Catastrophic):** {len(high_risk)}",
        f"- **Warnings:** {counts.get('WARNING', 0)}",
        f"- **Normal (OK):** {counts.get('OK', 0)}",
        "",
        "## Key High-Risk Findings",
    ]
    for _, r in high_risk.head(15).iterrows():
        md_lines.append(f"- **{r.get('scenario', 'Unknown')}** [{r.get('risk_level', '')}]: {r.get('primary_hazard', '')}")
    md_lines.append("")
    md_lines.append("See `hazop_report.html` for complete interactive tables and visualization cards.")

    md_out = out_dir / "hazop_report.md"
    md_out.write_text("\n".join(md_lines), encoding="utf-8")
    log.info(f"Saved Markdown report: {md_out}")

    # Copy to report_dir
    try:
        (report_dir / "hazop_report.html").write_text(html_content, encoding="utf-8")
        (report_dir / "hazop_report.md").write_text("\n".join(md_lines), encoding="utf-8")
    except Exception:
        pass

    return str(html_out)

if __name__ == "__main__":
    cfg = load_config("config.json")
    generate_report(cfg)
