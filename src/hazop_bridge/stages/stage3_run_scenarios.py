#!/usr/bin/env python3
"""stage3_run_scenarios.py -- Run HAZOP scenarios (DWSIM or ANALYTICAL fallback)."""
import sys
import json
import pandas as pd
from pathlib import Path
from ..pipeline_utils import (
    load_config, get_logger, StageTimer,
    stamp, ensure_dirs, load_thresholds, classify_risk
)

NOMINAL = {
    "Acetic Acid Feed.mass_flow_kgh": 0.6048,
    "Sodium bicarbonate Feed.mass_flow_kgh": 2.593,
    "pump_a_bar": 1.01325,
    "pump_b_bar": 1.01325,
    "Outlet 1.pressure_bar": 1.01325,
    "Outlet 2.pressure_bar": 1.01325,
    "Reactor.delta_P_bar": 0.0,
    "gas_tank_pressure_bar_abs": 0.069,
    "product_tank_fill_kg_per_min": 0.053,
    "Feed Mixture.temperature_C": 25.0,
    "E4.duty_kW": 0.0169,
    "Conversion reactor.conversion_AceticAcid": 95.0,
    "valve_pressure_drop_Pa": 0.0,
    "molar_ratio_B_over_A": 4.29,
}

def _normalise_scenarios(raw) -> list:
    """Accept list-of-dicts, dict-of-dicts, or list-of-strings."""
    if isinstance(raw, dict):
        if "scenarios" in raw and isinstance(raw["scenarios"], list):
            return raw["scenarios"]
        result = []
        for k, v in raw.items():
            if isinstance(v, dict):
                entry = dict(v)
                entry.setdefault("name", k)
                result.append(entry)
            else:
                result.append({"name": str(k)})
        return result
    if isinstance(raw, list):
        result = []
        for i, item in enumerate(raw):
            if isinstance(item, dict):
                item.setdefault("name", f"SC{i+1:03d}")
                result.append(item)
            else:
                result.append({"name": str(item)})
        return result
    raise ValueError(f"Unrecognised scenarios format: {type(raw)}")

def _analytical_result(scenario: dict) -> dict:
    """Physics-based analytical fallback (no DWSIM required)."""
    acid_kgh = float(scenario.get("Acetic Acid Feed.mass_flow_kgh",
                     scenario.get("acid_flow_kgh",
                     NOMINAL["Acetic Acid Feed.mass_flow_kgh"])))
    bicarb_kgh = float(scenario.get("Sodium bicarbonate Feed.mass_flow_kgh",
                       scenario.get("bicarb_flow_kgh",
                       NOMINAL["Sodium bicarbonate Feed.mass_flow_kgh"])))
    pump_a = float(scenario.get("pump_a_bar", NOMINAL["pump_a_bar"]))
    pump_b = float(scenario.get("pump_b_bar", NOMINAL["pump_b_bar"]))
    temp_C = float(scenario.get("Feed Mixture.temperature_C",
                   scenario.get("temperature_C",
                   NOMINAL["Feed Mixture.temperature_C"])))

    gas_p = max(0.0, 0.1146 * max(acid_kgh, 0.0) + 0.0001)
    fill_rate = max(0.0, 0.01667 * max(bicarb_kgh, 0.0) + 0.01006)
    out1 = pump_a
    out2 = pump_b * 0.98
    delta_p = max(0.0, out1 - out2)
    mol_acid = max(acid_kgh, 1e-9) / 60.052
    mol_bicarb = max(bicarb_kgh, 1e-9) / 84.007
    ratio_B_A = mol_bicarb / mol_acid

    if acid_kgh <= 0 or bicarb_kgh <= 0:
        conversion = 0.0
    elif ratio_B_A < 1.0:
        conversion = max(0.0, 95.0 * ratio_B_A)
    else:
        conversion = min(99.0, 95.0 + (ratio_B_A - 4.29) * 0.5)

    duty_kW = max(0.0, 0.0169 * (max(acid_kgh, 0.0) / 0.6048))
    valve_dP = max(0.0, (pump_a - 1.01325) * 1e5)

    return {
        "Acetic Acid Feed.mass_flow_kgh": acid_kgh,
        "Sodium bicarbonate Feed.mass_flow_kgh": bicarb_kgh,
        "pump_a_bar": pump_a,
        "pump_b_bar": pump_b,
        "Outlet 1.pressure_bar": out1,
        "Outlet 2.pressure_bar": out2,
        "Reactor.delta_P_bar": delta_p,
        "gas_tank_pressure_bar_abs": gas_p,
        "product_tank_fill_kg_per_min": fill_rate,
        "Feed Mixture.temperature_C": temp_C,
        "E4.duty_kW": duty_kW,
        "Conversion reactor.conversion_AceticAcid": conversion,
        "valve_pressure_drop_Pa": valve_dP,
        "molar_ratio_B_over_A": ratio_B_A,
    }

def run_scenarios(config: dict, scenarios_path: str = None) -> str:
    log = get_logger("stage3_run_scenarios", config.get("log_dir"))
    out_dir = Path(config.get("output_dir", "pipeline_output"))
    ensure_dirs(str(out_dir))

    if scenarios_path is None:
        bridge_dir = Path(config.get("bridge_dir", "pipeline_output"))
        scenarios_path = bridge_dir / config.get("default_scenarios", "scenarios_config_hazop80.json")

    log.info(f"Loading scenarios from: {scenarios_path}")
    with open(scenarios_path, "r", encoding="utf-8") as f:
        raw_scenarios = json.load(f)

    scenarios = _normalise_scenarios(raw_scenarios)
    log.info(f"Loaded {len(scenarios)} scenarios.")

    thresholds_file = config.get("thresholds_file", "configs/risk_thresholds.json")
    thresholds = load_thresholds(thresholds_file)
    log.info(f"Loaded risk thresholds from {thresholds_file}")

    results = []
    for sc in scenarios:
        name = sc.get("name") or sc.get("id") or "UNKNOWN"
        computed = _analytical_result(sc)
        risk_lvl, primary_hazard = classify_risk(computed, thresholds)

        row = {
            "scenario": name,
            **computed,
            "risk_level": risk_lvl,
            "primary_hazard": primary_hazard,
        }
        results.append(row)

    df = pd.DataFrame(results)

    ts = stamp()
    csv_ts_path = out_dir / f"scenario_results_summary_{ts}.csv"
    csv_std_path = out_dir / "scenario_results_summary.csv"
    xlsx_ts_path = out_dir / f"scenario_results_summary_{ts}.xlsx"

    df.to_csv(csv_ts_path, index=False)
    df.to_csv(csv_std_path, index=False)
    try:
        df.to_excel(xlsx_ts_path, index=False, engine="openpyxl")
    except Exception as e:
        log.warning(f"Excel export skipped: {e}")

    log.info(f"Results summary saved to {csv_ts_path}")
    return str(csv_ts_path)

if __name__ == "__main__":
    cfg = load_config("config.json")
    run_scenarios(cfg)
