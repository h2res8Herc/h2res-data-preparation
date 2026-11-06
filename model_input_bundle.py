"""Export sector results against the actual H2RES model input contract.

Reference workbooks are copied byte for byte. Replacing a sheet changes only its
worksheet XML, preserving formulas and their cached results everywhere else.
No network, policy, cost, or process-production data are invented for new zones.
"""
from __future__ import annotations

import hashlib
from contextlib import ExitStack
from copy import copy
import json
import posixpath
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import xml.etree.ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
import pandas as pd

from h2res_input_schema import annual_limits, model_calendar, transport_identifiers, validate_limits

ROOT = Path(__file__).resolve().parent
MODEL_VERSION = "H2RES_2.11.2026_novi"
DEFAULT_MODEL_ROOT = Path(r"D:\POSAO\H2RES_2.11.2026_novi")
LEGACY_REFERENCE = ROOT / "model_reference"
DEFAULT_REFERENCE = ROOT / "model_reference_2_11_2026"
TECH_WORKBOOKS = (
    "flex_tech.xlsx", "flex_tech_categories.xlsx", "flex_tech_complex_industry.xlsx",
    "flex_tech_efuel.xlsx", "flex_tech_efuel_categories.xlsx", "flex_tech_efuel_complex_industry.xlsx",
    "variants/technical_2050/flex_tech_efuel_categories.xlsx",
)
OTHER_WORKBOOKS = ("policy.xlsx", "policy_efuel.xlsx", "policy_fuels.xlsx", "industry_complex.xlsx",
                   "industry_complex_efuel.xlsx", "industry_complex_electricity_technical_2050.xlsx",
                   "industry_complex_efuel_electricity_technical_2050.xlsx", "h2_terminals.xlsx")
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def snapshot_reference(model_root: Path, destination: Path = DEFAULT_REFERENCE) -> dict:
    """Snapshot the complete live data tree; the model directory is read-only."""
    source = model_root.resolve() / "data"
    destination = destination.resolve()
    if destination == source or source in destination.parents or destination in source.parents:
        raise ValueError("The portable reference must be separate from the source model data")
    required = [source / name for name in (*TECH_WORKBOOKS[:6], *OTHER_WORKBOOKS)]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("Model reference inputs missing: " + ", ".join(missing))
    files = sorted(path for path in source.rglob("*") if path.is_file())
    directories = sorted(path.relative_to(source).as_posix() for path in source.rglob("*") if path.is_dir())
    (destination / "data").mkdir(parents=True, exist_ok=True)
    for name in directories:
        (destination / "data" / name).mkdir(parents=True, exist_ok=True)
    records = {}
    for path in files:
        if not path.resolve().is_relative_to(source):
            raise ValueError(f"Model data path points outside its data directory: {path}")
        relative = path.relative_to(source)
        target = destination / "data" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = sha256(path)
        if not target.exists() or sha256(target) != digest:
            shutil.copy2(path, target)
        records[relative.as_posix()] = {"sha256": digest, "bytes": path.stat().st_size}
    contract = {}
    for path in (model_root / "main.py", model_root / "scripts" / "read_process_data.py"):
        contract[path.name] = sha256(path)
    manifest = {"model_root": str(model_root.resolve()), "model_version": model_root.resolve().name,
                "captured_utc": datetime.now(timezone.utc).isoformat(), "data_layout": "model-directory-mirror",
                "directories": directories, "reader_sha256": contract, "files": records}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def selected_workbook(efuels: bool, industry_mode: str, electricity_case: str = "conservative") -> str:
    if industry_mode not in ("regular", "categories", "complex"):
        raise ValueError(f"Unknown industry mode: {industry_mode}")
    name = "flex_tech" + ("_efuel" if efuels else "")
    name += {"regular": "", "categories": "_categories", "complex": "_complex_industry"}[industry_mode]
    if efuels and industry_mode == "categories":
        if electricity_case == "technical_2050":
            return "variants/technical_2050/" + name + ".xlsx"
        if electricity_case != "conservative":
            raise ValueError(f"Unknown category electricity case: {electricity_case}")
    return name + ".xlsx"


def selected_complex_workbook(efuels: bool, electricity_case: str = "conservative") -> str:
    name = "industry_complex" + ("_efuel" if efuels else "")
    if electricity_case == "technical_2050":
        name += "_electricity_technical_2050"
    elif electricity_case != "conservative":
        raise ValueError(f"Unknown complex electricity case: {electricity_case}")
    return name + ".xlsx"


def sheet_paths(book: ZipFile) -> dict[str, str]:
    relations = ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))
    targets = {r.attrib["Id"]: posixpath.normpath("xl/" + r.attrib["Target"]) if not r.attrib["Target"].startswith("/")
               else r.attrib["Target"].lstrip("/") for r in relations}
    workbook = ET.fromstring(book.read("xl/workbook.xml"))
    return {s.attrib["name"]: targets[s.attrib[f"{{{REL_NS}}}id"]]
            for s in workbook.find(f"{{{MAIN_NS}}}sheets")}


def replace_sheets(path: Path, sheets: dict[str, pd.DataFrame]) -> None:
    """Patch existing sheets without round-tripping unrelated Excel cells."""
    from openpyxl import Workbook
    with TemporaryDirectory(dir=path.parent, prefix="_sheet_patch_") as folder:
        replacement = Path(folder) / "replacement.xlsx"
        workbook = Workbook(write_only=True)
        for name, frame in sheets.items():
            sheet = workbook.create_sheet(name)
            sheet.append(list(frame.attrs.get('native_header_cells',frame.columns)))
            for row in frame.itertuples(index=False, name=None):
                sheet.append([None if pd.isna(value) else value.item() if isinstance(value, np.generic) else value for value in row])
        workbook.save(replacement)
        patched = Path(folder) / "patched.xlsx"
        with ZipFile(path) as original, ZipFile(replacement) as new, ZipFile(patched, "w", ZIP_DEFLATED) as target:
            original_paths, new_paths = sheet_paths(original), sheet_paths(new)
            missing = set(sheets) - set(original_paths)
            if missing:
                raise ValueError(f"{path.name} has no sheets {sorted(missing)}")
            from excel_integrity import patch_sheet_parts
            patches = patch_sheet_parts(original, new, original_paths, new_paths, sheets)
            for member in original.infolist():
                if member.filename in patches:
                    target.writestr(copy(member), patches[member.filename])
                else:
                    with original.open(member) as source, target.open(copy(member), "w") as destination:
                        shutil.copyfileobj(source, destination, length=1024 * 1024)
        from excel_integrity import workbook_errors
        errors = workbook_errors(patched)
        if errors:
            raise ValueError(f"Invalid Excel package {path.name}: " + "; ".join(errors[:8]))
        patched.replace(path)


def reference_for(args) -> Path:
    reference = args.model_reference.resolve()
    # Existing GUI windows may still pass the old default template directory.
    if not args.model_root and reference == LEGACY_REFERENCE.resolve():
        reference = DEFAULT_REFERENCE.resolve()
    args.model_reference = reference
    if args.model_root or not (reference / "manifest.json").is_file():
        source = args.model_root or DEFAULT_MODEL_ROOT
        snapshot_reference(source, reference)
        print(f"Portable model reference: {reference}", flush=True)
    info = json.loads((reference / "manifest.json").read_text(encoding="utf-8"))
    version = info.get("model_version") or Path(info.get("model_root") or MODEL_VERSION).name
    print(f"Input format: {version}; templates: {reference}", flush=True)
    return reference


def preflight_reference(args, reference: Path) -> None:
    """Check local export contracts before starting source pipelines."""
    if getattr(args, "all_model_variants", False):
        from copy import copy
        from model_variants import configurations
        for efuels, mode, case in [*configurations(), (False, "complex", "technical_2050"), (True, "complex", "technical_2050")]:
            variant = copy(args)
            variant.all_model_variants = False
            variant.efuels, variant.industry_mode, variant.industry_electricity_case = efuels, mode, case
            preflight_reference(variant, reference)
        return
    workbook_name = selected_workbook(args.efuels, args.industry_mode, args.industry_electricity_case)
    data = reference / "data"
    metadata = json.loads((reference / "manifest.json").read_text(encoding="utf-8"))
    absent = [name for name in metadata.get("files", {}) if not (data / name).is_file()]
    if absent:
        raise ValueError(f"Portable reference has missing files: {absent}")
    from excel_integrity import workbook_errors
    integrity = workbook_errors(data / workbook_name)
    if integrity:
        raise ValueError(f"Model template {workbook_name} needs repair: " + "; ".join(integrity[:6]))
    required = {"active_zones": {"System", "zone", "active"}, "tech_cost_years": {"year"}}
    if "industry" in args.sectors and args.industry_mode != "complex":
        required.update(Industry_data={"Industry", "unit_name", "cap_mw", "share_fuel_2020", "max_share_fuel"},
                        simple_industry={"unit_name", "fuel_type", "Industry", "cap_mw"})
        if args.industry_mode == "categories":
            required["Industry_data"].add("category")
    if "transport" in args.sectors:
        required["transport_all"] = {"System", "zone", "sector", "unit_name", "type", "number", "efficiency_primary"}
        if args.efuels:
            required["transport_ICE_prim"] = {"sector_prim", "fuel_prim", "zone", "system", "use"}
    if "heating" in args.sectors:
        for name in ("flex_tech_heat", "flex_tech_DH", "thermal_tech", "thermal_tech_DH", "solar_indv", "solar_DH"):
            required[name] = {"System", "zone"}
    path = data / workbook_name
    if not path.is_file():
        raise ValueError(f"Selected portable technology workbook is missing: {path}")
    with pd.ExcelFile(path) as book:
        absent_sheets = set(required) - set(book.sheet_names)
        if absent_sheets:
            raise ValueError(f"{workbook_name} is missing sheets {sorted(absent_sheets)}")
        tables = {name: pd.read_excel(book, name) for name in required}
    for name, columns in required.items():
        absent_columns = columns - set(tables[name])
        if absent_columns:
            raise ValueError(f"{workbook_name}/{name} is missing columns {sorted(absent_columns)}")
        validate_limits(tables[name])
    if "industry" in args.sectors and args.industry_mode == "complex":
        name = selected_complex_workbook(args.efuels, args.industry_electricity_case)
        companion = {"complex_industry": {"Industry", "branch", "component", "unit_name", "cap_mw"},
                     "Process_data": {"Industry", "branch", "component"},
                     "Product_demand": {"Industry", "branch", "product_unit"},
                     "CC": {"Industry", "branch", "CC_cap"}}
        with pd.ExcelFile(data / name) as book:
            absent = set(companion) - set(book.sheet_names)
            if absent:
                raise ValueError(f"{name} is missing sheets {sorted(absent)}")
            for sheet, columns in companion.items():
                headers = pd.read_excel(book, sheet, nrows=0)
                if columns - set(headers):
                    raise ValueError(f"{name}/{sheet} is missing columns {sorted(columns - set(headers))}")
    if args.efuels and "transport" in args.sectors:
        engines = transport_identifiers(tables["transport_all"])
        fuels = transport_identifiers(tables["transport_ICE_prim"])
        needed = set(engines.loc[engines.type.isin(["ICE", "HYBRID"]), "unit_name"])
        missing_fuels = needed - set(fuels.sector_prim)
        if missing_fuels:
            raise ValueError(f"{workbook_name}/transport_ICE_prim lacks engines {sorted(missing_fuels)}")
    settings = getattr(args, "scenario", None)
    if settings:
        from scenario_config import investment_tables, parse_years
        policy_name = "policy_efuel.xlsx" if args.efuels else "policy.xlsx"
        setup = pd.read_excel(data / policy_name, "setup")
        years = settings["years"] or parse_years(setup.years_all.tolist())
        available = set(pd.to_numeric(tables["tech_cost_years"].year, errors="raise"))
        if not set(years).issubset(available):
            raise ValueError("Planning years are outside the portable technology cost data; no downloads started")
        if settings["preset"] == "res100" and (settings["target_year"] not in years or settings["target_year"] <= years[0]):
            raise ValueError("RES target year must be a modeled year after the first planning year")
        # The complete set of investment tables is needed to validate selectors.
        if settings["investment_overrides"]:
            with pd.ExcelFile(path) as book:
                investment_tables({name: pd.read_excel(book, name) for name in book.sheet_names},
                                  settings["investment_multiplier"], settings["investment_overrides"])


def import_model_inputs(reference: Path, out_root: Path) -> Path:
    """Materialize the supplied model's complete baseline, without reallocating it."""
    output = out_root.resolve() / "model_inputs"
    if output == reference or output in reference.parents or reference in output.parents:
        raise ValueError("Output and reference directories must be separate")
    repairs = copy_baseline(reference, output / "data")
    (output / "complex_generation.json").unlink(missing_ok=True)
    shutil.copy2(reference / "manifest.json", output / "reference_manifest.json")
    metadata = {"source": "supplied model baseline", "generated_sectors": [],
                "input_repairs": repairs,
                "note": "Original model geography and scenario assumptions retained."}
    reference_info = json.loads((reference / "manifest.json").read_text(encoding="utf-8"))
    metadata.update(model_version=reference_info.get("model_version", MODEL_VERSION),
                    data_layout=reference_info.get("data_layout"),
                    data_directories=reference_info.get("directories", []), reference_files=reference_info["files"],
                    reference_model_root=reference_info.get("model_root"))
    (output / "bundle_manifest.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return output


def copy_baseline(reference: Path, destination: Path) -> list[dict]:
    shutil.copytree(reference / "data", destination, dirs_exist_ok=True)
    if (reference / "data/variants/technical_2050/flex_tech_efuel_categories.xlsx").exists():
        # These application-generated v1 aliases were replaced by live v2 paths.
        for name in ("flex_tech_efuel_categories_electricity_review.xlsx", "flex_tech_efuel_categories_electricity_technical_2050.xlsx"):
            (destination / name).unlink(missing_ok=True)
    # The supplied transport file repeats the HR1 year byte-for-byte. Removing
    # exact repeated records preserves the reader's dictionary values while
    # making the hourly keys unambiguous. Conflicting records remain errors.
    path = destination / "transport_demand.csv"
    frame = pd.read_csv(path)
    unique = frame.drop_duplicates()
    repairs = []
    if len(unique) != len(frame):
        unique.to_csv(path, index=False)
        repairs.append({"file": path.name, "operation": "remove identical duplicate rows", "removed_rows": len(frame) - len(unique)})
    return repairs


def write_csv(frame: pd.DataFrame, path: Path, hourly: bool = False) -> None:
    if hourly:
        frame = model_calendar(frame)
    frame.to_csv(path, index=False)


def read_generated(path: Path, *, hourly: bool = False) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Required generated input is missing: {path}")
    result = pd.read_csv(path)
    return model_calendar(result) if hourly else result


def industry_parameters(generated: pd.DataFrame, reference: pd.DataFrame) -> pd.DataFrame:
    """Reuse current equipment assumptions; keep generated regional baselines."""
    from industry.fuel_representation import UNSUPPORTED_REGULAR
    if "fuel_type" in generated and "fuel_type" in reference:
        unsupported = (set(generated.fuel_type.dropna()) & UNSUPPORTED_REGULAR) - set(reference.fuel_type.dropna())
        if unsupported:
            raise ValueError(f"Prepared industry contains unsupported fuels {sorted(unsupported)} for this workbook. "
                             "Regenerate Industry using cached downloads to redistribute heat/waste; then export again.")
    keys = ["Industry", "unit_name"] + (["category"] if "category" in reference else [])
    reference = reference.dropna(subset=keys).copy()
    # HR1 is the calibrated national reference in this supplied model copy.
    if "zone" in reference and reference.zone.eq("HR1").any():
        reference = reference.loc[reference.zone.eq("HR1")]
    parameters = [c for c in reference if c not in {"System", "zone", "cap_mw", "share_fuel_2020", *keys}
                  and not str(c).startswith(("Unnamed:", "Column"))]
    duplicates = reference.duplicated(keys, keep=False)
    if duplicates.any():
        for _, group in reference.loc[duplicates].groupby(keys, dropna=False):
            if any(group[c].nunique(dropna=False) > 1 for c in parameters):
                raise ValueError(f"Ambiguous reference parameters for {tuple(group.iloc[0][keys])}")
    lookup = reference.drop_duplicates(keys).set_index(keys)
    rows = generated.to_dict("records")
    for row in rows:
        key = tuple(row[c] for c in keys)
        if key not in lookup.index:
            continue
        template = lookup.loc[key]
        baseline_share = float(row["share_fuel_2020"])
        row.update({col: template[col] for col in parameters})
        row["max_share_fuel"] = max(baseline_share, float(template.max_share_fuel))
    # Infer columns from the completed records. Integer-valued source defaults
    # must accept calibrated fractions without rounding or in-place upcasting.
    result = pd.DataFrame(rows, index=generated.index) if rows else generated.copy()
    # Supplemental HP equipment is part of this version's technology choice.
    # Its existing capacity is zero; operating limits and costs stay calibrated.
    services = result[[c for c in ("System", "zone", "Industry", "category") if c in result]].drop_duplicates()
    extra = []
    for service in services.to_dict("records"):
        candidates = reference.loc[reference.Industry.eq(service["Industry"]) & reference.unit_name.str.startswith("HP_industry_", na=False)]
        if "category" in reference:
            candidates = candidates.loc[candidates.category.eq(service["category"])]
        for candidate in candidates.drop_duplicates(keys).to_dict("records"):
            exists = result.unit_name.eq(candidate["unit_name"]) & result.Industry.eq(service["Industry"]) & result.zone.eq(service["zone"])
            if "category" in reference:
                exists &= result.category.eq(service["category"])
            if exists.any():
                continue
            candidate.update(service)
            candidate.update(cap_mw=0.0, share_fuel_2020=0.0)
            extra.append(candidate)
    if extra:
        result = pd.concat([result, pd.DataFrame(extra)], ignore_index=True)
    return annual_limits(result)


def pooled_industry(industry: pd.DataFrame, profiles: pd.DataFrame, template: pd.DataFrame) -> pd.DataFrame:
    """Recalculate the numeric remainder so old cached pooling cannot double count."""
    services = ["System", "zone", "Industry", "category"]
    main = industry.loc[~industry.unit_name.str.startswith("HP_industry_", na=False)].copy()
    # The reader treats any enabled equipment (including heat pumps) as a
    # detailed service. Disabled fuel alternatives in that service are not a
    # second remainder demand.
    flags = industry.include_in_the_model.astype(str).str.strip().str.upper().isin(["Y","YES","TRUE","1","1.0"])
    active = industry.loc[flags, services].drop_duplicates()
    excluded = main.merge(active.assign(_selected=True), on=services, how="left", validate="many_to_one")
    excluded = excluded.loc[excluded._selected.isna()]
    rows = []
    for (system, zone), block in excluded.groupby(["System", "zone"], sort=False):
        local_profiles = profiles.loc[profiles.System.eq(system) & profiles.zone.eq(zone)]
        weights = {}
        for sector, category in block[["Industry", "category"]].drop_duplicates().itertuples(index=False, name=None):
            name = f"{sector}[{category}]" if category != "all" else sector
            if name not in local_profiles:
                raise ValueError(f"Cannot pool industry demand: missing {name} for {(system, zone)}")
            weights[sector, category] = float(local_profiles[name].sum())
        total = sum(weights.values())
        for (unit, fuel), group in block.groupby(["unit_name", "fuel_type"], sort=False):
            candidates = template.loc[template.unit_name.eq(unit)]
            row = (candidates.iloc[0] if not candidates.empty else group.iloc[0]).to_dict()
            row.update(System=system, zone=zone, Industry="remainder", category="all",
                       unit_name=unit, fuel_type=fuel, include_in_the_model="Y",
                       cap_mw=float(group.cap_mw.sum()),
                       share_fuel_2020=sum(float(r.share_fuel_2020) * weights[r.Industry, r.category]
                                           for r in group.itertuples(index=False)) / total if total else 0.)
            row["max_share_fuel"] = max(row["share_fuel_2020"], sum(
                float(r.max_share_fuel) * weights[r.Industry, r.category] for r in group.itertuples(index=False)
            ) / total if total else 0.)
            # Preserve baseline fuel input with a service-weighted harmonic
            # efficiency instead of retaining an unrelated old pooled value.
            useful = sum(float(r.share_fuel_2020) * weights[r.Industry, r.category] for r in group.itertuples(index=False))
            if useful > 0 and "efficiency" in group:
                final = sum(float(r.share_fuel_2020) * weights[r.Industry, r.category] / float(r.efficiency)
                            for r in group.itertuples(index=False) if float(r.share_fuel_2020) > 0)
                if final <= 0 or not np.isfinite(final):
                    raise ValueError(f"Invalid efficiency while pooling {(system,zone,unit)}")
                row["efficiency"] = useful / final
                if "CO2Intensity" in group:
                    row["CO2Intensity"] = sum(
                        float(r.share_fuel_2020) * weights[r.Industry,r.category] / float(r.efficiency) * float(r.CO2Intensity)
                        for r in group.itertuples(index=False) if float(r.share_fuel_2020)>0
                    ) / final
            # Existing stocks and per-service build envelopes add when their
            # services are collapsed. Blank/unrestricted bounds remain blank.
            additive = [c for c in group if c in {"max_cap","CC_cap","Reboiler_cap","Tank_stor_cap"}
                        or re.fullmatch(r"(?:max_inv_period|CC_max_inv_period|Reboiler_max_inv_period|Tank_stor_max_inv_period)(?:_\d{4})?",str(c))]
            for column in additive:
                values = pd.to_numeric(group[column],errors="raise")
                row[column] = float(values.sum()) if values.notna().all() else np.nan
            rows.append(row)
    if not rows:
        return template.iloc[:0].copy()
    result=annual_limits(pd.DataFrame(rows))
    # Older simple templates omit ceilings present in Industry_data. Keep
    # those native fields so pooling does not silently discard their bounds.
    additional=[c for c in result if c in {'max_cap','CC_cap','Reboiler_cap','Tank_stor_cap'}
                or re.fullmatch(r'(?:max_inv_period|CC_max_inv_period|Reboiler_max_inv_period|Tank_stor_max_inv_period)(?:_\d{4})?',str(c))]
    return result.reindex(columns=list(dict.fromkeys([*template.columns,*additional])))


def export_complex_sector(args, mapping: pd.DataFrame) -> None:
    """Compatibility entry point; complex inputs are compiled from country sources."""
    from industry.generate_complex_industry_inputs import compile_inputs
    compile_inputs(countries=args.countries, mapping=mapping, reference=args.model_reference,
                   output=args.out_root / "industry" / "combined", cache=args.data_root / "industry" / "jrc_idees_2023",
                   source_root=getattr(args, "industry_source_root", None), download=getattr(args, "industry_download", True),
                   refresh=args.refresh_sources, efuels=args.efuels, electricity_case=args.industry_electricity_case,
                   base_year=getattr(args, "industry_base_year", 2020), zone_weights=getattr(args, "industry_zone_weights", None),
                   regional_allocation=getattr(args, "industry_regional_allocation", "require-weights"),
                   selected_sectors=getattr(args, "complex_industry_sectors", "all"), waste_allocation=getattr(args, "industry_waste_allocation", "sector-blend"))


def transport_parameters(generated: pd.DataFrame, template: pd.DataFrame,
                         primary: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """Keep current paid engine conversions and fuel compatibility metadata."""
    generated = transport_identifiers(generated)
    generated = generated.rename(columns={c: int(c) for c in generated if re.fullmatch(r"\d{4}", str(c))})
    if template.zone.eq("HR1").any():
        template = template.loc[template.zone.eq("HR1")].copy()
    base = template.loc[template.get("compat_parent", pd.Series(np.nan, index=template.index)).isna()]
    derived = template.loc[template.get("compat_parent", pd.Series(np.nan, index=template.index)).notna()]
    keep = {"zone", "System", "sector", "unit_name", "total_load", "number", "efficiency_primary"}
    rows = []
    for original in generated.to_dict("records"):
        matching = base.loc[base.unit_name.eq(original["unit_name"]) & base.sector.eq(original["sector"])]
        source = matching.iloc[0] if not matching.empty else None
        row = dict(original)
        if source is not None:
            row.update({c: source[c] for c in template if c not in keep and not str(c).startswith("compat_")})
        rows.append(row)
        children = derived.loc[derived.compat_parent.eq(original["unit_name"]) & derived.sector.eq(original["sector"])] if not derived.empty else derived
        for child in children.drop_duplicates(["unit_name", "sector"]).to_dict("records"):
            child.update(zone=original["zone"], System=original["System"], total_load=original["total_load"], number=0.)
            if source is not None and float(source.efficiency_primary) > 0:
                child["efficiency_primary"] = (float(original["efficiency_primary"]) * float(child["efficiency_primary"])
                                                / float(source.efficiency_primary))
            rows.append(child)
    result = pd.DataFrame(rows)
    if primary is None:
        return result, None
    fuel_rows = []
    for row in result.itertuples(index=False):
        options = primary.loc[primary.sector_prim.eq(row.unit_name)]
        if options.zone.eq("HR1").any():
            options = options.loc[options.zone.eq("HR1")]
        options = options.drop_duplicates(["sector_prim", "fuel_prim"])
        if row.type in ("ICE", "HYBRID") and options.empty:
            raise ValueError(f"No current primary-fuel compatibility mapping for {row.unit_name}")
        for option in options.to_dict("records"):
            option.update(zone=row.zone, system=row.System)
            fuel_rows.append(option)
    return result, pd.DataFrame(fuel_rows, columns=primary.columns)


def export_bundle(args, reference: Path) -> dict:
    output = args.out_root / "model_inputs"
    output_path, reference_path = output.resolve(), reference.resolve()
    if (output_path == reference_path or reference_path in output_path.parents
            or output_path in reference_path.parents):
        raise ValueError("Output must not overwrite the portable model reference")
    preflight_reference(args, reference)
    from regional_input_quality import check_prepared_methods
    regional_quality = check_prepared_methods(args)
    from model_variants import prepare_sources
    prepare_sources(args, reference)
    args.out_root.mkdir(parents=True, exist_ok=True)
    # Finish every transformation and check before replacing a previous export.
    # Keep unrelated user files, as the previous in-place exporter did.
    with TemporaryDirectory(dir=args.out_root, prefix="_model_export_") as folder:
        stage = Path(folder) / "model_inputs"
        if output.exists():
            shutil.copytree(output, stage, ignore=lambda directory, names:
                            [name for name in ("data", "h2res_inputs") if name in names]
                            if Path(directory) == output else [])
        (stage / "validation.json").unlink(missing_ok=True)
        report = None
        phase='building and validating native inputs'
        try:
            report = _export_bundle(args, reference, stage)
            if regional_quality:
                (stage / "regional_input_quality.json").write_text(json.dumps(regional_quality, indent=2), encoding="utf-8")
                report["regional_input_quality"] = regional_quality
                (stage / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            if getattr(args, "model_ready_package", False):
                phase='creating the native input folder and ZIP'
                from model_ready_package import build_package
                report["model_input_package"] = build_package(stage, report)
        except Exception as exc:
            from filesystem_publish import failure_details
            failure = dict(failure_details(exc,phase),previous_bundle_retained=True,
                           staging_folder=str(stage),output_folder=str(args.out_root))
            if (stage / "validation.json").exists():
                failure["validation"] = json.loads((stage / "validation.json").read_text(encoding="utf-8"))
            validated = bool(report and report.get("ready"))
            if (isinstance(exc, MemoryError) or validated) and stage.exists():
                prefix = "_unpublished_model_inputs_" if validated else "_incomplete_model_inputs_"
                recovery = args.out_root / (prefix + Path(folder).name.removeprefix("_model_export_"))
                stage.replace(recovery)
                failure["unvalidated_recovery_bundle"] = str(recovery)
                failure["recovery_input_coverage_passed"] = bool(validated)
            (args.out_root / "model_export_failure.json").write_text(json.dumps(failure, indent=2), encoding="utf-8")
            if isinstance(exc, MemoryError):
                raise MemoryError("Export exceeded available memory. Unvalidated work was preserved at "
                                  + failure.get("unvalidated_recovery_bundle", str(stage))) from exc
            raise
        # Keep the backup outside the temporary tree: if a Windows lock also
        # prevents rollback, context cleanup must not delete the previous data.
        if (stage / "data").is_dir():
            from native_data_delivery import publish_outputs
            native = Path(folder) / "data"
            shutil.copytree(stage / "data", native)
            summary = Path(folder) / "H2RES_DATA_manifest.json"
            summary.write_text(json.dumps({
                "data_folder": "data", "ready": report["ready"],
                "selected_configuration": json.loads((stage / "bundle_manifest.json").read_text(encoding="utf-8")),
                "validation": report,
            }, indent=2), encoding="utf-8")
            import gc
            gc.collect()
            try:
                publish_outputs([(stage, output), (native, args.out_root / "data"),
                                 (summary, args.out_root / summary.name)], args.out_root,
                                Path(folder).name.removeprefix("_model_export_"))
            except Exception as exc:
                # Publication may fail after all expensive transformations and
                # checks passed. Keep the completed bundle outside TemporaryDirectory
                # so that retrying publication never requires regeneration.
                recovery = args.out_root / ("_unpublished_model_inputs_" + Path(folder).name.removeprefix("_model_export_"))
                from filesystem_publish import failure_details
                failure = dict(failure_details(exc,'publishing the validated native data folder'),
                               cause=repr(exc.__cause__), previous_bundle_retained=True,
                               recovery_input_coverage_passed=bool(report.get("ready")),
                               validation=report)
                if stage.exists():
                    shutil.copytree(stage, recovery)
                    failure["unvalidated_recovery_bundle"] = str(recovery)
                if report.get('ready') and (recovery/'h2res_inputs/FILES.csv').is_file():
                    # A reader can leave a Windows handle on the original stage.
                    # The preserved copy has different paths and no such handles.
                    # Check its package hashes before trying that completed copy.
                    try:
                        from native_data_delivery import retry_prepared_publication
                        retry_prepared_publication(recovery,args.out_root)
                        print(f"Published the verified copy after a staging-folder lock: {args.out_root/'data'}",flush=True)
                        return report
                    except Exception as retry_error:
                        failure['publication_retry_error'] = str(retry_error)
                (args.out_root / "model_export_failure.json").write_text(json.dumps(failure, indent=2), encoding="utf-8")
                raise
            print(f"Ready-to-use H2RES data folder: {args.out_root / 'data'}", flush=True)
            (args.out_root / "model_export_failure.json").unlink(missing_ok=True)
            return report
        previous = args.out_root / ("_model_inputs_previous_" + Path(folder).name.removeprefix("_model_export_"))
        had_previous = output.exists()
        try:
            if had_previous:
                output.replace(previous)
            try:
                stage.replace(output)
            except OSError:
                if had_previous:
                    try:
                        previous.replace(output)
                    except OSError as recovery_error:
                        raise OSError(f"Export publication and rollback failed. Previous data remain at {previous}; close open files before restoring that folder.") from recovery_error
                raise
        except PermissionError as exc:
            raise PermissionError(f"Cannot publish {output}. Close files open in Excel or another application and retry; the previous bundle was retained.") from exc
        if had_previous:
            if previous.resolve().parent != args.out_root.resolve() or not previous.name.startswith("_model_inputs_previous_"):
                raise ValueError(f"Refusing to remove an export backup outside the output folder: {previous}")
            try:
                shutil.rmtree(previous)
            except OSError:
                print(f"Export completed; an open-file lock prevented removing the old backup at {previous}", flush=True)
    print(f"Model data bundle: {output / 'data'}\nValidation: {output / 'validation.json'}; ready={report['ready']}", flush=True)
    if "model_input_package" in report:
        package = report["model_input_package"]
        status = "input coverage passed" if package["ready"] else "INCOMPLETE INPUT COVERAGE"
        print(f"H2RES input files: {output / package['folder']}\nH2RES input ZIP: {output / package['archive']} ({status})", flush=True)
    (args.out_root / "model_export_failure.json").unlink(missing_ok=True)
    return report


def _export_bundle(args, reference: Path, output: Path) -> dict:
    """Build an export in an isolated staging directory; no live bundle writes."""
    output.mkdir(parents=True, exist_ok=True)
    data = output / "data"
    # Start from known current inputs every time; only this invocation's sectors
    # replace them. This prevents mixing old HU profiles with new HR generators.
    repairs = copy_baseline(reference, data)
    (output / "complex_generation.json").unlink(missing_ok=True)
    workbook_name = selected_workbook(args.efuels, args.industry_mode, args.industry_electricity_case)
    workbook = data / workbook_name
    updates = {}
    missing = []
    written = []
    sector_zones = {}

    def emit(name, frame, hourly=False):
        write_csv(frame, data / name, hourly)
        written.append(name)

    if "power" in args.sectors:
        generators = read_generated(args.out_root / "power" / "GENCO.csv")
        sector_zones["power"] = set(generators[["System", "Zone"]].drop_duplicates().itertuples(index=False, name=None))
        emit("generators.csv", generators)
        level = "individual" if args.power_output_level == "individual" else "aggregated"
        suffix = "_individual" if level == "individual" else ""
        profiles = [args.out_root / "power" / "vre" / level / f"AvailabilityFactors_VRE_{args.vre_year}.csv",
                    args.out_root / "power" / "hydro" / f"AvailabilityFactors_HROR_{args.hydro_year}{suffix}.csv"]
        curves = []
        for path in profiles:
            if path.exists():
                curves.append(read_generated(path, hourly=True))
            else:
                missing.append(str(path))
        if curves:
            combined = curves[0]
            for frame in curves[1:]:
                combined = combined.merge(frame, on="period", validate="one_to_one")
            emit("renewable_availability.csv", combined, True)
        inflows = args.out_root / "power" / "hydro" / f"ScaledInflows_{args.hydro_year}{suffix}.csv"
        if inflows.exists():
            emit("hydro_inflows.csv", read_generated(inflows, hourly=True), True)
        else:
            missing.append(str(inflows))
        demand = args.out_root / "power" / "demand" / f"electricity_demand_{args.electricity_demand_year}.csv"
        if demand.exists():
            frame = read_generated(demand, hourly=True).rename(columns={"el_dem_mw": "Power", "zone": "Zone"})
            emit("electricity_demand.csv", frame[["period", "Power", "System", "Zone"]], True)
        else:
            missing.append(str(demand))

    if "industry" in args.sectors:
        if args.industry_mode == "complex":
            base = args.out_root / "industry" / "combined"
            if getattr(args, "all_model_variants", False):
                from model_variants import complex_directory
                base = complex_directory(args, args.efuels, args.industry_electricity_case)
            generation = base / "complex_generation.json"
            if not generation.exists():
                raise ValueError("Regenerate complex industry from JRC sources before exporting; complex_generation.json is missing")
            details = json.loads(generation.read_text(encoding="utf-8"))
            if details["efuels"] != args.efuels or details["electricity_case"] != args.industry_electricity_case:
                raise ValueError("Generated complex industry variant differs from export settings; regenerate it with matching e-fuel and electricity options")
            # Keep the current model's repaired workbook and financial sheets.
            # Older cached industry exports may contain a legacy whole workbook.
            with pd.ExcelFile(base / "industry_inputs.xlsx") as generated_book:
                for sheet in ("Industry_data", "simple_industry", "industry_CC", "industry_heat_stor"):
                    if sheet in generated_book.sheet_names:
                        updates[sheet] = pd.read_excel(generated_book, sheet)
            updates["simple_industry"] = pooled_industry(updates["Industry_data"],read_generated(base/"industry_heat.csv"),
                                                        pd.read_excel(workbook,"simple_industry"))
            complex_name = selected_complex_workbook(args.efuels, args.industry_electricity_case)
            shutil.copy2(base / complex_name, data / complex_name)
            process = pd.read_excel(base / complex_name, "Process_data")
            from industry.generate_complex_industry_inputs import sync_costs
            sync_costs(workbook, pd.read_excel(base / complex_name, "complex_industry"))
            sector_zones["industry"] = set(process[["System", "zone"]].drop_duplicates().itertuples(index=False, name=None))
            shutil.copy2(generation, output / "complex_generation.json")
            written.extend([workbook_name, complex_name])
            for name in ("industry_heat.csv", "industry_electricity.csv"):
                emit(name, read_generated(base / name, hourly=True), True)
        else:
            base = args.out_root / "industry" / "combined"
            variant = "efuels" if args.efuels else "regular"
            if args.industry_mode == "categories":
                variant += "_heat_categories"
            frame = read_generated(base / f"Industry_data_{variant}.csv")
            sector_zones["industry"] = set(frame[["System", "zone"]].drop_duplicates().itertuples(index=False, name=None))
            updates["Industry_data"] = industry_parameters(frame, pd.read_excel(workbook, sheet_name="Industry_data"))
            profile_name = "industry_category_profiles.csv" if args.industry_mode == "categories" else "industry_heat.csv"
            updates["simple_industry"] = pooled_industry(updates["Industry_data"], read_generated(base / profile_name),
                                                        pd.read_excel(workbook, sheet_name="simple_industry"))
            for name in ("industry_heat.csv", "industry_category_profiles.csv", "industry_electricity.csv"):
                path = base / name
                if path.exists():
                    emit(name, read_generated(path, hourly=True), True)
                else:
                    missing.append(str(path))

    if "transport" in args.sectors:
        base = args.out_root / "transport" / "combined"
        fleet, fuels = transport_parameters(read_generated(base / "transport_all.csv"), pd.read_excel(workbook, "transport_all"),
                                           pd.read_excel(workbook, "transport_ICE_prim") if args.efuels else None)
        updates["transport_all"] = fleet
        sector_zones["transport"] = set(updates["transport_all"][["System", "zone"]].drop_duplicates().itertuples(index=False, name=None))
        if args.efuels:
            updates["transport_ICE_prim"] = fuels
        for name in ("transport_profiles.csv", "transport_demand.csv"):
            path = base / name
            if path.exists():
                emit(name, transport_identifiers(read_generated(path, hourly=True)), True)
            else:
                missing.append(str(path))

    if "heating" in args.sectors:
        base = args.out_root / "heating"
        for sheet in ("flex_tech_heat", "flex_tech_DH", "thermal_tech", "thermal_tech_DH", "solar_indv", "solar_DH"):
            updates[sheet] = read_generated(base / f"{sheet}.csv")
        sector_zones["heating"] = set(updates["thermal_tech"][["System", "zone"]].drop_duplicates().itertuples(index=False, name=None))
        for name in ("heating_individual.csv", "heating_district.csv", "heating_electricity.csv"):
            path = base / name
            if path.exists():
                emit(name, read_generated(path, hourly=True), True)
            else:
                missing.append(str(path))

    mapping_path = args.out_root / "_zone_maps" / "zone_map_common.csv"
    desired = set().union(*sector_zones.values()) if sector_zones else set()
    if mapping_path.exists():
        mapping = pd.read_csv(mapping_path)
        mapping = mapping.loc[mapping.country.isin(args.countries)]
        if not mapping.empty:
            system_col = "system_new" if "system_new" in mapping else "country"
            desired = set(mapping[[system_col, "zone"]].drop_duplicates().itertuples(index=False, name=None))
    if desired:
        active = pd.read_excel(workbook, "active_zones")
        active["active"] = "N"
        for system, zone in sorted(desired):
            select = active.System.eq(system) & active.zone.eq(zone)
            if select.any():
                active.loc[select, "active"] = "Y"
            else:
                active = pd.concat([active, pd.DataFrame([{"System": system, "zone": zone, "active": "Y"}])], ignore_index=True)
        updates["active_zones"] = active
    if updates:
        replace_sheets(workbook, updates)
    variants = []
    if getattr(args, "all_model_variants", False):
        from model_variants import update_workbooks
        variants = update_workbooks(args, data, updates, reference=reference)
        written.extend(v["technology_workbook"] for v in variants)
        if "industry" in args.sectors:
            written.extend(selected_complex_workbook(e, c) for e in (False, True)
                           for c in ("conservative", "technical_2050"))
        # Native variants share these filenames. The regular/category source
        # supplies common hourly shapes; complex process totals remain in its
        # own Process_data/Product_demand workbooks.
        if "industry" in args.sectors:
            base = args.out_root / "industry" / "combined"
            for name in ("industry_heat.csv", "industry_category_profiles.csv", "industry_electricity.csv"):
                emit(name, read_generated(base / name, hourly=True), True)
    from default_model_inputs import complete_defaults
    default_expansions = complete_defaults(data, desired, written, variants, workbook_name, updates)
    from power_input_links import synchronize as synchronize_power_inputs
    power_links = synchronize_power_inputs(data, reference, desired, [name for name in TECH_WORKBOOKS if (data/name).is_file()])
    written.extend(name for name in ['literature_fixed_opex.csv',*(entry['workbook'] for entry in power_links)] if name not in written)
    (output / "generator_input_links.json").write_text(json.dumps(power_links,indent=2),encoding="utf-8")
    from regional_network_inputs import synchronize as synchronize_networks
    network_links=synchronize_networks(data,desired,[name for name in TECH_WORKBOOKS if (data/name).is_file()])
    (output/'network_input_assumptions.json').write_text(json.dumps(network_links,indent=2),encoding='utf-8')
    from policy_input_links import synchronize as synchronize_policy_inputs
    policy_links=synchronize_policy_inputs(data,reference,desired)
    (output/'policy_input_assumptions.json').write_text(json.dumps(policy_links,indent=2),encoding='utf-8')
    if policy_links:written.extend(name for name in ('policy.xlsx','policy_efuel.xlsx') if name not in written)
    from industry.complex_regional_inputs import synchronize as synchronize_complex_activity
    complex_activity_repairs=[]
    for companion in data.glob('industry_complex*.xlsx'):
        notes=synchronize_complex_activity(companion)
        complex_activity_repairs.extend(dict(file=companion.name,**note) for note in notes)
    from scenario_config import apply_scenario
    settings = getattr(args, "scenario", None)
    if settings is None and args.industry_mode == "complex" and "industry" in args.sectors:
        # The launcher carries the explicit generated sector selection into the unchanged model.
        from scenario_config import resolve_scenario
        from types import SimpleNamespace
        policy_name = "policy_efuel.xlsx" if args.efuels else "policy.xlsx"
        years = pd.read_excel(data / policy_name, "setup").years_all.dropna().astype(int).tolist()
        settings = resolve_scenario(SimpleNamespace(efuels=args.efuels, planning_years=years))
    scenario = apply_scenario(output, workbook_name, settings, efuels=args.efuels,
                              industry_mode=args.industry_mode, electricity_case=args.industry_electricity_case)
    if scenario is None:
        from scenario_config import write_reference_launcher
        scenario = write_reference_launcher(output,workbook_name,efuels=args.efuels,industry_mode=args.industry_mode,
                                            electricity_case=args.industry_electricity_case)
    if variants and settings:
        from model_variants import apply_variant_investments
        apply_variant_investments(data, settings, variants, workbook_name,
                                  selected_complex_workbook(args.efuels, args.industry_electricity_case)
                                  if args.industry_mode == "complex" else None)
    reference_info = json.loads((reference / "manifest.json").read_text(encoding="utf-8"))
    from industry.fuel_representation import REGULAR_FUEL_METHOD
    manifest = {"model_version": reference_info.get("model_version", MODEL_VERSION), "generated_sectors": args.sectors,
                "scenario": scenario,
                "countries": args.countries, "industry_mode": args.industry_mode,
                "industry_electricity_case": args.industry_electricity_case,
                "efuels": args.efuels, "technology_workbook": workbook_name,
                "complex_workbook": selected_complex_workbook(args.efuels, args.industry_electricity_case) if args.industry_mode == "complex" else None,
                "policy_workbook": "policy_efuel.xlsx" if args.efuels else "policy.xlsx",
                "generated_files": written, "replaced_sheets": list(updates),
                "input_repairs": repairs,
                "sector_zones": {key: sorted(values) for key, values in sector_zones.items()},
                "reference_files": reference_info["files"],
                "data_layout": reference_info.get("data_layout"),
                "data_directories": reference_info.get("directories", []),
                "reference_model_root": reference_info.get("model_root"),
                "missing_generated_inputs": missing,
                "technology_variants": variants,
                "default_geography_assumptions": default_expansions,
                "variant_default_assumptions": getattr(args, "variant_default_assumptions", []),
                "generator_financial_link_method": "physical_generator_financial_links_v1",
                "generator_financial_links_file": "generator_input_links.json",
                "network_assumptions_file": "network_input_assumptions.json",
                "policy_assumptions_file":"policy_input_assumptions.json",
                "complex_zero_weight_activity_repairs":complex_activity_repairs,
                "industry_fuel_representation": {
                    "method": REGULAR_FUEL_METHOD,
                    "applies_to": "generated non-eFuel Industry_data and simple_industry; detailed complex process tables retain supported purchased heat",
                    "assumption": "Heat/waste useful service is reassigned to the local supported incumbent mix, excluding feedstocks and unbuilt technologies; explicit gas default if none exists.",
                    "conserved": "regional industry/category useful service and hourly demand",
                    "historical_electricity": "observed subtraction unchanged; reassigned electricity is additional modeled demand",
                } if "industry" in args.sectors else None,
                "note": "Other files and workbook sheets retain supplied model data and scenario assumptions."}
    (output / "bundle_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    report = validate_bundle(output, workbook_name, args.efuels, args.industry_mode, args.industry_electricity_case)
    if report.get("zones_without_sourced_generators"):
        print("Active zones with no sourced generator records (allowed): "
              + str(report["zones_without_sourced_generators"]), flush=True)
    if variants:
        validations = []
        for variant in variants:
            print("Validating native input variant: " + variant["technology_workbook"], flush=True)
            result = validate_bundle(output, variant["technology_workbook"], variant["efuels"],
                                     variant["industry_mode"], variant["industry_electricity_case"])
            validations.append(result)
            report["errors"].extend(variant["technology_workbook"] + ": " + error for error in result["errors"])
        for efuels in (False, True):
            name = selected_workbook(efuels, "complex")
            print('Validating native input variant: '+name+' (technical_2050)',flush=True)
            result = validate_bundle(output, name, efuels, "complex", "technical_2050")
            validations.append(result)
            report["errors"].extend(name + " (technical_2050): " + error for error in result["errors"])
        report["variants"] = validations
        (output / "variant_inventory.json").write_text(json.dumps(variants, indent=2), encoding="utf-8")
    provenance = []
    for name in reference_info["files"]:
        variant = next((v for v in variants if v["technology_workbook"] == name), None)
        if variant:
            provenance.append({"file": name, "source": "generated sector tables and default model assumptions",
                               "generated_sheets": variant["replaced_sheets"]})
        else:
            provenance.append({"file": name, "source": "generated" if name in written else "default model data"})
    (output / "input_provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    report["missing_generated_inputs"] = missing
    for sector, pairs in sector_zones.items():
        if pairs - desired:
            report["errors"].append(f"{sector} outputs contain zones outside the requested selection: {sorted(pairs - desired)}")
        if desired - pairs and sector != "power":
            report["errors"].append(f"{sector} outputs lack requested zones: {sorted(desired - pairs)}")
    report["ready"] = report["ready"] and not missing and not report["errors"]
    (output / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if not report["ready"]:
        for issue in (report["errors"] + missing)[:8]:
            print(f"  Incomplete: {issue}", flush=True)
    if args.require_model_ready and not report["ready"]:
        details = "; ".join((report["errors"] + missing)[:8])
        raise ValueError("Model bundle is incomplete; previous export retained. " + details)
    return report


def validate_bundle(output: Path, workbook_name: str, efuels: bool, industry_mode: str, electricity_case: str = "conservative") -> dict:
    """Check actual reader keys and coverage, without creating a solver model."""
    import gc
    try:
        with ExitStack() as books:
            return _validate_bundle(output, workbook_name, efuels, industry_mode, electricity_case, books)
    finally:
        gc.collect()


def _validate_bundle(output, workbook_name, efuels, industry_mode, electricity_case, books):
    data = output / "data"
    from excel_integrity import workbook_errors
    errors = [workbook_name + ": " + issue for issue in workbook_errors(data / workbook_name)]
    warnings = []
    book = books.enter_context(pd.ExcelFile(data / workbook_name))
    active = pd.read_excel(book, "active_zones")
    active = active.loc[active.active.astype(str).str.strip().str.upper().eq("Y"), ["System", "zone"]].dropna()
    zones = set(active.zone.astype(str))
    pairs = set(active.itertuples(index=False, name=None))
    if not pairs:
        errors.append("Technology workbook has no active zones")
    generators = pd.read_csv(data / "generators.csv")
    outside_files=[data/'outside_system_supply_shares.csv',data/'outside_system_normalized_curves.csv']
    if any(path.exists() for path in outside_files):
        if not all(path.exists() for path in outside_files):
            errors.append('Outside-system supply-share or normalized-curve file is missing')
        else:
            from native_input_checks import outside_supply_checks
            errors.extend(outside_supply_checks(*(pd.read_csv(path) for path in outside_files)))
    demand = pd.read_csv(data / "electricity_demand.csv")
    required = {"period", "Power", "System", "Zone"}
    if not required.issubset(demand):
        errors.append(f"electricity_demand.csv lacks {sorted(required - set(demand))}")
    else:
        for pair in pairs:
            subset = demand.loc[demand.System.eq(pair[0]) & demand.Zone.eq(pair[1])]
            if set(subset.period) != set(range(1, 8761)) or subset.period.duplicated().any():
                errors.append(f"electricity_demand.csv does not cover 8760 distinct hours for {pair}")
    generated_pairs = set(generators[["System", "Zone"]].drop_duplicates().itertuples(index=False, name=None))
    empty_generation = sorted(pairs - generated_pairs)
    if empty_generation:
        warnings.append("No sourced generator records in active zones " + str(empty_generation)
                        + "; these zones retain their demand and other model inputs.")
    metadata_path = output / "bundle_manifest.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    if "power" in metadata.get("generated_sectors", []) and generated_pairs - pairs:
        errors.append(f"Generated generator zones are inactive or absent in technology workbook: {sorted(generated_pairs - pairs)}")
    for issue in metadata.get("missing_generated_inputs", []):
        errors.append(f"Missing generated input: {issue}")
    policy_file=data/('policy_efuel.xlsx' if efuels else 'policy.xlsx')
    if policy_file.exists():
        with pd.ExcelFile(policy_file) as policy_book:
            if 'generation_targets' in policy_book.sheet_names:
                from policy_input_links import generation_checks
                errors.extend(generation_checks(policy_book.parse('generation_targets'),generators,pairs))
    policy_notes=output/'policy_input_assumptions.json'
    if policy_notes.exists():
        omitted=[r for r in json.loads(policy_notes.read_text(encoding='utf-8')) if not r['applied'] and r['workbook']==policy_file.name]
        if omitted:warnings.append('Unapplied reference generation calibration targets have no matching sourced generators: '+str([(r['System'],r['Fuel'],r['supplied_target_TWh']) for r in omitted])+'; see policy_input_assumptions.json')
    for filename in ("heating_individual.csv", "heating_district.csv", "cooling_individual.csv", "cooling_district.csv",
                     "industry_electricity.csv", "heating_electricity.csv", "solar_thermal_availability.csv"):
        frame = pd.read_csv(data / filename)
        if not zones.issubset(frame):
            errors.append(f"{filename} lacks active zones {sorted(zones - set(frame))}")
        try:
            model_calendar(frame)
        except ValueError as exc:
            errors.append(f"{filename}: {exc}")
    selected = generators.loc[generators.Zone.isin(zones)]
    if selected.unit_name.duplicated().any():
        errors.append("Active generator unit_name values are not unique")
    for filename, techs in (("renewable_availability.csv", {"PHOT", "WTON", "WTOF", "HROR"}),
                            ("hydro_inflows.csv", {"HDAM", "HPHS"})):
        frame = pd.read_csv(data / filename)
        units = set(selected.loc[selected.technology.isin(techs), "unit_name"])
        if not units.issubset(frame):
            errors.append(f"{filename} lacks generator columns {sorted(units - set(frame))}")
        try:
            model_calendar(frame)
        except ValueError as exc:
            errors.append(f"{filename}: {exc}")
        if units and units.issubset(frame):
            values = frame[sorted(units)].apply(pd.to_numeric, errors="coerce")
            if not np.isfinite(values).all().all() or values.lt(0).any().any():
                errors.append(f"{filename} has invalid active generator profile values")
            if filename == "renewable_availability.csv" and values.gt(1 + 1e-8).any().any():
                maximum = float(values.max().max())
                if maximum <= 1.02 and filename not in metadata.get("generated_files", []):
                    warnings.append(f"Reference {filename} retains historical factors up to {maximum}; source values were preserved.")
                else:
                    errors.append(f"{filename} has capacity factors greater than one")
    for sheet in ("Industry_data", "simple_industry", "industry_heat_stor", "industry_CC"):
        if sheet in book.sheet_names:
            try:
                table = pd.read_excel(book, sheet)
                validate_limits(table)
                if not efuels and sheet in {"Industry_data", "simple_industry"} and "fuel_type" in table:
                    from industry.fuel_representation import UNSUPPORTED_REGULAR
                    unsupported = sorted(set(table.fuel_type.dropna()) & UNSUPPORTED_REGULAR)
                    if unsupported:
                        errors.append(f"{sheet}: non-eFuel industry contains unsupported fuels {unsupported}; regenerate Industry")
            except ValueError as exc:
                errors.append(f"{sheet}: {exc}")
    profile_file = "industry_category_profiles.csv" if industry_mode == "categories" else "industry_heat.csv"
    profiles = pd.read_csv(data / profile_file)
    industry = pd.read_excel(book, "Industry_data").dropna(subset=["Industry", "unit_name"])
    from native_input_checks import industry_checks, generator_checks
    simple = pd.read_excel(book,"simple_industry") if "simple_industry" in book.sheet_names else pd.DataFrame()
    industry_errors,industry_audit = industry_checks(industry,simple,profiles,industry_mode)
    errors.extend(industry_errors)
    generator_audit = {}
    if {"tech_cost_years","cap_inv_lim"}.issubset(book.sheet_names):
        costs,limits = pd.read_excel(book,"tech_cost_years"),pd.read_excel(book,"cap_inv_lim")
        available = pd.to_numeric(costs.get('year',pd.Series(dtype=float)),errors='coerce').dropna()
        years = list(range(int(available.min()),int(available.max())+1)) if len(available) else []
        power_errors,generator_audit = generator_checks(generators,costs,limits,years,zones)
        errors.extend(power_errors)
    else:
        errors.append("Native technology workbook lacks generator cost or annual investment-limit sheets")
    network_audit={}
    if {'transmission','transmission_outside'}.issubset(book.sheet_names):
        from regional_network_inputs import checks as network_checks
        network_errors,network_audit=network_checks(pd.read_excel(book,'transmission'),pd.read_excel(book,'transmission_outside'),pairs)
        errors.extend(network_errors)
    else:
        errors.append('Native technology workbook lacks internal/external network inputs')
    if industry_mode == "categories" and "category" not in industry:
        errors.append("Category industry data lacks the category column")
    for pair in pairs:
        table = profiles.loc[profiles.System.eq(pair[0]) & profiles.zone.eq(pair[1])]
        if len(table) != 8760 or table.period.duplicated().any():
            errors.append(f"{profile_file} lacks 8760 unique hours for {pair}")
        rows = industry.loc[industry.System.eq(pair[0]) & industry.zone.eq(pair[1])]
        if rows.empty:
            errors.append(f"Industry_data has no equipment for {pair}")
        if industry_mode == "categories" and "category" in rows:
            columns = set(rows.Industry + "[" + rows.category.astype(str) + "]")
        else:
            columns = set(rows.Industry) - {"all", "remainder"}
        if not columns.issubset(profiles):
            errors.append(f"{profile_file} lacks industry columns {sorted(columns - set(profiles))}")
    transport = pd.read_excel(book, "transport_all")
    transport_curves = {name: pd.read_csv(data / name) for name in ("transport_profiles.csv", "transport_demand.csv")}
    for pair in pairs:
        fleet = transport.loc[transport.System.eq(pair[0]) & transport.zone.eq(pair[1])]
        if fleet.empty:
            errors.append(f"transport_all has no equipment for {pair}")
        for name, curve in transport_curves.items():
            local = curve.loc[curve.System.eq(pair[0]) & curve.zone.eq(pair[1])]
            if len(local) != 8760 or local.period.duplicated().any():
                errors.append(f"{name} lacks 8760 unique hours for {pair}")
            if name == "transport_demand.csv":
                expected = set(fleet.sector)
            else:
                expected = {str(row.compat_parent) if pd.notna(getattr(row, "compat_parent", np.nan)) else row.unit_name
                            for row in fleet.itertuples(index=False)}
            if not expected.issubset(curve):
                errors.append(f"{name} lacks transport columns {sorted(expected - set(curve))}")
    if industry_mode == "complex":
        filename = selected_complex_workbook(efuels, electricity_case)
        complex_book = books.enter_context(pd.ExcelFile(data / filename))
        for sheet, columns in {
            "complex_industry": {"System", "zone", "Industry", "branch", "component", "unit_name", "efficiency", "cap_mw"},
            "Process_data": {"System", "zone", "Industry", "branch", "component", "energy_intensity_MWh_per_activity"},
            "Product_demand": {"System", "zone", "Industry", "branch", "product_unit"},
            "CC": {"System", "zone", "Industry", "branch", "CC_capture_rate"},
        }.items():
            frame = pd.read_excel(complex_book, sheet)
            if not columns.issubset(frame):
                errors.append(f"{filename}/{sheet} lacks {sorted(columns - set(frame))}")
            available = set(frame[["System", "zone"]].drop_duplicates().itertuples(index=False, name=None))
            if not pairs.issubset(available):
                errors.append(f"{filename}/{sheet} lacks calibrated process data for {sorted(pairs - available)}")
            validate_limits(frame)
            if sheet in {'Process_data','Product_demand'}:
                from industry.complex_regional_inputs import zero_weight_activity
                _,bad=zero_weight_activity(frame,sheet)
                if bad:errors.append(f'{filename}/{sheet} has positive indexed activity in {bad} zero-allocation rows')
    warnings.append("Coverage validation does not solve the optimization model or certify scenario feasibility.")
    scenario_file = output / "scenario.json"
    if industry_mode == "complex" and (output / "complex_generation.json").exists() and not scenario_file.exists():
        errors.append("Generated complex inputs require scenario.json and the launcher to apply the generated sector selection")
    if scenario_file.exists():
        scenario = json.loads(scenario_file.read_text(encoding="utf-8"))
        policy = pd.read_excel(data / ("policy_efuel.xlsx" if efuels else "policy.xlsx"), "setup")
        if policy.years_all.astype(int).tolist() != scenario["years"]:
            errors.append("Scenario planning years differ from policy/setup")
        for filename in ("run_model_scenario.py", "scenario_runtime.py"):
            if not (output / filename).is_file():
                errors.append(f"Scenario launcher dependency is missing: {filename}")
        warnings.append("Run through run_model_scenario.py to apply the selected model flags and any scenario constraints.")
    return {"ready": not errors, "technology_workbook": workbook_name, "efuels": efuels,
            "industry_mode": industry_mode, "industry_electricity_case": electricity_case,
            "active_zones": sorted(zones), "zones_without_sourced_generators": [list(pair) for pair in empty_generation],
            "industry_accounting": industry_audit, "generator_financial_keys": generator_audit,
            "regional_network": network_audit,
            "errors": errors, "warnings": warnings}
