"""Load generated process inputs with the actual model adapter, without solving."""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def verify(model_root: Path, generated: Path):
    metadata = json.loads((generated / "complex_generation.json").read_text(encoding="utf-8"))
    old = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(model_root.resolve()))
    try:
        from scripts.complex_industry_support import prepare_complex_industry_inputs
        flex = pd.read_excel(generated / "industry_inputs.xlsx", sheet_name=["Industry_data", "industry_CC"])
        profiles = pd.read_csv(generated / "industry_heat.csv")
        periods, years = [1, 2, 3], [2020, 2025, 2050]
        result = prepare_complex_industry_inputs(
            workbook_path=generated / metadata["complex_workbook"], industry_data_df=flex["Industry_data"],
            industry_cc_df=flex["industry_CC"], industry_demand_df=profiles, model_industry_categories=False,
            periods=periods, years=years, active_zones=sorted(profiles.zone.unique()), systems=sorted(profiles.System.unique()),
            selected_industries=metadata["selected_industries"], representative_period_weights={p: 2920. for p in periods})
        # Representative-hour activity must close to annual source-calibrated demand.
        totals = {}
        for key, value in result["heat_demand_year"].items():
            detail, period, zone, system, year = key
            target = detail, zone, system, year
            totals[target] = totals.get(target, 0.) + value * 2920.
        for key, expected in result["annual_useful_energy"].items():
            if not math.isclose(totals.get(key, 0.), expected, rel_tol=1e-8, abs_tol=1e-5):
                raise AssertionError(f"Native annual useful-energy closure failed: {key}")
        report = dict(native_adapter_passed=True, sample_periods=periods, years=years,
                      countries=[s["country"] for s in metadata["sources"]],
                      selected_industries=metadata["selected_industries"],
                      annual_component_years=len(result["annual_useful_energy"]),
                      hourly_component_years=len(result["heat_demand_year"]),
                      heat_pump_service_budgets=len(result["hp_service_limits"]),
                      complete_other_sector_bundle_verified=False, optimization_solved=False)
        (generated / "native_adapter_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return report
    finally:
        sys.path.pop(0)
        sys.dont_write_bytecode = old


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--generated", type=Path, required=True)
    args = parser.parse_args()
    verify(args.model_root, args.generated)
