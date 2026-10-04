#!/usr/bin/env python3
"""Package entry point for the DWSIM HAZOP pipeline."""
import argparse
import sys
import time
from pathlib import Path
from .pipeline_utils import (
    load_config, get_logger, StageTimer,
    stamp, ensure_dirs, resolve_sim_file
)

class PipelineResult:
    def __init__(self):
        self.stages = {}
        self.start = time.perf_counter()

    def record(self, name, status, duration, output=None):
        self.stages[name] = {
            "status": status,
            "duration": duration,
            "output": str(output) if output else "",
        }

    def summary(self):
        lines = ["", "=" * 65, " PIPELINE SUMMARY ", "=" * 65]
        for name, info in self.stages.items():
            icon = "OK" if info["status"] == "OK" else "FAIL"
            lines.append(f" [{icon}] {name:<35} ({info['duration']:.1f}s)")
            if info["output"]:
                lines.append(f"      -> {info['output']}")
        lines += ["=" * 65, f" Total: {time.perf_counter() - self.start:.1f}s", "=" * 65, ""]
        return "\n".join(lines)

    def all_ok(self):
        return all(v["status"] == "OK" for v in self.stages.values())

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="DWSIM HAZOP Full Pipeline Orchestrator"
    )
    parser.add_argument("--config", default="config.json")
    parser.add_argument(
        "flowsheet_pos",
        nargs="?",
        default=None,
        help="Optional positional URL or local path to the DWSIM Simulation Flowsheet (.dwxmz)",
    )
    parser.add_argument(
        "--sim-file", "--flowsheet", "--sim-path", "--flowsheet-url",
        dest="sim_file",
        default=None,
        help="URL or local path to the DWSIM Simulation Flowsheet (.dwxmz)",
    )
    parser.add_argument("--scenarios", default=None)
    parser.add_argument("--regenerate-scenarios", action="store_true")
    parser.add_argument("--n-random", type=int, default=100)
    parser.add_argument("--skip-stage1", action="store_true")
    parser.add_argument("--start-stage", type=int, default=1, choices=range(1, 8))
    parser.add_argument("--stop-stage", type=int, default=7, choices=range(1, 8))
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    log = get_logger("orchestrator", cfg.get("log_dir"))

    # Resolve DWSIM Simulation Flowsheet URL or path from user
    sim_input = args.sim_file or args.flowsheet_pos
    flowsheet_target = resolve_sim_file(sim_input, cfg, log)
    if flowsheet_target:
        cfg["sim_file"] = flowsheet_target

    ensure_dirs(cfg.get("output_dir", "pipeline_output"),
                cfg.get("log_dir", "logs"),
                cfg.get("report_dir", "reports"))

    ts = stamp()
    log.info("=" * 65)
    log.info(" DWSIM HAZOP PIPELINE - run_full_pipeline.py")
    log.info(f" Run ID: {ts} | Config: {args.config}")
    log.info(f" Flowsheet: {cfg.get('sim_file', 'Not specified')}")
    log.info("=" * 65)

    result = PipelineResult()
    csv_path = None
    reg_path = None
    sc_path = None
    exit_code = 0

    def run_stage(num, name, fn, *fn_args):
        nonlocal exit_code
        if num < args.start_stage or num > args.stop_stage:
            log.info(f" SKIP Stage {num} ({name}) - outside range")
            return None
        t0 = time.perf_counter()
        try:
            with StageTimer(f"Stage {num} - {name}", log):
                out = fn(*fn_args)
            result.record(name, "OK", time.perf_counter() - t0, out)
            return out
        except Exception as exc:
            log.error(f"Stage {num} ({name}) FAILED: {exc}", exc_info=True)
            result.record(name, "FAILED", time.perf_counter() - t0)
            exit_code = 1
            return None

    # Stage 1: DEXPI Export
    if not args.skip_stage1:
        from .stages.stage1_dexpi import export_dexpi
        run_stage(1, "DEXPI Export", export_dexpi, cfg)
    else:
        log.info(" SKIP Stage 1 - --skip-stage1 flag set")

    # Stage 2: Scenario Generation
    from .stages.stage2_scenarios import generate_scenarios
    sc_path = run_stage(2, "Scenario Generation", generate_scenarios,
                        cfg, args.regenerate_scenarios, args.n_random)

    if args.scenarios:
        override = Path(cfg.get("bridge_dir", "pipeline_output")) / args.scenarios
        if override.exists():
            sc_path = override
            log.info(f"Scenario override: {sc_path}")
        else:
            log.warning(f"--scenarios not found: {override}")

    if sc_path is None:
        sc_path = Path(cfg.get("bridge_dir", "pipeline_output")) / cfg.get("default_scenarios", "scenarios_config_hazop80.json")

    # Stage 3: Simulation Execution
    from .stages.stage3_run_scenarios import run_scenarios
    csv_path = run_stage(3, "Run Scenarios", run_scenarios, cfg, sc_path)

    # Stage 4: Results Analysis
    from .stages.stage4_analyze import analyze_results
    reg_path = run_stage(4, "Analyze Results", analyze_results, cfg, csv_path)

    # Stage 5: Visualization
    from .stages.stage5_images import generate_images
    run_stage(5, "Generate Images", generate_images, cfg, csv_path)

    # Stage 6: Report Generation
    from .stages.stage6_report import generate_report
    run_stage(6, "Generate Report", generate_report, cfg, csv_path, None, None, reg_path)

    # Stage 7: Multi-Agent Debate
    from .stages.stage7_debate import run_debate_stage
    run_stage(7, "Multi-Agent Debate & Resolution", run_debate_stage, cfg, csv_path)

    log.info(result.summary())
    if result.all_ok():
        log.info("PIPELINE COMPLETED SUCCESSFULLY!")
    else:
        log.error("PIPELINE COMPLETED WITH ERRORS - review log.")
        exit_code = max(exit_code, 1)

    return exit_code

if __name__ == "__main__":
    sys.exit(main())
