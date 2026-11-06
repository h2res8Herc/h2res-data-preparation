"""Prepare every native technology workbook from one country configuration."""
from __future__ import annotations

from copy import copy
import json
from pathlib import Path
import shutil
from zipfile import BadZipFile
import xml.etree.ElementTree as ET

import pandas as pd


def reusable_complex(directory, *, countries, base_year, efuels, case, template, allocation, sources, sectors, waste):
    """Reuse a compiled alternative only when observations and assumptions match."""
    from model_input_bundle import sha256
    from excel_integrity import workbook_errors
    from industry.fuel_representation import REGULAR_FUEL_METHOD
    metadata = directory / "complex_generation.json"
    if not metadata.is_file():
        return False
    try:
        details = json.loads(metadata.read_text(encoding="utf-8"))
        if (details["base_year"] != base_year or details["efuels"] != efuels
                or (not efuels and details.get("regular_fuel_representation") != REGULAR_FUEL_METHOD)
                or details["electricity_case"] != case or not details["source_reconciliation_passed"]
                or details["inherited_template_sha256"] != sha256(template)
                or set(details["selected_industries"]) != set(sectors)):
            return False
        saved = details["sources"]
        if {s["country"] for s in saved} != set(countries):
            return False
        for source in saved:
            if source["waste_allocation"] != waste or source["files"] != sources[source["country"]]:
                return False
        observed = pd.read_csv(directory / "industry_allocation.csv")
        keys = ["country", "System", "zone", "Industry"]
        expected = allocation[keys + ["weight"]].sort_values(keys).reset_index(drop=True)
        actual = observed[keys + ["weight"]].sort_values(keys).reset_index(drop=True)
        pd.testing.assert_frame_equal(actual, expected, check_dtype=False, atol=1e-12, rtol=1e-12)
        companion = directory / details["complex_workbook"]
        return (all((directory / name).is_file() for name in ("industry_heat.csv", "industry_electricity.csv"))
                and not workbook_errors(companion) and not workbook_errors(directory / "industry_inputs.xlsx"))
    except (OSError, ValueError, KeyError, AssertionError, BadZipFile, ET.ParseError):
        return False


def configurations():
    for efuels in (False, True):
        for mode in ("regular", "categories", "complex"):
            yield efuels, mode, "conservative"
    yield True, "categories", "technical_2050"


def complex_directory(args, efuels, case):
    return args.out_root / "industry" / "model_variants" / ("complex_" + ("efuel_" if efuels else "regular_") + case)


def branch_allocation_weights(industry, mapping, industries):
    records = []
    for country, group in mapping.groupby("country"):
        zones = sorted(group.zone.unique())
        local = industry.loc[industry.zone.isin(zones)]
        for branch in industries:
            capacity = local.loc[local.Industry.eq(branch)].groupby("zone").cap_mw.sum().reindex(zones, fill_value=0.)
            total = float(capacity.sum())
            for zone in zones:
                records.append(dict(country=country, zone=zone, Industry=branch,
                                    weight=float(capacity.loc[zone]) / total if total > 0 else 1. / len(zones),
                                    allocation_basis="prepared_branch_capacity_share" if total > 0 else "assumed_equal_no_prepared_branch_capacity"))
    return pd.DataFrame(records)


def prepare_sources(args, reference):
    """Compile alternate industry methods; export-only never downloads."""
    if not getattr(args, "all_model_variants", False) or "industry" not in args.sectors:
        return
    base = args.out_root / "industry" / "combined"
    expected = [base / f"Industry_data_{fuel}{category}.csv"
                for fuel in ("regular", "efuels") for category in ("", "_heat_categories")]
    if not all(path.is_file() for path in expected):
        if args.export_only:
            raise FileNotFoundError("All H2RES variants require the prepared regular/category industry tables. "
                                    "Run Generate with all native variants enabled first.")
        from generate_all_sector_inputs import run_industry
        alternate = copy(args)
        alternate.industry_mode = "categories"
        common = args.out_root / "_zone_maps" / "zone_map_common.csv"
        print("Preparing regular and temperature-category industry variants", flush=True)
        run_industry(alternate, None if args.spatial_level == "nuts3" else {"common": common})
    from industry.generate_complex_industry_inputs import compile_inputs, allocations, jrc
    from industry.complex_sources import source_files
    from model_input_bundle import selected_complex_workbook, sha256
    mapping = pd.read_csv(args.out_root / "_zone_maps" / "zone_map_common.csv")
    source_root = getattr(args, "industry_source_root", None)
    if source_root and not any(Path(source_root).rglob("JRC-IDEES-2023_Industry_*.xlsx")):
        # Older GUI settings may point at the regular method's 2021 directory.
        # That directory is not a source of the process method's 2023 workbooks.
        print("Complex variants use the JRC-IDEES-2023 source cache; the configured folder has no 2023 Industry workbook.", flush=True)
        source_root = None
    weights = getattr(args, "industry_zone_weights", None)
    regional = getattr(args, "industry_regional_allocation", "require-weights")
    if weights is None and mapping.groupby("country").zone.nunique().gt(1).any() and regional == "require-weights":
        # Use the already prepared branch allocation rather than introduce an
        # independent equal split for the alternate process representation.
        prepared = base / "regional_branch_weights.csv"
        if not prepared.is_file():
            raise ValueError("Complex regional variants require the prepared paper-method industrial facility weights; regenerate Industry")
        weights = args.out_root / "industry" / "model_variants" / "regional_weights.csv"
        weights.parent.mkdir(parents=True, exist_ok=True)
        frame = pd.read_csv(prepared)
        frame.loc[frame.Industry.isin(jrc.SECTORS.values())].to_csv(weights, index=False)
        args.variant_default_assumptions = [dict(file=str(weights), basis="paper-method facility activity shares, including explicitly reported missing-sector density assumptions")]
    allocation = allocations(mapping, args.countries, weights, equal=regional == "equal")
    sectors = list(jrc.SECTORS.values()) if getattr(args, "complex_industry_sectors", "all") == "all" else [
        x.strip() for x in args.complex_industry_sectors.split(",") if x.strip()]
    cache = args.data_root / "industry" / "jrc_idees_2023"
    observations = {}
    for country in args.countries:
        files = source_files(country, cache, Path(source_root) if source_root else None,
                             download=bool(getattr(args, "industry_download", True)) and not args.export_only,
                             refresh=args.refresh_sources and not args.export_only)
        observations[country] = {str(p): sha256(p) for p in files}
    for efuels, case in ((e, c) for e in (False, True) for c in ("conservative", "technical_2050")):
        directory = complex_directory(args, efuels, case)
        if (not args.refresh_sources or args.export_only) and reusable_complex(
            directory, countries=args.countries, base_year=getattr(args, "industry_base_year", 2020),
            efuels=efuels, case=case, template=reference / "data" / selected_complex_workbook(efuels, case),
            allocation=allocation, sources=observations, sectors=sectors,
            waste=getattr(args, "industry_waste_allocation", "sector-blend"),
        ):
            print(f"Reusing reconciled complex industry variant: efuels={efuels}, electricity={case}", flush=True)
            continue
        print(f"Preparing complex industry variant: efuels={efuels}, electricity={case}", flush=True)
        compile_inputs(
            countries=args.countries, mapping=mapping, reference=reference,
            output=directory,
            cache=cache, source_root=source_root,
            download=bool(getattr(args, "industry_download", True)) and not args.export_only,
            refresh=False,
            efuels=efuels, electricity_case=case, base_year=getattr(args, "industry_base_year", 2020),
            zone_weights=weights, regional_allocation=regional,
            selected_sectors=getattr(args, "complex_industry_sectors", "all"),
            waste_allocation=getattr(args, "industry_waste_allocation", "sector-blend"),
        )


def update_workbooks(args, data, common_updates, reference=None):
    from model_input_bundle import (industry_parameters, pooled_industry, read_generated,
                                    replace_sheets, selected_complex_workbook, selected_workbook,
                                    transport_parameters)
    inventory = []
    industry_base = args.out_root / "industry" / "combined"
    heating = {name: frame for name, frame in common_updates.items()
               if name in {"active_zones", "flex_tech_heat", "flex_tech_DH", "thermal_tech",
                           "thermal_tech_DH", "solar_indv", "solar_DH"}}
    for efuels, mode, case in configurations():
        name = selected_workbook(efuels, mode, case)
        path = data / name
        template_path = reference / "data" / name if reference is not None else path
        updates = dict(heating)
        generated_companion = None
        with pd.ExcelFile(template_path) as book:
            if "industry" in args.sectors:
                if mode == "complex":
                    base = complex_directory(args, efuels, case)
                    with pd.ExcelFile(base / "industry_inputs.xlsx") as generated:
                        for sheet in ("Industry_data", "simple_industry", "industry_CC", "industry_heat_stor"):
                            if sheet in generated.sheet_names:
                                updates[sheet] = pd.read_excel(generated, sheet)
                    updates["simple_industry"] = pooled_industry(updates["Industry_data"],read_generated(base/"industry_heat.csv"),
                                                                 pd.read_excel(book,"simple_industry"))
                    generated_companion = base / selected_complex_workbook(efuels, case)
                else:
                    variant = ("efuels" if efuels else "regular") + ("_heat_categories" if mode == "categories" else "")
                    observations = read_generated(industry_base / f"Industry_data_{variant}.csv")
                    updates["Industry_data"] = industry_parameters(observations, pd.read_excel(book, "Industry_data"))
                    profiles = read_generated(industry_base / ("industry_category_profiles.csv" if mode == "categories" else "industry_heat.csv"))
                    updates["simple_industry"] = pooled_industry(updates["Industry_data"], profiles, pd.read_excel(book, "simple_industry"))
            if "transport" in args.sectors:
                fleet, primary = transport_parameters(
                    read_generated(args.out_root / "transport" / "combined" / "transport_all.csv"),
                    pd.read_excel(book, "transport_all"),
                    pd.read_excel(book, "transport_ICE_prim") if efuels else None,
                )
                updates["transport_all"] = fleet
                if efuels:
                    updates["transport_ICE_prim"] = primary
        if generated_companion:
            from industry.generate_complex_industry_inputs import sync_costs
            companion = data / generated_companion.name
            shutil.copy2(generated_companion, companion)
            sync_costs(path, pd.read_excel(companion, "complex_industry"))
            # The technical process companion is selected by the same native
            # complex flex-tech workbook and the model's electricity-case flag.
            technical = complex_directory(args, efuels, "technical_2050") / selected_complex_workbook(efuels, "technical_2050")
            shutil.copy2(technical, data / technical.name)
        replace_sheets(path, updates)
        flags = dict(model_efuel=efuels, model_industry_categories=mode == "categories",
                     model_complex_industry=mode == "complex", model_complex_non_metallic_minerals=mode == "complex",
                     industry_storage=mode == "categories", model_transport_and_industry=True,
                     industry_category_electricity_case=case, industry_complex_electricity_case=case)
        entry = dict(technology_workbook=name, industry_mode=mode, efuels=efuels,
                              industry_electricity_case=case, replaced_sheets=sorted(updates),
                              model_flags=flags,
                              sector_sources={s: "generated" if s in args.sectors else "default model data"
                                              for s in ("power", "industry", "transport", "heating")})
        if mode == "complex":
            entry["complex_workbooks"] = {option: selected_complex_workbook(efuels, option)
                                          for option in ("conservative", "technical_2050")}
            generation = complex_directory(args, efuels, case) / "complex_generation.json"
            if generation.is_file():
                entry["complex_industry_sectors"] = json.loads(generation.read_text(encoding="utf-8"))["selected_industries"]
        inventory.append(entry)
        print(f"Prepared native technology variant: {name}", flush=True)
    return inventory


def apply_variant_investments(data, settings, variants, selected_name, selected_companion=None):
    """Apply the same investment choices across compatible native formats."""
    if not settings or (settings["investment_multiplier"] == 1 and not settings["investment_overrides"]):
        return
    from scenario_config import investment_tables
    from model_input_bundle import replace_sheets, selected_complex_workbook
    eligible = {"cap_inv_lim", "Industry_data", "simple_industry", "industry_CC", "industry_heat_stor", "transport_all",
                "flex_tech", "flex_tech_heat", "flex_tech_DH", "thermal_tech", "thermal_tech_DH", "efuel", "PE_generation",
                "solar_DH", "solar_indv", "solar_stor_DH", "solar_stor_indv"}
    for variant in variants:
        name = variant["technology_workbook"]
        if name == selected_name:
            continue
        with pd.ExcelFile(data / name) as book:
            tables = {sheet: pd.read_excel(book, sheet) for sheet in book.sheet_names if sheet in eligible}
        updated = investment_tables(tables, settings["investment_multiplier"], settings["investment_overrides"])
        changed = {sheet: value for sheet, value in updated.items() if not value.equals(tables[sheet])}
        if changed:
            replace_sheets(data / name, changed)
    if settings["investment_multiplier"] != 1:
        for efuels in (False, True):
            for case in ("conservative", "technical_2050"):
                name = selected_complex_workbook(efuels, case)
                if name == selected_companion:
                    continue
                tables = pd.read_excel(data / name, sheet_name=["complex_industry", "CC"])
                replace_sheets(data / name, investment_tables(tables, settings["investment_multiplier"], []))
