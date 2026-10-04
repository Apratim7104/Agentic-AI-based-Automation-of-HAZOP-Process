#!/usr/bin/env python3
"""stage2_scenarios.py -- Generate HAZOP scenario list (80 scenarios)."""
import json
from pathlib import Path
import sys
from ..pipeline_utils import load_config, get_logger, ensure_dirs

NOM_ACID = 0.6048
NOM_BICARB = 2.593
NOM_PUMP_A = 1.01325
NOM_PUMP_B = 1.01325
NOM_TEMP = 25.0

ACID_KEY = "Acetic Acid Feed.mass_flow_kgh"
BICARB_KEY = "Sodium bicarbonate Feed.mass_flow_kgh"
PUMP_A_KEY = "pump_a_bar"
PUMP_B_KEY = "pump_b_bar"
TEMP_KEY = "Feed Mixture.temperature_C"

def _sc(name, acid=NOM_ACID, bicarb=NOM_BICARB,
        pump_a=NOM_PUMP_A, pump_b=NOM_PUMP_B, temp=NOM_TEMP):
    return {
        "name": name,
        ACID_KEY: acid,
        BICARB_KEY: bicarb,
        PUMP_A_KEY: pump_a,
        PUMP_B_KEY: pump_b,
        TEMP_KEY: temp,
    }

def build_scenarios() -> list:
    """Return list of 80 HAZOP scenario dicts."""
    sc = []

    # 1. Nominal
    sc.append(_sc("Nominal"))

    # 2. Feed A deviations
    feed_a_cases = [
        (0.0, "Feed_A_ZERO"),
        (-0.1, "Feed_A_minus10pct"),
        (-0.5, "Feed_A_minus50pct"),
        (0.5, "Feed_A_plus50pct"),
        (1.0, "Feed_A_plus100pct"),
        (1.5, "Feed_A_plus150pct"),
        (2.0, "Feed_A_plus200pct"),
        (3.0, "Feed_A_plus300pct"),
        (-1.0, "Feed_A_REVERSE"),
    ]
    for pct, label in feed_a_cases:
        if pct >= 0:
            acid = max(0.0, NOM_ACID * (1 + pct))
        else:
            acid = -0.01
        sc.append(_sc(label, acid=acid))

    # 3. Feed B deviations
    feed_b_cases = [
        (0.0, "Feed_B_ZERO"),
        (-0.2, "Feed_B_minus20pct"),
        (-0.5, "Feed_B_minus50pct"),
        (-0.8, "Feed_B_minus80pct"),
        (0.5, "Feed_B_plus50pct"),
        (1.0, "Feed_B_plus100pct"),
        (2.0, "Feed_B_plus200pct"),
        (3.0, "Feed_B_plus300pct"),
        (-1.0, "Feed_B_REVERSE"),
    ]
    for pct, label in feed_b_cases:
        if pct >= 0:
            bicarb = max(0.0, NOM_BICARB * (1 + pct))
        else:
            bicarb = -0.01
        sc.append(_sc(label, bicarb=bicarb))

    # 4. Pump A pressure deviations
    pump_a_cases = [
        (0.0, "PumpA_OFF"),
        (0.3, "PumpA_0p3bar"),
        (0.5, "PumpA_0p5bar"),
        (0.8, "PumpA_0p8bar"),
        (1.20, "PumpA_1p20bar"),
        (1.50, "PumpA_1p50bar"),
        (1.65, "PumpA_1p65bar"),
        (1.81, "PumpA_1p81bar"),
        (2.00, "PumpA_2p00bar"),
        (2.50, "PumpA_2p50bar"),
    ]
    for p, label in pump_a_cases:
        sc.append(_sc(label, pump_a=p))

    # 5. Pump B pressure deviations
    pump_b_cases = [
        (0.0, "PumpB_OFF"),
        (0.3, "PumpB_0p3bar"),
        (0.5, "PumpB_0p5bar"),
        (0.8, "PumpB_0p8bar"),
        (1.20, "PumpB_1p20bar"),
        (1.50, "PumpB_1p50bar"),
        (1.65, "PumpB_1p65bar"),
        (1.81, "PumpB_1p81bar"),
        (2.00, "PumpB_2p00bar"),
        (2.50, "PumpB_2p50bar"),
    ]
    for p, label in pump_b_cases:
        sc.append(_sc(label, pump_b=p))

    # 6. Temperature deviations
    temp_cases = [
        (5.0, "Temp_5C"),
        (15.0, "Temp_15C"),
        (35.0, "Temp_35C"),
        (50.0, "Temp_50C"),
        (70.0, "Temp_70C"),
        (100.0, "Temp_100C"),
    ]
    for t, label in temp_cases:
        sc.append(_sc(label, temp=t))

    # 7. Combined scenarios
    combined = [
        ("Combined_FeedA200_PumpA2p0", NOM_ACID * 3.0, NOM_BICARB, 2.00, NOM_PUMP_B, NOM_TEMP),
        ("Combined_FeedB200_PumpB2p5", NOM_ACID, NOM_BICARB * 3.0, NOM_PUMP_A, 2.50, NOM_TEMP),
        ("Combined_FeedA300_FeedB50", NOM_ACID * 4.0, NOM_BICARB * 0.5, NOM_PUMP_A, NOM_PUMP_B, NOM_TEMP),
        ("Combined_BothPumps_High", NOM_ACID, NOM_BICARB, 1.81, 1.81, NOM_TEMP),
        ("Combined_BothFeeds_Low", NOM_ACID * 0.1, NOM_BICARB * 0.1, NOM_PUMP_A, NOM_PUMP_B, NOM_TEMP),
        ("Combined_HighTemp_HighPumpA", NOM_ACID, NOM_BICARB, 2.0, NOM_PUMP_B, 70.0),
        ("Combined_LowTemp_HighPumpB", NOM_ACID, NOM_BICARB, NOM_PUMP_A, 2.0, 5.0),
        ("Combined_FeedA_Rev_PumpA_Zero", -0.01, NOM_BICARB, 0.0, NOM_PUMP_B, NOM_TEMP),
        ("Combined_FeedB_Rev_PumpB_Zero", NOM_ACID, -0.01, NOM_PUMP_A, 0.0, NOM_TEMP),
        ("Combined_WorstCase_Overpressure", NOM_ACID * 3.0, NOM_BICARB * 3.0, 2.5, 2.5, 80.0),
    ]
    for name, acid, bicarb, pa, pb, t in combined:
        sc.append(_sc(name, acid=acid, bicarb=bicarb, pump_a=pa, pump_b=pb, temp=t))

    # Pad or generate up to 80 systematically if needed
    curr_len = len(sc)
    if curr_len < 80:
        for idx in range(curr_len + 1, 81):
            factor = 1.0 + (idx - 50) * 0.05
            sc.append(_sc(
                f"MultiVar_Sweep_{idx:02d}",
                acid=NOM_ACID * factor,
                bicarb=NOM_BICARB * (2.0 - factor if factor < 2.0 else 0.5),
                pump_a=min(2.5, NOM_PUMP_A * factor),
                pump_b=min(2.5, NOM_PUMP_B * (2.2 - factor if factor < 2.2 else 0.8)),
                temp=25.0 + (factor - 1.0) * 20.0
            ))

    return sc[:80]

def generate_scenarios(config: dict, regenerate: bool = False, n_random: int = 100) -> str:
    log = get_logger("stage2_scenarios", config.get("log_dir"))
    bridge_dir = Path(config.get("bridge_dir", "pipeline_output"))
    ensure_dirs(str(bridge_dir))

    default_file = config.get("default_scenarios", "scenarios_config_hazop80.json")
    out_path = bridge_dir / default_file

    if out_path.exists() and not regenerate:
        log.info(f"Using existing scenarios file: {out_path}")
        return str(out_path)

    log.info(f"Generating 80 structured HAZOP scenarios...")
    scenarios = build_scenarios()
    payload = {
        "description": "80 structured HAZOP deviation scenarios for Acetic Acid + NaHCO3 Batch Reactor",
        "count": len(scenarios),
        "scenarios": scenarios
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    log.info(f"Saved {len(scenarios)} scenarios to: {out_path}")
    return str(out_path)

if __name__ == "__main__":
    cfg = load_config("config.json")
    print(generate_scenarios(cfg))
