"""Additional renewable-origin constraints for the supplied H2RES builder.

The native RPS and carbon budget do not establish renewable origin across all
sectors. This adapter adds terminal-year restrictions before objective/solve.
"""
from __future__ import annotations

import re

RENEWABLE = {"solar", "wind", "hydro", "biomass", "biogas", "geothermal", "ambientheat",
             "bio_diesel", "bio_gas", "ethanol", "lignin"}
SECONDARY = {"electricity", "h2", "hydrogen", "heat", "dh_heat", "district_heat", "districtheating",
             "e_petrol", "e_diesel", "e_kerosene", "e_methane", "saf", "methanol", "ammonia", "dme"}
NON_ENERGY = {"co2", "n2", "nitrogen", "water", "oxygen", "air", "non_energy", "non_energy_gas", "non_energy_oil"}
NON_RENEWABLE = {"coal", "lignite", "gas", "naturalgas", "oil", "fuel_oil", "diesel", "petrol", "kerosene",
                 "fueloil", "lpg", "bitumen", "waste", "nuclear", "uranium", "hardcoal", "heavyfueloil", "lightfueloil"}


def fuel_kind(raw) -> str:
    name = re.sub(r"[\s-]+", "", str(raw).strip().casefold())
    if name in RENEWABLE:
        return "renewable"
    if name in SECONDARY:
        return "secondary"
    if name in NON_ENERGY:
        return "material"
    if name in NON_RENEWABLE:
        return "nonrenewable"
    raise ValueError(f"RES scenario has no renewable-origin classification for fuel {raw!r}")


def add_renewable_constraints(ns: dict, scenario: dict) -> dict:
    if scenario["preset"] != "res100":
        return {}
    required = {"model_heating", "model_transport_and_industry", "model_efuel"} if scenario["scope"] == "all-energy" else set()
    if any(not ns.get(flag) for flag in required):
        raise ValueError("Whole-energy RES requires heating, industry/transport and e-fuel modeling to be enabled")
    model = ns["ucp"]
    if ns.get("_renewable_scenario_model") is model:
        return ns["renewable_scenario_constraints"]
    target = scenario["target_year"]
    terminal_years = {int(year) for year in ns["years"] if int(year) >= target}
    rows = {}
    if not terminal_years:
        ns["_renewable_scenario_model"] = model
        ns["renewable_scenario_constraints"] = rows
        return rows
    if not ns.get("generation"):
        raise ValueError("Renewable adapter cannot identify the model's generation variables")
    seen = set()

    def block(name, predicate, year_index=-1):
        for key, variable in ns.get(name, {}).items():
            key = key if isinstance(key, tuple) else (key,)
            if int(key[year_index]) in terminal_years and predicate(key):
                identity = (name, key)
                if identity not in seen:
                    seen.add(identity)
                    rows[identity] = model.addConstr(variable == 0, name=f"scenario_RES[{name},{','.join(map(str, key))}]")

    def primary(raw):
        return fuel_kind(raw) == "nonrenewable"

    generation_fuels = ns.get("generator_fuel_type", {})
    def nonrenewable_generator(key):
        asset = key[:3]
        if asset not in generation_fuels:
            raise ValueError(f"Missing generator fuel classification for {asset}")
        return primary(generation_fuels[asset])
    block("generation", nonrenewable_generator)
    block("heat_input", nonrenewable_generator)
    block("generation_H2_steam", lambda key: True)
    block("generation_H2_steam_gas", lambda key: True, -3)
    block("noloadel", lambda key: True, 1)
    # Hydrogen and generic fuel imports have no origin certificate in these
    # inputs. At the target, secondary carriers must be produced internally.
    outside = ("import_outside", "import_outside_H2", "import_zone_system_terminal_outside")
    for name in outside:
        def unverified_import(key):
            carrier = str(key[0]).strip().casefold()
            if scenario["scope"] == "all-energy":
                return carrier not in NON_ENERGY
            return name == "import_outside_H2" or carrier in {"electricity", "h2", "hydrogen"} or key[0] in ns.get("transmission_outside_units_el", [])
        block(name, unverified_import, 1)
    active = set(ns.get("active_zones_system_df_list", {}))
    for name in ("import_zone_system", "import_zone_system_H2", "import_zone_system_terminal"):
        def external_route(key):
            if len(key) != 7:
                raise ValueError(f"Unsupported internal-trade index in {name}: {key}")
            return (key[-4], key[-3]) not in active or (key[-2], key[-1]) not in active
        block(name, external_route, 1)
    if ns.get("include_secc_links"):
        block("import_zone_system_secc", lambda key: (key[1], key[2]) not in active or (key[3], key[4]) not in active, -2)
    # There is no origin tracer for pre-target stored energy. Clear it at the
    # transition boundary, then permit renewable stocks to carry forward.
    for name in ("stat_sto_soc0", "h2_sto_soc0", "veh_sto_soc0", "heat_pump_sto_soc0"):
        block(name, lambda key: int(key[1]) == target, 1)
    block("storage_level0", lambda key: int(key[-1]) == target and key[0] in ns.get("hphs_units", []))
    if scenario["scope"] == "all-energy":
        block("fuel_SOC_0", lambda key: int(key[-1]) == target and fuel_kind(key[0]) != "material")
        block("ind_sto_soc0", lambda key: int(key[-1]) == target)
        block("heat_sto_level0", lambda key: int(key[-1]) == target)
        for name in ("boiler_ind_generation", "boiler_dh_generation"):
            block(name, lambda key: primary(key[1]))
        # These hourly dictionaries are keyed by physical fuel, not equipment.
        for name in ("fuel_industry_hours", "fuel_demand", "fuel_dem", "ICE_energy_transp_primsecc_sum_fuel",
                     "PE_power_tot", "PE_power_CHP_tot", "feedstock_tot", "feedstock_tot1", "feedstock_tot2", "feedstock_tot3"):
            block(name, lambda key: primary(key[0]))
        block("ICE_energy_transp_prim", lambda key: primary(key[0]))
        for name in ("raf_oil_dem", "oil_gas_extraction", "oil_products_gen"):
            block(name, lambda key: True)
        unit_fuels = {}
        mixed_waste_units = set()
        for name in ("Industry_data_model_df", "Industry_data_active_df", "Industry_data_df", "complex_industry_technology_df"):
            table = ns.get(name)
            if table is None or not {"unit_name", "fuel_type"}.issubset(table.columns):
                continue
            for record in table.to_dict("records"):
                unit_fuels[record["unit_name"]] = record["fuel_type"]
                fraction = record.get("fossil_waste_final_energy_share", 0.)
                if fraction is not None and float(fraction) > 0:
                    mixed_waste_units.add(record["unit_name"])
        def fossil_equipment(key):
            if key[0] not in unit_fuels:
                raise ValueError(f"No industry fuel mapping for {key[0]}")
            return primary(unit_fuels[key[0]]) or key[0] in mixed_waste_units
        block("boiler_industry_generation", fossil_equipment)
    ns["_renewable_scenario_model"] = model
    ns["renewable_scenario_constraints"] = rows
    print(f"[RES SCENARIO] {len(rows)} origin/energy constraints for {sorted(terminal_years)}; scope={scenario['scope']}")
    return rows
