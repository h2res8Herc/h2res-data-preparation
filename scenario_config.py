"""Explicit scenario assumptions for the H2RES input bundle."""
from __future__ import annotations

import json
import math
from pathlib import Path
import re
import shutil

import pandas as pd


def positive_integer(value, label: str) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a positive integer") from None
    if isinstance(value, bool) or not math.isfinite(number) or number <= 0 or not number.is_integer():
        raise ValueError(f"{label} must be a positive integer")
    return int(number)


def parse_years(raw) -> list[int]:
    try:
        values = raw.split(",") if isinstance(raw, str) else list(raw)
    except TypeError:
        raise ValueError("Planning years must be a comma-separated string or a list") from None
    years = [positive_integer(value, "Planning year") for value in values]
    if not years or years != sorted(set(years)):
        raise ValueError("Planning years must be strictly increasing and unique")
    if len({b - a for a, b in zip(years, years[1:])}) > 1:
        raise ValueError("This model requires equally spaced planning years")
    return years


def finite_number(value, label: str, *, fraction=False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be numeric") from None
    if not math.isfinite(number) or number < 0 or (fraction and number > 1):
        raise ValueError(f"{label} must be finite and {'between 0 and 1' if fraction else 'non-negative'}")
    return number


def resolve_scenario(args) -> dict | None:
    """CLI values override JSON; no options keeps the original reference intact."""
    config_path = getattr(args, "scenario_config", None)
    config = json.loads(Path(config_path).read_text(encoding="utf-8")) if config_path else {}
    allowed = {"preset", "scope", "years", "start_year", "end_year", "year_step", "target_year",
               "start_share", "investment_multiplier", "investment_overrides"}
    if not isinstance(config, dict) or set(config) - allowed:
        raise ValueError(f"Scenario configuration must be an object with keys {sorted(allowed)}")

    def choice(name, key, default=None):
        value = getattr(args, name, None)
        return config.get(key, default) if value is None else value

    preset = choice("scenario_preset", "preset", "reference")
    scope = choice("scenario_scope", "scope", "all-energy")
    if preset not in {"reference", "res100"} or scope not in {"electricity", "all-energy"}:
        raise ValueError("Unknown scenario preset or renewable target scope")
    years = choice("planning_years", "years")
    start, end, step = (choice(name, key) for name, key in (("start_year", "start_year"), ("end_year", "end_year"), ("year_step", "year_step")))
    if years is not None and any(v is not None for v in (start, end, step)):
        raise ValueError("Specify planning-years or start/end/year-step, not both")
    if any(v is not None for v in (start, end, step)):
        start, end, step = (positive_integer(start, "Start year") if start is not None else 2025,
                            positive_integer(end, "End year") if end is not None else 2050,
                            positive_integer(step, "Year step") if step is not None else 1)
        if start <= 0 or step <= 0 or end < start or (end - start) % step:
            raise ValueError("Planning range needs a positive step and an end year on its grid")
        years = list(range(start, end + 1, step))
    if years is not None:
        years = parse_years(years)
    target = choice("renewable_target_year", "target_year", 2050)
    target = positive_integer(target, "Renewable target year")
    start_share = choice("renewable_start_share", "start_share")
    if start_share is not None:
        start_share = finite_number(start_share, "Starting renewable share", fraction=True)
    multiplier = finite_number(choice("investment_multiplier", "investment_multiplier", 1.), "Investment multiplier")
    overrides = config.get("investment_overrides", [])
    if not isinstance(overrides, list):
        raise ValueError("investment_overrides must be a list")
    if preset == "res100" and scope == "all-energy" and not args.efuels:
        raise ValueError("The whole-energy RES preset requires --efuels for renewable fuel pathways")
    if preset == "reference" and (start_share is not None or getattr(args, "renewable_target_year", None) is not None):
        raise ValueError("Renewable target settings require --scenario-preset res100")
    explicit = config_path or any(getattr(args, name, None) is not None for name in
                                  ("scenario_preset", "planning_years", "start_year", "end_year", "year_step", "investment_multiplier"))
    if preset == "reference" and years is None and multiplier == 1 and not overrides:
        if not explicit or not config_path:
            return None
    return {"preset": preset, "scope": scope, "years": years, "target_year": target,
            "start_share": start_share, "investment_multiplier": multiplier,
            "investment_overrides": overrides}


def setup_table(reference: pd.DataFrame, years: list[int]) -> pd.DataFrame:
    controls = ("chunk_size", "step_size", "first_hour", "last_hour")
    result = pd.DataFrame({"years_all": years})
    for column in controls:
        values = reference[column].dropna()
        if values.empty:
            raise ValueError(f"Reference setup has no {column}")
        result[column] = float("nan")
        result.loc[0, column] = values.iloc[0]
    return result


def renewable_curve(reference: pd.DataFrame, systems: list[str], years: list[int], target: int, start_share=None):
    if target not in years or target <= years[0]:
        raise ValueError("RES target year must be a modeled year after the first planning year")
    result = reference.copy()
    year_columns = [column for column in result if re.fullmatch(r"\d{4}", str(column))]
    result[year_columns] = result[year_columns].apply(pd.to_numeric, errors="raise").astype(float)
    assumptions = []
    for system in systems:
        selected = result.System.eq(system)
        if not selected.any():
            if start_share is None:
                raise ValueError(f"No starting RPS share for {system}; provide --renewable-start-share")
            result = pd.concat([result, pd.DataFrame([{"System": system}])], ignore_index=True)
            selected = result.System.eq(system)
        column = years[0] if years[0] in result else str(years[0])
        initial = start_share if start_share is not None else result.loc[selected, column].iloc[0]
        initial = finite_number(initial, f"Starting RPS share for {system}", fraction=True)
        assumptions.append({"System": system, "initial_electricity_share": initial,
                            "basis": "user scenario value" if start_share is not None else "reference RPS trajectory; not a measured national share"})
        for column in result:
            if re.fullmatch(r"\d{4}", str(column)):
                year = int(column)
                if year >= years[0]:
                    result.loc[selected, column] = initial + (1. - initial) * min(1., (year - years[0]) / (target - years[0]))
        for year in years:
            if year not in result and str(year) not in result:
                result[year] = float("nan")
            col = year if year in result else str(year)
            result.loc[selected, col] = initial + (1. - initial) * min(1., (year - years[0]) / (target - years[0]))
    return result, assumptions


def investment_tables(tables: dict[str, pd.DataFrame], multiplier: float, overrides: list[dict]) -> dict[str, pd.DataFrame]:
    result = {name: frame.copy() for name, frame in tables.items()}
    for name, frame in result.items():
        for column in frame:
            label = str(column)
            annual = (name == "cap_inv_lim" and label not in {"zone", "System"} and not label.startswith("year"))
            annual |= bool(re.fullmatch(r"(?:max_inv_period|CC_max_inv_period|Reboiler_max_inv_period|Tank_stor_max_inv_period)(?:_\d{4})?", label))
            annual |= label == "max_cap_period"
            annual |= name == "transport_all" and bool(re.fullmatch(r"\d{4}", label))
            if annual and multiplier != 1.:
                cleaned = frame[column].replace(r"^\s*$", float('nan'), regex=True)
                numeric = pd.to_numeric(cleaned, errors="raise")
                if numeric.dropna().map(lambda value: not math.isfinite(value) or value < 0).any():
                    raise ValueError(f"Investment limit {name}/{column} must be finite and non-negative or blank")
                frame[column] = numeric * multiplier
    for override in overrides:
        if not isinstance(override, dict) or set(override) - {"sheet", "column", "value", "where", "years"}:
            raise ValueError("Investment overrides accept sheet, column, value, where and years")
        name = override.get("sheet")
        if name not in result:
            raise ValueError(f"No investment sheet {name!r} in selected technology workbook")
        frame = result[name]
        column = override.get("column")
        value = finite_number(override.get("value"), "Investment override")
        permitted = column == "max_cap_period" or bool(re.fullmatch(r"(?:max_inv_period|CC_max_inv_period|Reboiler_max_inv_period|Tank_stor_max_inv_period)(?:_\d{4})?", str(column)))
        permitted |= name == "cap_inv_lim" and column not in {"year", "zone", "System"}
        permitted |= name == "transport_all" and bool(re.fullmatch(r"\d{4}", str(column)))
        if name == "cap_inv_lim" and str(column).startswith("year"):
            permitted = False
        if not permitted:
            raise ValueError(f"Override {name}/{column} is not an annual investment limit")
        mask = pd.Series(True, index=frame.index)
        filters = override.get("where", {})
        if not isinstance(filters, dict):
            raise ValueError("Investment override 'where' must be an object of column/value filters")
        for key, expected in filters.items():
            if key not in frame:
                raise ValueError(f"Unknown override filter {key} in {name}")
            mask &= frame[key].astype(str).eq(str(expected))
        selected_years = override.get("years")
        columns = [column]
        if selected_years is not None:
            selected_years = parse_years(selected_years)
            if "year" in frame:
                mask &= pd.to_numeric(frame.year, errors="coerce").isin(selected_years)
            elif name == "transport_all":
                columns = selected_years
            else:
                columns = [f"{column}_{year}" for year in selected_years]
        if not mask.any():
            raise ValueError(f"Investment override matches no rows in {name}")
        for col in columns:
            actual = col if col in frame else str(col) if str(col) in frame else int(col) if str(col).isdigit() and int(col) in frame else None
            if actual is None:
                raise ValueError(f"Missing investment column {col!r} in {name}")
            frame[actual] = pd.to_numeric(frame[actual], errors="raise").astype(float)
            frame.loc[mask, actual] = value
    return result


def write_reference_launcher(output: Path, workbook_name: str, *, efuels: bool, industry_mode: str, electricity_case: str):
    """Carry selected flags into H2RES without altering any reference policy."""
    from model_input_bundle import selected_complex_workbook
    setup = pd.read_excel(output / 'data' / ('policy_efuel.xlsx' if efuels else 'policy.xlsx'),'setup')
    years = parse_years(setup.years_all.dropna().tolist())
    record = dict(preset='reference',scope='all-energy',years=years,target_year=max(years),start_share=None,
                  investment_multiplier=1.,investment_overrides=[],technology_workbook=workbook_name,
                  industry_mode=industry_mode,industry_electricity_case=electricity_case,efuels=efuels,
                  complex_workbook=selected_complex_workbook(efuels,electricity_case) if industry_mode=='complex' else None,
                  requires_scenario_launcher=True,assumptions=[],target_definition='Unchanged reference policies',
                  investment_basis='Explicit generated generator links and conserved native annual build budgets')
    (output/'scenario.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    for name in ('run_model_scenario.py','scenario_runtime.py'):
        shutil.copy2(Path(__file__).resolve().parent/name,output/name)
    return record


def apply_scenario(output: Path, workbook_name: str, settings: dict | None, *, efuels: bool, industry_mode: str,
                   electricity_case: str = "conservative") -> dict | None:
    if settings is None:
        # copy_baseline may reuse an output directory from a previous preset.
        (output / "scenario.json").unlink(missing_ok=True)
        return None
    from model_input_bundle import replace_sheets, selected_complex_workbook
    data = output / "data"
    selected = data / workbook_name
    with pd.ExcelFile(selected) as book:
        costs = pd.read_excel(book, "tech_cost_years")
        names = [name for name in book.sheet_names if name in {
            "cap_inv_lim", "Industry_data", "simple_industry", "industry_CC", "industry_heat_stor", "transport_all",
            "flex_tech", "flex_tech_heat", "flex_tech_DH", "thermal_tech", "thermal_tech_DH", "efuel", "PE_generation",
            "solar_DH", "solar_indv", "solar_stor_DH", "solar_stor_indv"}]
        tables = {name: pd.read_excel(book, name) for name in names}
        active = pd.read_excel(book, "active_zones")
    systems = sorted(active.loc[active.active.eq("Y"), "System"].unique().tolist())
    setup = pd.read_excel(data / ("policy_efuel.xlsx" if efuels else "policy.xlsx"), "setup")
    years = settings["years"] or parse_years(setup.years_all.tolist())
    available = set(pd.to_numeric(costs.year, errors="raise").astype(int))
    if not set(years).issubset(available):
        raise ValueError(f"Planning years outside available cost data {min(available)}–{max(available)}; no extrapolation is assumed")
    policy_patches = {}
    assumptions = []
    for name in ("policy.xlsx", "policy_efuel.xlsx"):
        patches = {"setup": setup_table(pd.read_excel(data / name, "setup"), years)}
        if settings["preset"] == "res100":
            patches["RPS"], assumptions = renewable_curve(pd.read_excel(data / name, "RPS"), systems, years,
                                                          settings["target_year"], settings["start_share"])
        policy_patches[name] = patches
    updated = investment_tables(tables, settings["investment_multiplier"], settings["investment_overrides"])
    changed = {name: updated[name] for name in updated if not updated[name].equals(tables[name])}
    complex_patch = None
    if industry_mode == "complex" and settings["investment_multiplier"] != 1.:
        complex_name = selected_complex_workbook(efuels, electricity_case)
        raw = pd.read_excel(data / complex_name, sheet_name=["complex_industry", "CC"])
        complex_patch = (complex_name, investment_tables(raw, settings["investment_multiplier"], []))
    for name, patches in policy_patches.items():
        replace_sheets(data / name, patches)
    if changed:
        replace_sheets(selected, changed)
    if complex_patch:
        replace_sheets(data / complex_patch[0], complex_patch[1])
    record = {**settings, "years": years, "technology_workbook": workbook_name,
              "industry_mode": industry_mode, "industry_electricity_case": electricity_case, "efuels": efuels,
              "complex_workbook": selected_complex_workbook(efuels, electricity_case) if industry_mode == "complex" else None,
              "assumptions": assumptions, "requires_scenario_launcher": True,
              "target_definition": ("No fossil/nuclear energy use or unverified energy imports at and after the target year; renewable electricity trajectory. "
                                    "Non-electric transition before that year is chosen by the optimizer. This is an energy-origin target, not a net-zero CO2 definition.")
                                   if settings["preset"] == "res100" and settings["scope"] == "all-energy" else "Native electricity RPS or reference policies",
              "investment_basis": "Reference annual build limits scaled uniformly; zero remains blocked and blank remains unrestricted. Overrides use the sheet's native units."}
    (output / "scenario.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    for filename in ("run_model_scenario.py", "scenario_runtime.py"):
        shutil.copy2(Path(__file__).resolve().parent / filename, output / filename)
    return record
