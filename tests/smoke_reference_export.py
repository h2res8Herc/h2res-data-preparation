"""Exercise industry/transport regeneration offline with real reference schemas.

This is an interface test, not a new statistical calibration. It feeds a copy
of reference capacities through the generator and keeps the result separate
from the delivered baseline inputs.
"""
from pathlib import Path
import sys
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd
from generate_all_sector_inputs import build_parser
from model_input_bundle import DEFAULT_REFERENCE, export_bundle


def main():
    output = ROOT / "validation" / "generated_smoke"
    combined = output / "industry" / "combined"
    combined.mkdir(parents=True, exist_ok=True)
    reference = DEFAULT_REFERENCE / "data"
    workbook = reference / "flex_tech_efuel_categories_electricity_review.xlsx"
    source = pd.read_excel(workbook, "Industry_data")
    source = source.loc[source.zone.eq("HR1") & ~source.unit_name.str.startswith("HP_industry_", na=False)].copy()
    source["Industry"] = source.Industry + " [" + source.category + "]"
    units = combined / "industry_units_by_category_ALL_NON_ENERGY.csv"
    source.to_csv(units, index=False)
    profiles = pd.read_csv(reference / "industry_category_profiles.csv")
    profiles = profiles.loc[profiles.System.eq("HR") & profiles.zone.eq("HR1")]
    hourly = combined / "industry_hourly_distributions_by_category_ALL_NON_ENERGY.csv"
    profiles.to_csv(hourly, index=False)
    spec = importlib.util.spec_from_file_location("industry_smoke", ROOT / "industry/generate_industry_inputs_standalone.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.write_industry_variants(units, combined, True)
    module.write_demand_views(hourly, combined)
    transport_dir = output / "transport" / "combined"
    transport_dir.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location("transport_smoke", ROOT / "transport/script/generate_transport_inputs_standalone.py")
    transport = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transport)
    fleet = pd.read_excel(workbook, "transport_all")
    fleet = fleet.loc[fleet.zone.eq("HR1") & fleet.compat_parent.isna(), transport.FINAL_COLUMNS]
    ready = transport.model_ready(fleet)
    ready.to_csv(transport_dir / "transport_all.csv", index=False)
    transport.transport_ice_prim(ready).to_csv(transport_dir / "transport_ICE_prim.csv", index=False)
    for key, name in zip(("activity", "plugin", "v2g"), transport.CURVE_FILES):
        (transport_dir / name).write_bytes(transport.embedded_bytes(key))
    transport.write_distribution_curves(transport_dir, transport_dir)
    transport.write_model_curves(ready, transport_dir)
    args = build_parser().parse_args(["--countries", "HR", "--sectors", "industry,transport", "--spatial-level", "country",
                                      "--efuels", "--industry-mode", "categories", "--out-root", str(output),
                                      "--require-model-ready"])
    report = export_bundle(args, DEFAULT_REFERENCE)
    assert report["ready"], report


if __name__ == "__main__":
    main()
