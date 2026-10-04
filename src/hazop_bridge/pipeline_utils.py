#!/usr/bin/env python3
"""pipeline_utils.py Shared helpers for the DWSIM HAZOP pipeline."""
import json
import glob
import logging
import time
from pathlib import Path

#
# Config loader
#
def load_config(path: str = "config.json") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

#
# Flowsheet URL / Path resolver
#
def resolve_sim_file(sim_file_input: str = None, config: dict = None, log=None) -> str:
    """
    Resolve the DWSIM simulation flowsheet from user input (CLI / interactive) or config.
    Supports:
      - Local file path (absolute or relative)
      - Remote URL (http:// or https://) downloaded to a local cache directory
      - Interactive user prompt when input is not provided and config has a placeholder/missing path.
    """
    import os
    import sys
    import urllib.request
    import urllib.parse

    sim_file = sim_file_input

    # If not supplied directly via CLI, check if we should prompt the user
    if not sim_file:
        config_sim = config.get("sim_file", "") if config else ""
        is_placeholder = (
            not config_sim
            or "Path/To" in str(config_sim)
            or "Path\\To" in str(config_sim)
            or not Path(str(config_sim)).exists()
        )
        if sys.stdin and (sys.stdin.isatty() or is_placeholder):
            prompt = (
                f"Enter DWSIM Simulation Flowsheet URL or file path [{config_sim}]: "
                if config_sim and not is_placeholder
                else "Enter DWSIM Simulation Flowsheet URL or file path: "
            )
            try:
                user_val = input(prompt).strip()
                if user_val:
                    sim_file = user_val
                elif not is_placeholder:
                    sim_file = config_sim
            except (EOFError, KeyboardInterrupt):
                if not is_placeholder:
                    sim_file = config_sim
        else:
            sim_file = config_sim

    if not sim_file:
        return ""

    # Clean quotes and surrounding whitespace
    sim_file = str(sim_file).strip().strip("'\"")

    # If it's a URL, download it to a local flowsheet directory
    if sim_file.startswith(("http://", "https://")):
        parsed = urllib.parse.urlparse(sim_file)
        filename = Path(parsed.path).name or f"flowsheet_{stamp()}.dwxmz"
        download_dir = Path("data/flowsheets")
        if config and "output_dir" in config:
            download_dir = Path(config["output_dir"]) / "flowsheets"
        download_dir.mkdir(parents=True, exist_ok=True)
        dest_path = download_dir / filename

        msg = f"Downloading DWSIM flowsheet from URL: {sim_file} -> {dest_path}"
        if log:
            log.info(msg)
        else:
            print(msg)

        try:
            req = urllib.request.Request(
                sim_file,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            with urllib.request.urlopen(req) as response, open(dest_path, "wb") as out_f:
                out_f.write(response.read())
        except Exception as exc:
            err_msg = f"Failed to download DWSIM flowsheet from URL '{sim_file}': {exc}"
            if log:
                log.error(err_msg)
            raise RuntimeError(err_msg) from exc

        if log:
            log.info(f"Flowsheet downloaded successfully ({dest_path.stat().st_size} bytes).")
        return str(dest_path.resolve())

    # Otherwise treat as a local path
    local_path = Path(os.path.expandvars(os.path.expanduser(sim_file)))
    return str(local_path.resolve() if local_path.is_absolute() else local_path)

#
# Logger
#
def get_logger(name: str, log_dir: str = None) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    if log_dir:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(Path(log_dir) / f"{name}.log", encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    return logger

#
# Stage timer context manager
#
class StageTimer:
    def __init__(self, label: str, logger: logging.Logger):
        self.label = label
        self.logger = logger

    def __enter__(self):
        self._t0 = time.time()
        self.logger.info("=" * 60)
        self.logger.info(f"START {self.label}")
        self.logger.info("=" * 60)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = time.time() - self._t0
        if exc_type:
            self.logger.error(
                f"FAILED {self.label} ({elapsed:.1f}s) - "
                f"{exc_type.__name__}: {exc_val}"
            )
        else:
            self.logger.info(f"DONE {self.label} ({elapsed:.1f}s)")
        return False  # do not suppress exceptions

#
# Timestamp helper
#
def stamp() -> str:
    import datetime
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

#
# Directory helper
#
def ensure_dirs(*dirs):
    for d in dirs:
        if d:
            Path(d).mkdir(parents=True, exist_ok=True)

#
# latest_file - find the most-recently modified
# file matching a glob pattern in a directory
#
def latest_file(directory: str, pattern: str) -> str:
    """
    Return the path of the most recently modified file matching
    'pattern' (e.g. 'scenario_results_summary*.csv') inside 'directory'.
    Raises FileNotFoundError if no match is found.
    """
    search = str(Path(directory) / pattern)
    matches = glob.glob(search)
    if not matches:
        raise FileNotFoundError(
            f"No files matching '{pattern}' found in '{directory}'"
        )
    return max(matches, key=lambda p: Path(p).stat().st_mtime)

#
# Risk thresholds loader
#
def load_thresholds(path: str) -> dict:
    """Load risk_thresholds.json, stripping keys that start with '_'."""
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if not k.startswith("_")}

#
# classify_risk - works with real threshold keys
#
def classify_risk(result: dict, thresholds: dict) -> tuple:
    """
    Classify overall risk level for one scenario result row.

    Parameters
    ----------
    result : dict
        One row of computed scenario values,
        keys must match risk_thresholds.json keys
    thresholds : dict
        Loaded from risk_thresholds.json (pre-stripped of _ keys)

    Returns
    -------
    (risk_level, primary_hazard) both strings
    """
    LEVELS = ["OK", "WARNING", "CRITICAL", "HAZARDOUS", "CATASTROPHIC"]
    worst_level = "OK"
    worst_hazard = "None"

    def _upgrade(current, candidate):
        if candidate in LEVELS and current in LEVELS:
            if LEVELS.index(candidate) > LEVELS.index(current):
                return candidate
        return current

    for key, limits in thresholds.items():
        if key.startswith("_"):
            continue
        if key not in result:
            continue
        val = result[key]
        if val is None:
            continue
        try:
            val = float(val)
        except (TypeError, ValueError):
            continue

        # reverse-flow check
        if limits.get("_reverse_is_critical") and val < 0:
            level = "CRITICAL"
            hazard = f"{key} reverse flow ({val:.4f} < 0)"
            if LEVELS.index(level) > LEVELS.index(worst_level):
                worst_level = level
                worst_hazard = hazard
            continue

        level = "OK"
        hazard = None

        if "catastrophic" in limits and val >= limits["catastrophic"]:
            level = "CATASTROPHIC"
            hazard = f"{key} >= {limits['catastrophic']} catastrophic limit ({val:.4f})"
        elif "burst_risk" in limits and val >= limits["burst_risk"]:
            level = "HAZARDOUS"
            hazard = f"{key} >= {limits['burst_risk']} burst risk ({val:.4f})"
        elif "hazardous" in limits and val >= limits["hazardous"]:
            level = "HAZARDOUS"
            hazard = f"{key} >= {limits['hazardous']} hazardous limit ({val:.4f})"
        elif "max" in limits and val >= limits["max"]:
            level = "CRITICAL"
            hazard = f"{key} >= {limits['max']} critical max ({val:.4f})"
        elif "min" in limits and val <= limits["min"]:
            level = "CRITICAL"
            hazard = f"{key} <= {limits['min']} critical min ({val:.4f})"
        elif "max_warning" in limits and val >= limits["max_warning"]:
            level = "WARNING"
            hazard = f"{key} >= {limits['max_warning']} warning max ({val:.4f})"
        elif "min_warning" in limits and val <= limits["min_warning"]:
            level = "WARNING"
            hazard = f"{key} <= {limits['min_warning']} warning min ({val:.4f})"

        if level != "OK" and LEVELS.index(level) > LEVELS.index(worst_level):
            worst_level = level
            worst_hazard = hazard

    return worst_level, worst_hazard

if __name__ == "__main__":
    print("pipeline_utils module loaded successfully.")
