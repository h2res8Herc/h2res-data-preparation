"""Run the supplied heat calculator with the paper's regional weather method."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import geopandas as gpd
import numpy as np
import pandas as pd
from heating.paper_weather import regional_hdd


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--calculator", type=Path, required=True)
    parser.add_argument("--weather-points", type=int, default=8)
    parser.add_argument("--weather-seed", type=int, default=0)
    options, remaining = parser.parse_known_args()
    def argument(name):
        return remaining[remaining.index(name) + 1]
    output = Path(argument("--outdir"))
    output.mkdir(parents=True, exist_ok=True)
    nuts = gpd.read_file(argument("--nuts3-geojson"))
    country = argument("--country")
    nuts = nuts.loc[nuts.CNTR_CODE.eq(country)]
    population = Path(argument("--pop-tif"))
    spec = importlib.util.spec_from_file_location("paper_heat_calculator", options.calculator)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    source = options.calculator.read_text(encoding="utf-8")
    old = '"electric_heater": None,\n        "heat_pump": None,'
    if source.count(old) != 1:
        raise ValueError("The supplied heating calculator's electric-fuel adapter needs review")
    source = source.replace(old, '"electric_heater": "m_electricity",\n        "heat_pump": "m_electricity",', 1)
    exec(compile(source, str(options.calculator), "exec"), module.__dict__)
    method = dict(method_id="paper_heating_v1", weather_points=options.weather_points,
                  weather_seed=options.weather_seed, weather_method="random inhabited grid cells with population weights",
                  district_heating_chp_used=False)
    def compute(pop_df, era5_path, year, base_temp_c, alpha_temp, beta_pop, verbose=False):
        return regional_hdd(pop_df, nuts, population, era5_path, year, base_temp_c,
                            alpha_temp, beta_pop, module.open_era5_t2m_series,
                            count=options.weather_points, seed=options.weather_seed, output=output)
    module.compute_base_weights_pop_hdd = compute
    def fuel_modifiers(nuts3_gdf_3035, eigl_dir, gamma_eigl, verbose=False):
        patterns = dict(gas="gas", oil="oil", coal="solid", biomass="renewables", electricity="electricity")
        values = {}
        for fuel, prefix in patterns.items():
            path = Path(eigl_dir) / f"{prefix}_oth_demand_2019.tif"
            if not path.is_file():
                raise FileNotFoundError(f"Heating fuel prevalence source is missing: {path}")
            values[fuel] = np.power(np.maximum(module.zonal_sum_raster(str(path), list(nuts3_gdf_3035.geometry),
                                                        nodata_values=(0.,-9999.)), 0.) + 1e-12, gamma_eigl)
        denominator = np.sum(list(values.values()), axis=0)
        result = pd.DataFrame(dict(nuts3_id=nuts3_gdf_3035.NUTS_ID.to_numpy()))
        for fuel, value in values.items():
            result["m_" + fuel] = value / denominator
        method["fuel_prevalence_sources"] = list(patterns)
        return result
    module.build_region_fuel_share_modifiers = fuel_modifiers
    original_chp = module.compute_chp_weights_by_nuts3
    def chp(*args, **kwargs):
        values = original_chp(*args, **kwargs)
        geography = kwargs.get("nuts3_gdf_4326", args[0] if args else None)
        method["district_heating_chp_used"] = bool(sum(values) > 0)
        method["district_heating_chp_weights"] = dict(zip(geography.NUTS_ID, map(float, values)))
        return values
    module.compute_chp_weights_by_nuts3 = chp
    sys.argv = [str(options.calculator), *remaining]
    module.main()
    (output / "paper_method_details.json").write_text(json.dumps(method, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
