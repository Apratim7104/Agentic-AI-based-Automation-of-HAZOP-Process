#!/usr/bin/env python3
"""stage7_debate.py Multi-agent HAZOP debate & resolution stage.
For every scenario whose risk_level is at/above the configured trigger
level, spins up a bounded debate between process/safety/control engineer
LLM personas (grounded in the DEXPI plant model + the scenario's numeric
deviation, each persona anchored by few-shot examples and its own
cross-run memory), then forces a single structured resolution out of a
moderator agent. The human-facing report (CSV + Excel workbook) is written
locally under ./hazop_debate_reports/ regardless of config.json's
output_dir nothing is applied to the live flowsheet automatically unless
auto_apply is enabled.

Usage (standalone):
python stage7_debate.py
"""
import sys
from pathlib import Path
import pandas as pd
from ..pipeline_utils import load_config, get_logger, StageTimer, stamp, ensure_dirs, latest_file
from ..dexpi.dexpi_context import load_dexpi_summary, render_context_text
from ..llm.llm_client import LLMClient, LLMConfigError
from ..llm.agent_debate import load_personas, run_full_debate_for_scenario
from ..llm.persona_memory import extract_stance
from ..equipment.equipment_resolver import apply_resolution

DEFAULT_TRIGGER_LEVELS = ["CRITICAL", "HAZARDOUS", "CATASTROPHIC"]
DEFAULT_MAX_SCENARIOS = 5
REPO_ROOT = Path(__file__).resolve().parents[3]

def _select_trigger_rows(df: pd.DataFrame, trigger_levels, max_scenarios) -> pd.DataFrame:
    df = df.copy()
    df["risk_level"] = df["risk_level"].astype(str).str.upper()
    triggered = df[df["risk_level"].isin([lvl.upper() for lvl in trigger_levels])]
    return triggered.head(max_scenarios)

def _write_report(reports_dir: Path, ts: str, summary_rows: list, transcript_rows: list) -> Path:
    """Write the comprehensive debate report as both CSV (plain tabular) and
    an Excel workbook with a Resolutions sheet + a full Transcript sheet."""
    ensure_dirs(str(reports_dir))
    summary_df = pd.DataFrame(summary_rows)
    transcript_df = pd.DataFrame(transcript_rows)

    csv_path = reports_dir / f"{ts}_debate_summary.csv"
    summary_df.to_csv(csv_path, index=False)

    xlsx_path = reports_dir / f"{ts}_debate_summary.xlsx"
    try:
        with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
            summary_df.to_excel(writer, sheet_name="Resolutions", index=False)
            transcript_df.to_excel(writer, sheet_name="Full Transcript", index=False)
            for sheet_name, frame in (("Resolutions", summary_df), ("Full Transcript", transcript_df)):
                if frame.empty:
                    continue
                ws = writer.sheets[sheet_name]
                for col_idx, col_name in enumerate(frame.columns, start=1):
                    max_len = frame[col_name].astype(str).str.len().max()
                    max_len = 12 if pd.isna(max_len) else int(max_len)
                    width = min(max(12, max_len + 2), 80)
                    ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = width
    except Exception as e:
        pass

    return csv_path

def run_debate_stage(config: dict, csv_path: str = None) -> str:
    log = get_logger("stage7_debate", config.get("log_dir"))
    out_dir = Path(config.get("output_dir", "pipeline_output"))
    reports_dir = out_dir / "hazop_debate_reports"

    llm_cfg = config.get("llm", {})
    trigger_levels = llm_cfg.get("risk_trigger_levels", DEFAULT_TRIGGER_LEVELS)
    max_scenarios = llm_cfg.get("max_scenarios_per_run", DEFAULT_MAX_SCENARIOS)
    auto_apply = llm_cfg.get("auto_apply_equipment_changes", False)

    if csv_path is None:
        try:
            csv_path = latest_file(str(out_dir), "scenario_results_summary*.csv")
        except FileNotFoundError:
            log.warning("No scenario results CSV found. Debate stage skipped.")
            return ""

    log.info(f"Reading scenario results: {csv_path}")
    df = pd.read_csv(csv_path)
    triggered = _select_trigger_rows(df, trigger_levels, max_scenarios)
    log.info(
        f"{len(triggered)} scenario(s) triggered a debate "
        f"(levels={trigger_levels}, cap={max_scenarios})"
    )

    if triggered.empty:
        log.info("No scenarios triggered debate. Stage 7 complete.")
        return ""

    # Initialize LLM Client
    try:
        client = LLMClient()
    except LLMConfigError as err:
        log.warning(f"LLM Client configuration error: {err}. Skipping LLM debate stage.")
        return ""

    # Load DEXPI Summary Context
    dexpi_dir = Path(config.get("dexpi_dir", "data/dexpi"))
    dexpi_prefix = config.get("dexpi_prefix", "BatchReactor_DEXPI_Export")
    xml_path = dexpi_dir / f"{dexpi_prefix}_v2.xml"
    if not xml_path.exists():
        xml_candidates = list(dexpi_dir.glob("*.xml"))
        if xml_candidates:
            xml_path = xml_candidates[0]
        else:
            log.warning(f"DEXPI XML not found in {dexpi_dir}. Proceeding with minimal context.")
            xml_path = None

    if xml_path and xml_path.exists():
        dexpi_summary = load_dexpi_summary(str(xml_path))
        dexpi_context = render_context_text(dexpi_summary)
    else:
        dexpi_summary = {"equipment": [], "connections": []}
        dexpi_context = "No DEXPI model available. System: Laboratory Batch Reactor PD-BR-001."

    # Load Personas
    personas_file = config.get("personas_config", "configs/personas_config.json")
    personas_cfg = load_personas(personas_file)

    summary_rows = []
    transcript_rows = []
    ts = stamp()

    for idx, (_, row) in enumerate(triggered.iterrows(), start=1):
        row_dict = row.to_dict()
        sc_name = row_dict.get("scenario") or row_dict.get("name") or f"SC_{idx}"
        log.info(f"Starting Multi-Agent Debate for {sc_name} ({row_dict.get('risk_level', 'UNKNOWN')})")

        transcript, resolution = run_full_debate_for_scenario(
            client=client,
            personas_cfg=personas_cfg,
            dexpi_context_text=dexpi_context,
            scenario_row=row_dict,
            log=log
        )

        # Store resolutions
        summary_rows.append({
            "scenario": sc_name,
            "risk_level": row_dict.get("risk_level", "UNKNOWN"),
            "primary_hazard": row_dict.get("primary_hazard", ""),
            "action": resolution.get("action", "none"),
            "equipment_type": resolution.get("equipment_type", "none"),
            "target_tag": resolution.get("target_tag", ""),
            "new_tag": resolution.get("new_tag", ""),
            "rationale": resolution.get("rationale", ""),
            "consensus_level": resolution.get("consensus_level", "MAJORITY"),
            "safety_veto_exercised": resolution.get("safety_veto_exercised", False)
        })

        # Store transcripts
        for turn in transcript.turns:
            transcript_rows.append({
                "scenario": sc_name,
                "round": turn.get("round", 1),
                "persona": turn.get("persona", ""),
                "statement": turn.get("text", "")
            })

        # Apply resolution if auto_apply enabled
        if auto_apply:
            apply_resolution(config, resolution, dexpi_summary, log=log)

    report_path = _write_report(reports_dir, ts, summary_rows, transcript_rows)
    log.info(f"Debate stage complete. Reports saved under: {report_path}")
    return str(report_path)

if __name__ == "__main__":
    cfg = load_config("config.json")
    run_debate_stage(cfg)
