#!/usr/bin/env python3
"""stage1_dexpi.py Export DWSIM flowsheet objects to a DEXPI-style JSON."""
import sys
import json
from pathlib import Path
from ..pipeline_utils import (
    load_config, get_logger, StageTimer, stamp, ensure_dirs, resolve_sim_file
)

# Tags we want to interrogate must match your DWSIM flowsheet object names
KNOWN_TAGS = [
    "Acetic Acid Feed",
    "Sodium bicarbonate Feed",
    "Feed Mixture",
    "Conversion reactor",
    "E4",
    "Outlet 1",
    "Outlet 2",
    "PUMP-1",
    "PUMP-2",
    "PUMP-3",
    "VALVE-1",
    "VALVE-2",
    "VALVE-3",
]

# Properties to try reading from each object
PROPS = [
    "MassFlow",
    "Temperature",
    "Pressure",
    "VolumetricFlow",
    "SpecificEnthalpy",
    "Conversion",
]

def _safe_get(obj, prop):
    """Return float value or None never raises."""
    try:
        v = getattr(obj, prop, None)
        return float(v) if v is not None else None
    except Exception:
        return None

def export_dexpi(config: dict) -> str:
    log = get_logger("stage1_dexpi", config.get("log_dir"))
    out_dir = Path(config.get("output_dir", "pipeline_output"))
    ensure_dirs(str(out_dir))

    # Add DWSIM to path
    dwsim_path = config.get("dwsim_path", "")
    if dwsim_path and dwsim_path not in sys.path:
        sys.path.append(dwsim_path)
        log.info(f"Added DWSIM path to sys.path: {dwsim_path}")

    # Ensure DWSIM flowsheet URL/path is resolved
    sim_file = config.get("sim_file", "")
    if not sim_file or "Path/To" in str(sim_file) or str(sim_file).startswith(("http://", "https://")) or not Path(str(sim_file)).exists():
        resolved = resolve_sim_file(config=config, log=log)
        if resolved:
            config["sim_file"] = resolved

    # Load DWSIM
    try:
        import clr
        clr.AddReference(str(Path(dwsim_path) / "DWSIM.Automation.dll"))
        clr.AddReference(str(Path(dwsim_path) / "DWSIM.Interfaces.dll"))
        from DWSIM.Automation import Automation3
        manager = Automation3()
        sim = manager.LoadFlowsheet(config["sim_file"])
        log.info(f"Simulation loaded: {config['sim_file']}")
    except Exception as exc:
        raise RuntimeError(f"Stage 1 failed to load DWSIM: {exc}") from exc

    # Enumerate objects via singular GetFlowsheetSimulationObject
    # The DWSIM Automation API exposes GetFlowsheetSimulationObject(tag)
    # (singular). There is NO plural form. We iterate our known tag list.
    objects_data = []
    for tag in KNOWN_TAGS:
        try:
            obj = sim.GetFlowsheetSimulationObject(tag)
            if obj is None:
                log.debug(f"Tag not found in flowsheet: {tag}")
                continue
            entry = {"tag": tag, "type": type(obj).__name__}
            for prop in PROPS:
                entry[prop] = _safe_get(obj, prop)
            objects_data.append(entry)
            log.debug(f"Exported: {tag} ({entry['type']})")
        except Exception as e:
            log.warning(f"Could not read tag '{tag}': {e}")
    log.info(f"Exported {len(objects_data)} flowsheet objects")

    # Write DEXPI JSON
    ts = stamp()
    out_path = out_dir / f"dexpi_export_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"objects": objects_data}, f, indent=2)
    log.info(f"DEXPI export saved: {out_path}")
    return str(out_path)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Stage 1 - DEXPI Export")
    parser.add_argument("--config", default="config.json")
    parser.add_argument(
        "--sim-file", "--flowsheet", dest="sim_file", default=None,
        help="URL or local path to the DWSIM Simulation Flowsheet (.dwxmz)"
    )
    args = parser.parse_args()
    cfg = load_config(args.config)
    log = get_logger("stage1_dexpi", cfg.get("log_dir"))
    resolved = resolve_sim_file(args.sim_file, cfg, log)
    if resolved:
        cfg["sim_file"] = resolved
    with StageTimer("Stage 1 - DEXPI Export", log):
        print(export_dexpi(cfg))
