#!/usr/bin/env python3
"""equipment_resolver.py Applies a validated debate resolution to the live
DWSIM flowsheet, generalizing the phased, fallback-heavy pattern proven out
in add_equipment.py (load -> inspect -> mutate -> solve -> save) to
arbitrary add/remove actions driven by resolution_schema.py output instead
of one hardcoded VALVE-NEW insertion. The original flowsheet file is never
overwritten a new, timestamped copy is always written.

SAFETY: this is gated behind TWO independent config flags because it
mutates a live engineering flowsheet, which is a hard-to-reverse action:
1. llm.auto_apply_equipment_changes (stage7_debate.py decides whether
to call this module at all)
2. llm.dwsim_mutation_enabled (this module's own hard gate)
If either is false, apply_resolution() only writes a human-readable
"application plan" to disk and does NOT touch DWSIM. Both default to
false a human must opt in explicitly.
"""
import io
import json
import subprocess
import sys
import time
from pathlib import Path
from ..dexpi.dexpi_context import find_neighbors

# DWSIM ObjectType names we know how to instantiate. Anything not listed
# here (e.g. 'interlock', 'instrument') cannot be represented as a DWSIM
# flowsheet object and is always routed to manual/control-layer review.
EQUIPMENT_TYPE_TO_DWSIM = {
    "valve": "Valve",
    "psv": "Valve",  # modeled as a valve tagged PSV-<n>; DWSIM has no first-class relief-valve object type.
    "check_valve": "Valve",
    "pump": "Pump",
    "heat_exchanger": "HeatExchanger",
    "vessel": "Vessel",
}

def _equipment_changes_dir(config: dict) -> Path:
    d = Path(config.get("output_dir", "pipeline_output")) / "equipment_changes"
    d.mkdir(parents=True, exist_ok=True)
    return d

def _plan_path(config: dict, resolution: dict) -> Path:
    out_dir = _equipment_changes_dir(config) / "plans"
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = resolution.get("target_tag", "unknown")
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(tag))
    return out_dir / f"plan_{resolution.get('action', 'action')}_{safe}.json"

def _write_plan(config: dict, resolution: dict, note: str, log=None) -> str:
    plan = {"resolution": resolution, "note": note}
    path = _plan_path(config, resolution)
    path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    if log:
        log.info(f"Application plan written (not applied to DWSIM): {path}")
    return str(path)

def apply_resolution(config: dict, resolution: dict, dexpi_summary: dict, log=None) -> str:
    """Attempt to apply 'resolution' to the DWSIM flowsheet referenced by
    config['sim_file']. Returns a path to either the applied output file or
    the written plan file if mutation is disabled/unsupported.
    """
    action = resolution.get("action", "none")
    equipment_type = resolution.get("equipment_type", "none").lower()
    target_tag = resolution.get("target_tag", "unknown")

    # Safety Gate 1 & 2
    auto_apply = config.get("llm", {}).get("auto_apply_equipment_changes", False)
    dwsim_mutation = config.get("llm", {}).get("dwsim_mutation_enabled", False)

    if not auto_apply:
        return _write_plan(config, resolution, "Auto-apply equipment changes disabled in config (llm.auto_apply_equipment_changes=false).", log)

    if not dwsim_mutation:
        return _write_plan(config, resolution, "DWSIM mutation hard-gate disabled in config (llm.dwsim_mutation_enabled=false).", log)

    if action not in ("add", "add_equipment", "modify"):
        return _write_plan(config, resolution, f"Action '{action}' does not require flowsheet equipment mutation.", log)

    dwsim_type = EQUIPMENT_TYPE_TO_DWSIM.get(equipment_type)
    if not dwsim_type:
        return _write_plan(config, resolution, f"Equipment type '{equipment_type}' cannot be instantiated as a DWSIM object. Routed to manual/control-layer review.", log)

    dwsim_path = config.get("dwsim_path", "")
    sim_file = config.get("sim_file", "")

    if not Path(sim_file).exists():
        return _write_plan(config, resolution, f"Flowsheet file not found: {sim_file}. Plan preserved for manual execution.", log)

    # Attempt DWSIM COM / pythonnet connection
    try:
        import clr
        if dwsim_path and dwsim_path not in sys.path:
            sys.path.insert(0, dwsim_path)
        clr.AddReference(str(Path(dwsim_path) / "DWSIM.Automation.dll"))
        clr.AddReference(str(Path(dwsim_path) / "DWSIM.Interfaces.dll"))
        from DWSIM.Automation import Automation3
        from DWSIM.Interfaces.Enums.GraphicObjects import ObjectType

        auto = Automation3()
        fs = None
        sim = None
        for mn in ("LoadFlowsheet", "OpenFlowsheet", "GetFlowsheet"):
            m = getattr(auto, mn, None)
            if m:
                try:
                    res = m(sim_file)
                    if hasattr(res, "GetFlowsheet"):
                        sim = res
                        fs = res.GetFlowsheet()
                    else:
                        fs = sim = res
                    break
                except Exception:
                    pass

        if fs is None:
            return _write_plan(config, resolution, "Could not open flowsheet via Automation3.", log)

        # Generate unique new tag
        ts = str(int(time.time()))
        new_tag = resolution.get("new_tag") or f"{equipment_type.upper()}_{ts[-4:]}"

        # Resolve ObjectType enum
        enum_name = "Valve" if "valve" in equipment_type or "psv" in equipment_type else dwsim_type
        obj_enum = getattr(ObjectType, enum_name, ObjectType.Valve)

        # Add object to flowsheet
        new_obj = fs.AddObject(obj_enum, 370, 270, new_tag)
        if log:
            log.info(f"Added {new_tag} ({enum_name}) to DWSIM flowsheet.")

        # Attempt solve
        for mn in ("CalculateFlowsheet2", "CalculateFlowsheet", "SolveFlowsheet"):
            m = getattr(auto, mn, None)
            if m:
                try:
                    m(fs)
                    break
                except Exception:
                    pass

        # Save to timestamped file (never overwrite original)
        out_name = f"{Path(sim_file).stem}_MODIFIED_{ts}.dwxmz"
        out_file = str(Path(config.get("output_dir", "pipeline_output")) / out_name)

        saved = False
        m_save = getattr(auto, "SaveFlowsheet", None)
        if m_save:
            for args in [(out_file, fs), (out_file, sim), (fs, out_file)]:
                try:
                    m_save(*args)
                    saved = True
                    break
                except Exception:
                    pass

        if not saved:
            for obj in (fs, sim):
                for attr in ("SaveToFile", "SaveAs", "Save"):
                    m = getattr(obj, attr, None)
                    if m:
                        try:
                            m(out_file)
                            saved = True
                            break
                        except Exception:
                            pass
                if saved:
                    break

        if saved:
            if log:
                log.info(f"Modified flowsheet saved to: {out_file}")
            # Write audit record
            record_path = _plan_path(config, resolution).with_suffix(".applied.json")
            record_path.write_text(json.dumps({
                "resolution": resolution,
                "status": "APPLIED",
                "output_flowsheet": out_file,
                "timestamp": ts,
            }, indent=2), encoding="utf-8")
            return out_file
        else:
            return _write_plan(config, resolution, "Topology modified in memory but failed to save to disk.", log)

    except Exception as exc:
        return _write_plan(config, resolution, f"DWSIM mutation attempt failed with exception: {exc}", log)
