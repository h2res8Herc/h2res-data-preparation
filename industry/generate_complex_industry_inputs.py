"""Compile source-calibrated JRC-IDEES processes into native H2RES inputs.

Observations and technology/scenario assumptions have separate provenance.
Historical scripts and the source model are never executed or modified.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
import re
import shutil
import sys
from zipfile import ZipFile
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
from openpyxl import load_workbook
from openpyxl.formula.translate import Translator
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from model_input_bundle import DEFAULT_REFERENCE, replace_sheets, selected_workbook, selected_complex_workbook, sha256, sheet_paths
from h2res_input_schema import annual_limits, validate_limits
from industry.complex_sources import source_files, require_formula_caches, sector_waste_proofs
from industry.methods import jrc_source as jrc, fuel_policy, electricity_policy, heat_pump_policy
from industry.fuel_representation import REGULAR_FUEL_METHOD, regular_complex_aggregate

KEY = ["Industry", "branch", "component"]
HP_COEFFICIENTS = dict(lt100_below60=.5, lt100_below80=.8, heat100_400_below125=.25,
                       heat100_400_below150=.5, source_heat_fraction=.75)
# Positive electrolysis activity is absent from the supplied Croatian calibration.
# This explicit JRC service label is electrical; do not broaden unknown-label guessing.
SOURCE_FUEL_EXTENSIONS = {"Aluminium electrolysis (smelting)": "Electricity"}


def observations(source: Path, components: list[dict]) -> dict:
    book = load_workbook(source, read_only=True, data_only=True)
    nodes = {}
    paths = {}
    try:
        for code in jrc.SECTORS:
            for suffix in ("_ued", "_fec"):
                for node in jrc.read_tree(book[code + suffix]):
                    nodes[code + suffix, node["row"]] = node
                    paths[code + suffix, node["path"]] = node
        result = {}
        for c in components:
            records = []
            for fuel, values in c["fuels"].items():
                for address in values["source_cells"]:
                    sheet, cell = address.split("!")
                    row = int(re.search(r"\d+$", cell).group())
                    node = nodes[sheet, row]
                    records.append(dict(fuel=fuel, useful=node["values"][c["source_year"]],
                                        final=paths[sheet.replace("_ued", "_fec"), node["path"]]["values"][c["source_year"]],
                                        path=" / ".join(node["path"]), kind=fuel_policy.classify(node["path"])))
            result[tuple(c[k] for k in KEY)] = records
        return result
    finally:
        book.close()


def allocations(mapping: pd.DataFrame, countries: list[str], weights_path: Path | None, equal=False):
    weights = pd.read_csv(weights_path) if weights_path else None
    if weights is not None:
        required = {"country", "zone", "Industry", "weight"}
        if not required.issubset(weights):
            raise ValueError("Industry allocation CSV requires country,zone,Industry,weight; Industry='*' applies to all sectors")
        weights["weight"] = pd.to_numeric(weights.weight, errors="raise")
        if not np.isfinite(weights.weight).all() or weights.weight.lt(0).any():
            raise ValueError("Industry allocation weights must be finite and nonnegative")
        if weights.duplicated(["country", "zone", "Industry"]).any():
            raise ValueError("Duplicate industry allocation weights")
        expected = set(map(tuple, mapping[["country", "zone"]].drop_duplicates().values))
        if set(map(tuple, weights[["country", "zone"]].values)) - expected:
            raise ValueError("Industry allocation CSV contains zones outside the selected map")
    result = []
    system = "system_new" if "system_new" in mapping else "country"
    for country in countries:
        zones = mapping.loc[mapping.country.eq(country), [system, "zone"]].drop_duplicates()
        if zones.empty:
            raise ValueError(f"No industry zones selected for {country}")
        for industry in jrc.SECTORS.values():
            block = None
            if weights is not None:
                local = weights.loc[weights.country.eq(country)]
                block = local.loc[local.Industry.eq(industry)]
                if block.empty:
                    block = local.loc[local.Industry.eq("*")]
                if set(block.zone) != set(zones.zone) or not math.isclose(block.weight.sum(), 1., abs_tol=1e-9):
                    raise ValueError(f"Allocation weights must cover every selected zone and sum to one: {country}/{industry}")
            elif len(zones) > 1 and not equal:
                raise ValueError(f"JRC data are national: {country} has {len(zones)} zones. Supply --industry-zone-weights, or explicitly choose --industry-regional-allocation equal")
            for target in zones.itertuples(index=False, name=None):
                result.append(dict(country=country, System=target[0], zone=target[1], Industry=industry,
                                   weight=float(block.loc[block.zone.eq(target[1]), "weight"].iloc[0]) if block is not None else 1. / len(zones),
                                   allocation_basis="user_supplied_weights" if block is not None else "national" if len(zones) == 1 else "assumed_equal_allocation"))
    return pd.DataFrame(result)


def equipment_frames(components, branches, evidence, observed, templates, country, efuels, electricity_case):
    old = templates["complex_industry"]
    exact = {tuple(r[k] for k in KEY + ["unit_name"]): r for r in old.to_dict("records")}
    generic = {unit: block.iloc[0].to_dict() for unit, block in old.groupby("unit_name", sort=False)}
    hp_spec = {r.unit_name: r._asdict() for r in templates["industry_heat_pumps"].itertuples(index=False)}
    technology, process, screening = [], [], []
    for c in components:
        key = tuple(c[k] for k in KEY)
        leaves = observed[key]
        useful = c["useful_ktoe"] * jrc.KTOE_TO_MWH
        output = c["output"]
        shares = {f: v["useful"] / c["useful_ktoe"] for f, v in c["fuels"].items()} if c["useful_ktoe"] > 0 else {"Electricity": 1.}
        fossil = sum(s for f, s in shares.items() if f in {"Coal", "Gas", "fuel_oil", "diesel", "LPG", "heat"})
        options = set(shares)
        if fossil > 0 and not c["feedstock"]:
            options |= {"Electricity", "H2"} | (jrc.SYNTHETIC if efuels else set())
        total = sum(o["useful"] for o in leaves)
        low = sum(o["useful"] for o in leaves if o["kind"] == "common_low_enthalpy_heat") / total if total else float("Low-enthalpy" in c["component"])
        mid = sum(o["useful"] for o in leaves if o["kind"] == "common_steam_or_drying_heat") / total if total else 0.
        hp = heat_pump_policy.hp_eligibility(low, mid, HP_COEFFICIENTS)
        group = []
        for fuel in sorted(options):
            model_fuel = ("Hydrogen" if fuel == "H2" else "Oil" if fuel in {"LPG", "diesel", "fuel_oil"} else fuel) if not efuels else fuel
            unit = jrc.UNITS[fuel]
            parent = exact.get(key + (unit,), generic.get(unit))
            if parent is None:
                raise ValueError(f"No explicit equipment assumption template for {unit}")
            row = parent.copy()
            values = c["fuels"].get(fuel)
            if values and values["final"] > 0:
                efficiency = values["useful"] / values["final"]
                basis = "observed_JRC_useful_to_final_ratio"
            else:
                reference = c["fuels"].get("Gas") or c["fuels"].get("fuel_oil") or next(iter(c["fuels"].values()), None)
                efficiency = 1. if fuel == "Electricity" else min(1., reference["useful"] / reference["final"]) if reference and reference["final"] else 1.
                basis = "assumed_electric_resistance_ratio_1" if fuel == "Electricity" else "assumed_reference_fuel_ratio_bounded_at_1"
            factor = values["co2"] / (values["final"] * jrc.KTOE_TO_MWH) if values and values["final"] else None
            share = shares.get(fuel, 0.)
            maximum = share if c["feedstock"] else min(1., share + fossil) if fuel == "Electricity" else fossil if fuel in jrc.SYNTHETIC else share
            row.update({k: c[k] for k in KEY})
            row.update(System=country, zone=country + "1", unit_name=unit, fuel_type=model_fuel, group=model_fuel,
                       efficiency=efficiency, efficiency_basis=basis, cap_mw=useful * share / 8760.,
                       share_fuel_2020=share, max_share_fuel=maximum, CO2Intensity=jrc.MODEL_CO2.get(model_fuel, 0.),
                       combustion_CO2_t_per_MWh=factor if factor is not None else jrc.MODEL_CO2.get(model_fuel, 0.),
                       observed_CO2_t_per_MWh=factor, source_year=c["source_year"],
                       emission_factor_basis="observed_JRC_final_energy_fuel_blend" if factor is not None else "assumed_existing_model_fuel_factor",
                       service_type="material_feedstock" if c["feedstock"] else "energy_service",
                       fossil_waste_final_energy_share=values.get("fossil_waste_final_energy_share", 0.) if values else 0.,
                       source_waste_split=values.get("waste_split_source") if values else None,
                       source_ued_cells="; ".join(values["source_cells"]) if values else None,
                       source_fec_cells="; ".join(values["final_source_cells"]) if values else None,
                       source_emi_cells="; ".join(values["emissions_source_cells"]) if values else None,
                       source_note="JRC observations recalculated for this country; equipment lifetime, costs, build limits and substitutions are inherited scenario assumptions. Initial MW equals annual useful MWh / 8760, not measured plant capacity. Material feedstocks use the supplied H2-fed convention.")
            group.append(row)
        frame = pd.DataFrame(group)
        bases, pools, _, _ = fuel_policy.service_pools(frame, leaves, "useful")
        for row in group:
            maximum, rule = fuel_policy.ceiling(pd.Series(row), bases, pools, feedstock=c["feedstock"])
            if row["unit_name"] == "Electricity_industry":
                electric, electric_rule, _ = electricity_policy.envelope(c, leaves, row["share_fuel_2020"])
                maximum = electric
                if electricity_case == "technical_2050" and electric_rule not in {"fixed_material", "inactive_placeholder", "reduction_chemistry_retained"}:
                    maximum = 1.
                rule = electric_rule + ":" + electricity_case
            row["max_share_fuel"] = max(row["share_fuel_2020"], min(1., maximum))
            row["include_in_the_model"] = "Y" if row["efficiency"] > 0 and (row["max_share_fuel"] > 0 or row.get("include_in_the_model") == "Y") else "N"
            screening.append({**{k: c[k] for k in KEY}, "unit_name": row["unit_name"], "max_share_fuel": row["max_share_fuel"], "rule": rule})
        for unit, spec in hp_spec.items():
            sink = int(spec["sink_max_C"])
            if hp[sink] <= 1e-12 or c["feedstock"]:
                continue
            parent = exact.get(key + (unit,), generic.get(unit))
            if parent is None:
                raise ValueError(f"Missing heat-pump assumptions: {unit}")
            row = parent.copy()
            row.update({k: c[k] for k in KEY})
            row.update(System=country, zone=country + "1", unit_name=unit, fuel_type="Electricity", group=unit,
                       efficiency=float(spec["COP"]), efficiency_basis="assumed_heat_pump_COP", cap_mw=0., share_fuel_2020=0.,
                       max_share_fuel=hp[sink], include_in_the_model="Y", source_year=c["source_year"],
                       CO2Intensity=0., combustion_CO2_t_per_MWh=0., observed_CO2_t_per_MWh=None,
                       source_ued_cells=None, source_fec_cells=None, source_emi_cells=None, fossil_waste_final_energy_share=0., source_waste_split=None,
                       source_note="Supplied heat-pump COP/cost assumption and cumulative temperature/source eligibility; no observed initial HP capacity.")
            group.append(row)
        technology.extend(group)
        excluded = jrc.historical_h2_reforming_process_co2(c) if country == "HR" else 0.
        intensity = useful / output if output else 0.
        carbon = (c["process_co2"] - excluded) / output if output else 0.
        process.append(dict(System=country, zone=country + "1", **{k: c[k] for k in KEY}, include_in_the_model="Y",
                            activity_unit=c["activity_unit"], activity_factor=1., useful_energy_demand_MWh=useful,
                            energy_intensity_MWh_per_activity=intensity, energy_intensity_MWh_per_t=intensity if c["activity_unit"] == "t_product" else None,
                            process_CO2_t_per_activity=carbon, process_CO2_t_per_t=carbon if c["activity_unit"] == "t_product" else None,
                            historical_process_CO2_t=c["process_co2"], historical_process_CO2_t_per_activity=c["process_co2"] / output if output else 0.,
                            excluded_H2_reforming_CO2_t=excluded, excluded_H2_reforming_CO2_t_per_activity=excluded / output if output else 0.,
                            process_CO2_accounting_basis="historic_ammonia_SMR_represented_by_H2_supply" if excluded else "independent_observed_process_CO2",
                            source_process_CO2_reference=jrc.AMMONIA_INVENTORY_REFERENCE if excluded else None,
                            process_CO2_capturable_share=1. if carbon else 0., product_output_t=output if c["activity_unit"] == "t_product" else None,
                            reference_activity=output, source_process_emi_cells="; ".join(c["process_co2_source_cells"]), source_year=c["source_year"],
                            service_type="material_feedstock" if c["feedstock"] else "energy_service",
                            source_note="Separate observed process emissions, assigned once per branch. Capturable share is an assumption. No HR ammonia adjustment is applied to another country.",
                            technology_limit_basis="Supplied service eligibility coefficients and equipment assumptions",
                            **{heat_pump_policy.HP_FIELDS[k]: v for k, v in hp.items()}))
    capture, products = [], []
    for b in branches:
        matching = templates["CC"].loc[templates["CC"].Industry.eq(b["Industry"]) & templates["CC"].branch.eq(b["branch"])]
        row = (matching.iloc[0] if not matching.empty else templates["CC"].iloc[0]).to_dict()
        row.update(System=country, zone=country + "1", Industry=b["Industry"], branch=b["branch"], CC_cap=0., Reboiler_cap=0., Tank_stor_cap=0., CC_active="Y")
        capture.append(row)
        latest = max(b["activity"])
        products.append(dict(System=country, zone=country + "1", Industry=b["Industry"], branch=b["branch"], product_unit=b["activity_unit"],
                             **{str(y): b["activity"].get(y, b["activity"][latest]) for y in range(2020, 2051)},
                             source_note=f"Observed JRC {b['source_sheet']} row {b['source_output_row']}; activity held constant after {latest}, an editable scenario assumption."))
    return {"complex_industry": annual_limits(pd.DataFrame(technology)), "Process_data": pd.DataFrame(process),
            "CC": pd.DataFrame(capture), "Product_demand": pd.DataFrame(products),
            "JRC_source_cells": pd.DataFrame(evidence).assign(country=country), "Generation_screening": pd.DataFrame(screening)}


def regionalize(frames, allocation, country, prefix=False):
    result = {}
    extensive = {"complex_industry": ["cap_mw"], "CC": ["CC_cap", "Reboiler_cap", "Tank_stor_cap"],
                 "Process_data": ["useful_energy_demand_MWh", "historical_process_CO2_t", "excluded_H2_reforming_CO2_t"]}
    for name, original in frames.items():
        if name not in {"complex_industry", "CC", "Process_data", "Product_demand"}:
            result[name] = original.assign(country=country)
            continue
        chunks = []
        for a in allocation.loc[allocation.country.eq(country)].itertuples(index=False):
            frame = original.loc[original.Industry.eq(a.Industry)].copy()
            frame["System"], frame["zone"] = a.System, a.zone
            frame["source_country"] = country
            frame["allocation_weight"], frame["allocation_basis"] = a.weight, a.allocation_basis
            for field in extensive.get(name, []):
                frame[field] = frame[field] * a.weight
            # National finite investment budgets are apportioned, including exact zero; blanks stay unlimited.
            for field in frame:
                if "max_inv_period" in str(field):
                    frame[field] = frame[field] * a.weight
            if name == "Product_demand":
                physical = frame.product_unit.eq("t_product")
                columns = [col for col in frame if str(col).isdigit()]
                frame[columns] = frame[columns].astype(float)
                frame.loc[physical, columns] = frame.loc[physical, columns] * a.weight
            if name == "Process_data":
                physical = frame.activity_unit.eq("t_product")
                frame[["product_output_t", "reference_activity"]] = frame[["product_output_t", "reference_activity"]].astype(float)
                frame.loc[physical, ["product_output_t", "reference_activity"]] *= a.weight
                index = ~physical
                for field in ["energy_intensity_MWh_per_activity", "process_CO2_t_per_activity", "historical_process_CO2_t_per_activity", "excluded_H2_reforming_CO2_t_per_activity"]:
                    frame[field] = frame[field].astype(float)
                    frame.loc[index, field] *= a.weight
            if prefix:
                for field in ("branch", "component"):
                    if field in frame:
                        frame[field] = country + "__" + frame[field]
            from industry.complex_regional_inputs import zero_weight_activity
            frame,_=zero_weight_activity(frame,name)
            chunks.append(frame)
        result[name] = pd.concat(chunks, ignore_index=True)
    return result


def sync_costs(path: Path, technology: pd.DataFrame) -> list[dict]:
    """Append generic-cost proxies while retaining all existing cells and caches."""
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with ZipFile(path) as archive:
        member = sheet_paths(archive)["tech_cost_years"]
        root = ET.fromstring(archive.read(member))
        rows = root.find(ns + "sheetData").findall(ns + "row")
        shared = ET.fromstring(archive.read("xl/sharedStrings.xml")) if "xl/sharedStrings.xml" in archive.namelist() else None
        strings = ["".join(x.itertext()) for x in shared.findall(ns + "si")] if shared is not None else []
        def value(cell):
            if cell.get("t") == "inlineStr":
                return "".join(cell.find(ns + "is").itertext())
            v = cell.find(ns + "v")
            return strings[int(v.text)] if cell.get("t") == "s" else v.text if v is not None else None
        # Do not rely on contiguous XML cells for source column indexes.
        headers = {value(cell): re.match(r"[A-Z]+", cell.get("r")).group() for cell in rows[0]}
        count = len(headers)
        added = []
        for component, unit in sorted(set(technology[["component", "unit_name"]].itertuples(index=False, name=None))):
            key = f"{component}_{unit}"
            if key in headers:
                continue
            if unit not in headers:
                raise ValueError(f"No generic CAPEX donor for {key}: {unit}")
            donor = headers[unit]
            count += 1
            if count > 16384:
                raise ValueError("Merged process/component costs exceed Excel's 16384-column limit; use separate country zones")
            target = get_column_letter(count)
            for row in rows:
                number = row.get("r")
                source = next((c for c in row if c.get("r") == donor + number), None)
                if source is None:
                    continue
                cell = deepcopy(source)
                cell.set("r", target + number)
                if number == "1":
                    for child in list(cell):
                        cell.remove(child)
                    cell.set("t", "inlineStr")
                    ET.SubElement(ET.SubElement(cell, ns + "is"), ns + "t").text = key
                else:
                    formula = cell.find(ns + "f")
                    if formula is not None and formula.text:
                        formula.text = Translator("=" + formula.text, origin=source.get("r")).translate_formula(cell.get("r"))[1:]
                row.append(cell)
            headers[key] = target
            added.append(dict(component_cost=key, generic_donor=unit, basis="assumed_generic_equipment_cost_proxy"))
        if not added:
            return []
        dimension = root.find(ns + "dimension")
        if dimension is not None:
            dimension.set("ref", f"A1:{get_column_letter(count)}{rows[-1].get('r')}")
        payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        temporary = path.with_suffix(".costs.tmp.xlsx")
        with ZipFile(temporary, "w") as output:
            for info in archive.infolist():
                output.writestr(info, payload if info.filename == member else archive.read(info.filename))
    temporary.replace(path)
    return added


def profiles_and_standard(reference, compiled, allocation, efuels):
    """Derive native aggregate baselines; inherit hourly shapes with explicit provenance."""
    native = pd.read_csv(reference / "industry_heat.csv")
    tech = compiled["complex_industry"]
    process = compiled["Process_data"]
    with pd.ExcelFile(reference / selected_workbook(efuels, "complex")) as book:
        templates = pd.read_excel(book, sheet_name=[s for s in ["Industry_data", "simple_industry", "industry_CC", "industry_heat_stor"] if s in book.sheet_names])
    ordinary, curves, electricity, profile_notes = [], [], [], []
    for (system, zone), local in process.groupby(["System", "zone"], sort=False):
        demand = pd.DataFrame({"period": range(1, 8761), "System": system, "zone": zone})
        el = np.zeros(8760)
        for industry, services in local.groupby("Industry", sort=False):
            countries = set(services.source_country)
            local_tech = tech.loc[tech.System.eq(system) & tech.zone.eq(zone) & tech.Industry.eq(industry)]
            demand[industry] = 0.
            for country in sorted(countries):
                curve = native.loc[native.System.eq(country) & native.zone.eq(country + "1")].sort_values("period")
                if curve.empty:
                    curve = native.loc[native.System.eq(country)].groupby("period", as_index=False).sum(numeric_only=True)
                if industry in curve and len(curve) == 8760 and curve.period.nunique() == 8760 and curve[industry].sum() > 0:
                    shape = curve[industry].to_numpy(float) / curve[industry].sum()
                    basis = "inherited_reference_country_hourly_shape_rescaled_to_JRC_useful_energy"
                else:
                    shape = np.full(8760, 1. / 8760)
                    basis = "assumed_flat_hourly_shape_no_country_reference_profile"
                selected = services.loc[services.source_country.eq(country)]
                demand[industry] += shape * selected.useful_energy_demand_MWh.sum()
                t = local_tech.loc[local_tech.source_country.eq(country)]
                t = t.loc[t.unit_name.eq("Electricity_industry") & t.cap_mw.gt(0)]
                el += shape * (t.cap_mw * 8760 / t.efficiency).sum()
                profile_notes.append(dict(System=system, zone=zone, country=country, Industry=industry, basis=basis))
            total = services.useful_energy_demand_MWh.sum()
            for unit, block in local_tech.groupby("unit_name", sort=False):
                if unit.startswith("HP_industry_"):
                    continue
                template = templates["Industry_data"].loc[templates["Industry_data"].Industry.eq(industry) & templates["Industry_data"].unit_name.eq(unit)]
                row = (template.iloc[0] if not template.empty else block.iloc[0]).to_dict()
                amount = block.cap_mw.sum() * 8760
                final = (block.cap_mw * 8760 / block.efficiency.replace(0, np.nan)).sum()
                row.update(System=system, zone=zone, Industry=industry, unit_name=unit, category="all", include_in_the_model="Y",
                           fuel_type=block.fuel_type.iloc[0], cap_mw=amount / 8760, share_fuel_2020=amount / total if total else 0.,
                           max_share_fuel=max(amount / total if total else 0., float(block.max_share_fuel.max())),
                           efficiency=amount / final if final else float(block.efficiency.iloc[0]),
                           source_note="Aggregate of generated country/zone process observations; scenario equipment parameters inherited from reference.")
                ordinary.append(row)
        curves.append(demand)
        electricity.append(pd.DataFrame({"period": range(1, 8761), zone: el}))
    heat = pd.concat(curves, ignore_index=True)
    el = electricity[0]
    for block in electricity[1:]:
        el = el.merge(block, on="period", validate="one_to_one")
    # All supplied sectors have explicit rows. Native complex replacement removes chosen services.
    # Keep zero-capacity remainder rows to satisfy the native table schema without adding old demand.
    remainder = []
    capture, storage = [], []
    for system, zone in process[["System", "zone"]].drop_duplicates().itertuples(index=False, name=None):
        frame = templates["simple_industry"].loc[templates["simple_industry"].zone.eq("HR1")].copy()
        frame["System"], frame["zone"] = system, zone
        frame["cap_mw"], frame["share_fuel_2020"] = 0., 0.
        remainder.append(frame)
        for name, target in [("industry_CC", capture), ("industry_heat_stor", storage)]:
            if name not in templates:
                continue
            frame = templates[name].loc[templates[name].zone.eq("HR1")].copy()
            frame["System"], frame["zone"] = system, zone
            for column in frame:
                if column in {"CC_cap", "Reboiler_cap", "Tank_stor_cap", "cap_mw", "stor_cap"}:
                    frame[column] = 0.
            target.append(frame)
    ordinary = pd.DataFrame(ordinary)
    fuel_notes = []
    if not efuels:
        ordinary, fuel_notes = regular_complex_aggregate(ordinary, templates["Industry_data"])
    # Every aggregate service has explicit detailed equipment. An empty, typed
    # simple sheet is correct here; zero-filled dummy remainder assets have no
    # corresponding demand key in the native reader.
    updates = {"Industry_data": annual_limits(ordinary), "simple_industry": pd.concat(remainder, ignore_index=True).iloc[:0].copy()}
    updates["Industry_data"].attrs["fuel_redistribution"] = fuel_notes
    if capture:
        updates["industry_CC"] = pd.concat(capture, ignore_index=True)
    if storage:
        updates["industry_heat_stor"] = pd.concat(storage, ignore_index=True)
    return updates, heat, el, profile_notes


def reconcile(frames, components, country):
    records = []
    tech = frames["complex_industry"]
    process = frames["Process_data"]
    for industry in jrc.SECTORS.values():
        original = [c for c in components if c["Industry"] == industry]
        t = tech.loc[tech.Industry.eq(industry)]
        p = process.loc[process.Industry.eq(industry)]
        measures = {
            "useful_MWh": (sum(c["useful_ktoe"] * jrc.KTOE_TO_MWH for c in original), t.cap_mw.sum() * 8760),
            "final_MWh": (sum(v["final"] * jrc.KTOE_TO_MWH for c in original for v in c["fuels"].values()), (t.cap_mw * 8760 / t.efficiency.replace(0, np.nan)).sum()),
            "combustion_CO2_t": (sum(v["co2"] for c in original for v in c["fuels"].values()), (t.cap_mw * 8760 / t.efficiency.replace(0, np.nan) * t.combustion_CO2_t_per_MWh).sum()),
            "historical_process_CO2_t": (sum(c["process_co2"] for c in original), p.historical_process_CO2_t.sum()),
        }
        for measure, (expected, actual) in measures.items():
            passed = math.isclose(expected, actual, rel_tol=1e-8, abs_tol=1e-5)
            records.append(dict(country=country, Industry=industry, measure=measure, source=float(expected), generated=float(actual), passed=passed))
            if not passed:
                raise ValueError(f"JRC reconciliation failed: {records[-1]}")
    return records


def compile_inputs(*, countries, mapping, reference, output, cache, source_root=None, download=True, refresh=False,
                   efuels=False, electricity_case="conservative", base_year=2020, zone_weights=None, regional_allocation="require-weights",
                   selected_sectors="all", waste_allocation="sector-blend"):
    reference, output = Path(reference).resolve(), Path(output).resolve()
    if reference.name != "data":
        reference = reference / "data"
    if output == reference or reference in output.parents:
        raise ValueError("Generated inputs must be outside the reference directory")
    allocation = allocations(mapping, countries, zone_weights, equal=regional_allocation == "equal")
    if allocation.groupby("zone").System.nunique().gt(1).any():
        raise ValueError("Model zone names must be unique across systems; assign distinct zone names or a shared system_new")
    selected = list(jrc.SECTORS.values()) if selected_sectors == "all" else [s.strip() for s in selected_sectors.split(",") if s.strip()]
    if not selected or set(selected) - set(jrc.SECTORS.values()):
        raise ValueError("Complex sector selection must be 'all' or comma-separated native JRC Industry labels")
    name = selected_complex_workbook(efuels, electricity_case)
    template_path = reference / name
    templates = pd.read_excel(template_path, sheet_name=None)
    # Each run replaces only the staged output; unrelated workbook members are preserved.
    output.mkdir(parents=True, exist_ok=True)
    normalized = output / "normalized"
    normalized.mkdir(exist_ok=True)
    all_frames, sources, totals = [], [], []
    merged = mapping.groupby("zone").country.nunique().gt(1).any()
    for country in countries:
        files = source_files(country, Path(cache), Path(source_root) if source_root else None, download=download, refresh=refresh)
        for path in files:
            require_formula_caches(path)
        old_year, old_fuels = jrc.BASE_YEAR, jrc.FUELS.copy()
        waste_proof, waste_notes = sector_waste_proofs(files[0], waste_allocation)
        try:
            jrc.BASE_YEAR = base_year
            jrc.FUELS.update(SOURCE_FUEL_EXTENSIONS)
            components, branches, evidence = jrc.extract_source(files[0], waste_proof_by_sector=waste_proof)
        finally:
            jrc.BASE_YEAR = old_year
            jrc.FUELS.clear()
            jrc.FUELS.update(old_fuels)
        if any(base_year not in b["activity"] for b in branches):
            raise ValueError(f"Base year {base_year} is absent from JRC observations for {country}")
        for c in components:
            values = [c["useful_ktoe"], c["output"], c["process_co2"]] + [v[k] for v in c["fuels"].values() for k in ("useful", "final", "co2")]
            if any(not math.isfinite(v) or v < 0 for v in values):
                raise ValueError(f"Invalid source observation for {country}/{c['component']}: finite nonnegative energy, activity and CO2 required")
        observed = observations(files[0], components)
        (normalized / f"{country}_components.json").write_text(json.dumps(components, indent=2), encoding="utf-8")
        (normalized / f"{country}_branches.json").write_text(json.dumps(branches, indent=2), encoding="utf-8")
        pd.DataFrame(evidence).to_csv(normalized / f"{country}_fuel_observations.csv", index=False)
        frames = equipment_frames(components, branches, evidence, observed, templates, country, efuels, electricity_case)
        regional = regionalize(frames, allocation, country, prefix=merged)
        totals.extend(reconcile(regional, components, country))
        for frame in regional.values():
            validate_limits(frame)
        all_frames.append(regional)
        sources.append(dict(country=country, files={str(p): sha256(p) for p in files}, components=len(components), branches=len(branches), fuel_observations=len(evidence),
                            waste_allocation=waste_allocation, sector_waste_blend_assumptions=waste_notes,
                            reference_year_fallbacks=[{k: c[k] for k in KEY + ["source_year"]} for c in components if c["source_year"] != base_year]))
        print(f"{country}: compiled {len(components)} components, {len(branches)} branches; energy and CO2 reconcile", flush=True)
    compiled = {key: pd.concat([f[key] for f in all_frames], ignore_index=True) for key in all_frames[0]}
    # Audit tables describing the original HR-only migrations are not presented as new country calculations.
    stale = {"industry_share_limits_20261030", "process_elec_limits_20261031", "fuel_compatibility_20261031"}
    workbook_frames = {key: value for key, value in templates.items() if key not in stale}
    workbook_frames.update(compiled)
    workbook_frames["Methodology"] = pd.DataFrame([
        dict(item="Source", value="JRC-IDEES-2023 country Industry/EnergyBalance/EmissionBalance workbooks; SHA256 and exact cells in generation.json and normalized records"),
        dict(item="Equipment assumptions", value="Supplied handoff costs/lifetimes/build limits; pure service compatibility, electrification and cumulative HP screening methods. Not observed plant MW or technology forecasts."),
        dict(item="Base calibration", value=f"Requested observation year {base_year}; zero-output branches use the last positive source year. Explicit fallbacks are recorded."),
        dict(item="Future activity", value="Observed activity through 2023, then latest activity held constant through 2050; editable scenario assumption."),
        dict(item="Feedstocks and carbon", value="Supplied H2-fed material convention. Observed combustion and process emissions separate. HR ammonia exception restricted to exact HR observation; other countries retain process emissions and require their own evidence to reclassify H2-reforming emissions."),
        dict(item="Hourly allocation", value="Country reference industry shapes rescaled to JRC useful energy; flat shape explicitly recorded where unavailable. Regional weights are assumptions unless supplied with evidence."),
        dict(item="Heat pumps", value=json.dumps(HP_COEFFICIENTS)),
    ])
    with pd.ExcelWriter(output / name, engine="openpyxl") as writer:
        for sheet, frame in workbook_frames.items():
            frame.to_excel(writer, sheet_name=sheet, index=False)
    updates, heat, electricity, profile_notes = profiles_and_standard(reference, compiled, allocation, efuels)
    fuel_notes = updates["Industry_data"].attrs.get("fuel_redistribution", [])
    (output / "fuel_redistribution.json").write_text(json.dumps(fuel_notes, indent=2), encoding="utf-8")
    flex = output / "industry_inputs.xlsx"
    shutil.copy2(reference / selected_workbook(efuels, "complex"), flex)
    replace_sheets(flex, updates)
    costs = sync_costs(flex, compiled["complex_industry"])
    heat.to_csv(output / "industry_heat.csv", index=False, float_format="%.12g")
    electricity.to_csv(output / "industry_electricity.csv", index=False, float_format="%.12g")
    allocation.to_csv(output / "industry_allocation.csv", index=False)
    pd.DataFrame(totals).to_csv(output / "source_reconciliation.csv", index=False)
    # Match the original HR calibration by stable keys, independently of Excel row order.
    comparison = []
    if countries == ["HR"] and not merged and set(allocation.zone) == {"HR1"}:
        keys = ["System", "zone"] + KEY + ["unit_name"]
        old = templates["complex_industry"].set_index(keys)
        new = compiled["complex_industry"].set_index(keys)
        for key in old.index.union(new.index):
            if key not in old.index or key not in new.index:
                comparison.append(dict(zip(keys, key), field="row", old="present" if key in old.index else "absent", new="present" if key in new.index else "absent"))
                continue
            for field in ["cap_mw", "efficiency", "share_fuel_2020", "max_share_fuel", "combustion_CO2_t_per_MWh", "max_inv_period"]:
                a, b = old.at[key, field], new.at[key, field]
                if not (pd.isna(a) and pd.isna(b)) and not math.isclose(float(a), float(b), rel_tol=1e-10, abs_tol=1e-10):
                    comparison.append(dict(zip(keys, key), field=field, old=a, new=b))
        pd.DataFrame(comparison, columns=keys + ["field", "old", "new"]).to_csv(output / "reference_calibration_diff.csv", index=False)
    metadata = dict(method="supplied_JRC_process_tree_and_service_compatibility", base_year=base_year, sources=sources,
                    regular_fuel_representation=REGULAR_FUEL_METHOD if not efuels else "native_efuel_fuels",
                    regular_fuel_redistribution=fuel_notes,
                    explicit_source_fuel_extensions=SOURCE_FUEL_EXTENSIONS,
                    selected_industries=selected, efuels=efuels, electricity_case=electricity_case, complex_workbook=name,
                    geography=allocation[["System", "zone"]].drop_duplicates().to_dict("records"),
                    inherited_template=str(template_path), inherited_template_sha256=sha256(template_path),
                    appended_cost_proxies=costs, hourly_profiles=profile_notes,
                    reference_calibration_comparison_performed=countries == ["HR"] and not merged and set(allocation.zone) == {"HR1"},
                    reference_calibration_differences=len(comparison) if countries == ["HR"] and not merged and set(allocation.zone) == {"HR1"} else None,
                    source_reconciliation_passed=all(r["passed"] for r in totals), optimization_solved=False,
                    limitations=["Costs, technology substitutions, build limits, future activity and hourly/regional allocation are assumptions.",
                                 "Non-HR ammonia process emissions are preserved; an H2-supply reclassification requires country-specific evidence.",
                                 "Waste splits use exact single-class evidence where available; otherwise the selected sector-blend mode assumes the observed sector mix applies to its processes. Strict mode rejects ambiguous splits."])
    (output / "complex_generation.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--countries", default="HR")
    parser.add_argument("--zone-map", type=Path, help="Shared country,nuts3,zone[,system_new] CSV; omitted means national zones")
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs_all/industry/combined")
    parser.add_argument("--cache", type=Path, default=ROOT / "data_all/industry/jrc_idees_2023")
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--download", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--efuels", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--electricity-case", choices=("conservative", "technical_2050"), default="conservative")
    parser.add_argument("--base-year", type=int, default=2020)
    parser.add_argument("--zone-weights", type=Path)
    parser.add_argument("--regional-allocation", choices=("require-weights", "equal"), default="require-weights")
    parser.add_argument("--selected-sectors", default="all")
    parser.add_argument("--waste-allocation", choices=("strict", "sector-blend"), default="sector-blend")
    args = parser.parse_args()
    countries = [c.strip().upper() for c in args.countries.split(",") if c.strip()]
    mapping = pd.read_csv(args.zone_map) if args.zone_map else pd.DataFrame([dict(country=c, zone=c + "1") for c in countries])
    compile_inputs(countries=countries, mapping=mapping, reference=args.reference, output=args.output, cache=args.cache,
                   source_root=args.source_root, download=args.download, refresh=args.refresh, efuels=args.efuels,
                   electricity_case=args.electricity_case, base_year=args.base_year, zone_weights=args.zone_weights,
                   regional_allocation=args.regional_allocation, selected_sectors=args.selected_sectors, waste_allocation=args.waste_allocation)


if __name__ == "__main__":
    main()
