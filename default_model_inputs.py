"""Extend supplied assumptions to requested geography, with explicit provenance.

Generated observations are never repaired with reference observations here.
Only files/sheets retained as defaults may receive missing geography rows.
"""
from pathlib import Path

import pandas as pd


QUANTITIES = {
    "capacity", "cap_mw", "cap_mwh", "cap_twh", "stor_cap_twh", "stor_cap",
    "heat_storage_cap", "cc_cap", "reboiler_cap", "tank_stor_cap", "max_cap",
    "max_cap_twh", "max_cap_period", "max_cap_period_twh", "max_inv_period",
    "max_new_twh_per_year", "max_gen_aval_twh", "base_year_demand_twh",
    "gen2020", "import2020", "export2020", "total_load", "number",
    "target_twh", "annual_heat_mwh", "annual_demand_mwh", "excluded_heat_mwh",
}


def quantity_columns(frame, sheet=None):
    annual_totals = sheet in {"NH3_demand", "max_inv_EV"}
    return [c for c in frame if str(c).lower() in QUANTITIES
            or str(c).lower().startswith("max_inv_period_")
            or (annual_totals and str(c).isdigit())]


def allocation_weights(data, targets, *, with_basis=False):
    """Demand shares for unsourced defaults, with optional per-country provenance.

    A sector needs positive demand in the requested geography, not merely a
    table on disk. Otherwise electricity supplies the explicit allocation proxy.
    """
    totals = {}
    for kind, names in {
        "electricity": ("electricity_demand.csv",),
        "heating": ("heating_individual.csv", "heating_district.csv"),
        "industry": ("industry_heat.csv",),
    }.items():
        values = {pair: 0. for pair in targets}
        found = False
        for name in names:
            path = data / name
            if not path.is_file():
                continue
            frame = pd.read_csv(path)
            if {"System", "zone", "all"}.issubset(frame):
                annual = frame.groupby(["System", "zone"])["all"].sum()
                values = {pair: values[pair] + float(annual.get(pair, 0.)) for pair in targets}
                found = True
            elif {"System", "Zone", "Power"}.issubset(frame):
                annual = frame.groupby(["System", "Zone"])["Power"].sum()
                values = {pair: values[pair] + float(annual.get(pair, 0.)) for pair in targets}
                found = True
            elif "period" in frame:
                for pair in targets:
                    if pair[1] in frame:
                        values[pair] += float(pd.to_numeric(frame[pair[1]], errors="raise").sum())
                        found = True
        if found:
            totals[kind] = values
    result, bases = {}, {}
    for kind in ("electricity", "heating", "industry"):
        weights, basis = {}, {}
        for system in {pair[0] for pair in targets}:
            pairs = sorted(pair for pair in targets if pair[0] == system)
            values = totals.get(kind, {})
            total = sum(values.get(pair, 0.) for pair in pairs)
            source = f"prepared {kind} demand"
            # A retained national reference table may exist without covering
            # any requested regional zones. Its presence is not evidence of
            # usable regional weights. Fall back per country, just as when
            # the sector table is absent, and retain zero-demand zone shares.
            if total <= 0 and kind != "electricity":
                values = totals.get("electricity", {})
                total = sum(values.get(pair, 0.) for pair in pairs)
                source = (f"prepared electricity demand (fallback: no positive {kind} "
                          "demand for the requested country/zones)")
            if total > 0:
                weights.update({pair: values.get(pair, 0.) / total for pair in pairs})
                basis.update({pair: source for pair in pairs})
            elif len(pairs) == 1:
                weights[pairs[0]] = 1.
                basis[pairs[0]] = "single model zone; no regional subdivision"
        result[kind] = weights
        bases[kind] = basis
    return (result, bases) if with_basis else result


def default_rows(frame, targets, *, weights=None, quantities=(), weight_basis=None):
    system = next((c for c in frame if str(c).lower() == "system"), None)
    zone = next((c for c in frame if str(c).lower() == "zone"), None)
    if system is None or frame.empty:
        return frame, []
    if frame[system].dropna().empty or (zone and frame[zone].dropna().empty):
        return frame, []
    additions, notes = [], []
    requested = sorted(targets) if zone else [(system, None) for system in sorted({pair[0] for pair in targets})]
    for target_system, target_zone in requested:
        matching = frame[system].eq(target_system)
        if zone:
            matching &= frame[zone].eq(target_zone)
        if matching.any():
            continue
        donors = frame.loc[frame[system].eq(target_system)]
        if donors.empty:
            donors = frame.loc[frame[system].eq("HR")]
        if donors.empty:
            donors = frame.loc[frame[system].eq(frame[system].dropna().iloc[0])]
        if zone:
            national = donors.loc[donors[zone].eq(str(donors[system].iloc[0]) + "1")]
            donors = national if not national.empty else donors.loc[donors[zone].eq(donors[zone].dropna().iloc[0])]
        extra = donors.copy()
        extra[system] = target_system
        if zone:
            extra[zone] = target_zone
        fields = [c for c in quantities if c in extra] if zone else []
        share = None
        # A national donor is a total, not a full stock in every county. Existing
        # regional observations are retained; only newly cloned defaults change.
        if fields and weights is not None:
            pair = (target_system, target_zone)
            if pair not in weights:
                raise ValueError(f"No prepared regional demand weights for default quantities in {pair}")
            share = weights[pair]
            for column in fields:
                extra[column] = pd.to_numeric(extra[column], errors="raise") * share
        additions.append(extra)
        notes.append(dict(System=target_system, zone=target_zone if zone else None,
                          donor_system=str(donors[system].iloc[0]),
                          donor_zone=str(donors[zone].iloc[0]) if zone else None,
                          basis=("national default allocated with prepared demand shares; not a sourced observation"
                                 if share is not None else "unchanged supplied default; not a sourced observation"),
                          rows=len(extra), allocated_quantity_columns=fields if share is not None else [],
                          allocation_weight=share,
                          weight_basis=(weight_basis.get((target_system, target_zone))
                                        if isinstance(weight_basis, dict) else weight_basis)))
    return (pd.concat([frame, *additions], ignore_index=True) if additions else frame), notes


def complete_defaults(data: Path, targets, generated_files, variants, selected_name, selected_sheets):
    # The supplied model's reference calibration already covers this geography.
    if not targets or targets == {("HR", "HR1")}:
        return []
    from model_input_bundle import pooled_industry, replace_sheets, write_csv
    notes = []
    generated = set(generated_files)
    regional, regional_basis = allocation_weights(data, targets, with_basis=True)
    annual_industry_profiles = {}
    unit_aliases = {}
    for path in data.glob("*.csv"):
        if path.name in generated or path.name in {"renewable_availability.csv", "hydro_inflows.csv", "literature_fixed_opex.csv",
                                                  "outside_system_supply_shares.csv", "outside_system_normalized_curves.csv"}:
            continue
        frame = pd.read_csv(path)
        quantities = quantity_columns(frame)
        if path.name in {"industry_heat.csv", "industry_category_profiles.csv"}:
            # These long-format values are hourly MW, not normalized shapes.
            # Allocating default equipment without allocating its heat demand
            # would repeat the full national industrial service in every zone.
            quantities = [c for c in frame if c not in {"System", "zone", "period"}]
        updated, changes = default_rows(frame, targets, weights=regional["electricity"],
                                        quantities=quantities, weight_basis=regional_basis["electricity"])
        if path.name == "generators.csv" and changes:
            old_length = len(frame)
            for index in range(old_length, len(updated)):
                old_name = str(updated.at[index, "unit_name"])
                name = str(updated.at[index, "Zone"]) + "__" + old_name
                updated.at[index, "unit_name"] = name
                unit_aliases[name] = old_name
        wide = {"co2_demand.csv", "nh3_demand.csv", "cooling_individual.csv", "cooling_district.csv",
                "heating_individual.csv", "heating_district.csv", "heating_electricity.csv",
                "industry_electricity.csv", "solar_thermal_availability.csv"}
        if path.name in wide or path.name == "electricity_prices.csv":
            for system, zone in sorted(targets):
                column = system if path.name == "electricity_prices.csv" else zone
                if column in updated:
                    continue
                candidates = [system + "1", "HR1", "HR"]
                donor = next((c for c in candidates if c in updated), None)
                if donor is None:
                    raise ValueError(f"No supplied default distribution donor for {path.name}/{column}")
                absolute = path.name in {"cooling_individual.csv", "cooling_district.csv", "heating_individual.csv",
                                         "heating_district.csv", "heating_electricity.csv", "industry_electricity.csv"}
                share = regional["electricity"].get((system, zone)) if absolute else 1.
                if share is None:
                    raise ValueError(f"No regional demand weight for default {path.name}/{zone}")
                updated[column] = updated[donor] * share
                changes.append(dict(column=column, donor_column=donor, allocation_weight=share,
                                    weight_basis=regional_basis["electricity"].get((system, zone)) if absolute else None,
                                    basis="national absolute hourly default allocated with demand shares" if absolute
                                          else "shared normalized profile or intensive hourly assumption"))
        if changes:
            write_csv(updated, path)
            notes.extend(dict(file=path.name, **change) for change in changes)
    for name in ("renewable_availability.csv", "hydro_inflows.csv"):
        if unit_aliases and name not in generated:
            frame = pd.read_csv(data / name)
            for unit, donor in unit_aliases.items():
                if donor in frame:
                    frame[unit] = frame[donor]
                    notes.append(dict(file=name, column=unit, donor_column=donor, basis="supplied default generator profile"))
            write_csv(frame, data / name)
    for path in data.rglob("*.xlsx"):
        if "sources" in path.relative_to(data).parts:
            continue
        name = path.relative_to(data).as_posix()
        entry = next((v for v in variants if v["technology_workbook"] == name), None)
        exclude = set(entry["replaced_sheets"]) if entry else set(selected_sheets) if name == selected_name else set()
        # Inland transport adds technology columns to the template cost table.
        # Its system/year rows still need the normal regional default expansion.
        exclude.discard("tech_cost_years")
        if path.name.startswith("industry_complex") and path.name in generated:
            continue
        patches = {}
        with pd.ExcelFile(path) as book:
            for sheet in book.sheet_names:
                if sheet in exclude:
                    continue
                if path.name in {'policy.xlsx','policy_efuel.xlsx'} and sheet in {'generation_targets','hydro_caps','biomass_caps','outside_trade'}:
                    # Native Zone='*' expresses national annual totals. These
                    # are scoped explicitly by policy_input_links, not cloned.
                    continue
                headers = next(book.book[sheet].iter_rows(min_row=1, max_row=1, values_only=True), ())
                if not any(str(value).lower() == "system" for value in headers):
                    continue
                frame = pd.read_excel(book, sheet)
                kind = ("industry" if sheet.startswith("industry") or sheet == "NH3_demand" else
                        "heating" if sheet.startswith(("solar_", "thermal_", "flex_tech_heat", "flex_tech_DH"))
                        else "electricity")
                try:
                    updated, changes = default_rows(frame, targets, weights=regional[kind],
                                                    quantities=quantity_columns(frame, sheet),
                                                    weight_basis=regional_basis[kind])
                except ValueError as exc:
                    raise ValueError(f"Cannot apply regional defaults in {name}/{sheet}: {exc}") from exc
                if changes:
                    patches[sheet] = updated
                    notes.extend(dict(file=name, sheet=sheet, **change) for change in changes)
            if (path.name.startswith("flex_tech") and "Industry_data" not in exclude
                    and {"Industry_data", "simple_industry"}.issubset(book.sheet_names)):
                # Retained source/default sheets can change independently
                # during regional expansion. The remainder is derived from
                # final service flags/stocks; it is never a separately cloned
                # national stock. Generated variants already pool using their
                # own source-specific profiles and must not be overwritten.
                profile_name = ("industry_category_profiles.csv" if "categories" in path.stem
                                else "industry_heat.csv")
                if profile_name not in annual_industry_profiles:
                    profiles = pd.read_csv(data / profile_name)
                    annual_industry_profiles[profile_name] = profiles.groupby(
                        ["System", "zone"], as_index=False).sum(numeric_only=True)
                industry = patches.get("Industry_data")
                if industry is None:
                    industry = pd.read_excel(book, "Industry_data")
                industry = industry.dropna(subset=["Industry", "unit_name"]).copy()
                if "category" not in industry:
                    industry["category"] = "all"
                simple = pd.read_excel(book, "simple_industry")
                patches["simple_industry"] = pooled_industry(
                    industry, annual_industry_profiles[profile_name], simple)
                notes.append(dict(file=name, sheet="simple_industry",
                                  basis="recomputed from final regional Industry_data service selection, stocks and build limits; retained industry profile weights",
                                  rows=len(patches["simple_industry"])))
        if patches:
            print(f"Applying regional defaults: {name} ({len(patches)} tables)", flush=True)
            replace_sheets(path, patches)
    return notes
