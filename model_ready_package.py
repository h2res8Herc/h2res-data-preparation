"""Create a focused native H2RES input folder and ZIP from a prepared bundle."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd

FOLDER = "h2res_inputs"
ARCHIVE = "H2RES_model_inputs.zip"
SECTORS = ("power", "industry", "transport", "heating")
DISTRIBUTIONS = {
    "electricity_demand.csv", "renewable_availability.csv", "hydro_inflows.csv",
    "industry_heat.csv", "industry_category_profiles.csv", "industry_electricity.csv",
    "transport_demand.csv", "transport_profiles.csv", "heating_individual.csv",
    "heating_district.csv", "heating_electricity.csv", "cooling_individual.csv",
    "cooling_district.csv", "solar_thermal_availability.csv", "outside_system_normalized_curves.csv",
}


def build_package(bundle: Path, report: dict | None = None) -> dict:
    """Copy native files byte-for-byte; leave the source bundle's data untouched.

    When called by the exporter this runs inside its protected staging folder.
    The standalone command rechecks coverage before packaging existing files.
    """
    from model_input_bundle import MODEL_VERSION, TECH_WORKBOOKS, selected_complex_workbook, selected_workbook, sha256, validate_bundle

    bundle = bundle.resolve()
    metadata = json.loads((bundle / "bundle_manifest.json").read_text(encoding="utf-8"))
    saved_report = json.loads((bundle / "validation.json").read_text(encoding="utf-8"))
    mode = metadata.get("industry_mode", saved_report["industry_mode"])
    efuels = metadata.get("efuels", saved_report["efuels"])
    case = metadata.get("industry_electricity_case", saved_report.get("industry_electricity_case", "conservative"))
    technology = selected_workbook(efuels, mode, case)
    if saved_report["technology_workbook"] != technology:
        raise ValueError("Bundle validation and selected technology workbook disagree; re-export with matching settings")
    if report is None:
        report = validate_bundle(bundle, technology, efuels, mode, case)
    if report["technology_workbook"] != technology:
        raise ValueError("Package coverage report describes another technology workbook")
    issues = list(report.get("errors", []))
    missing = list(report.get("missing_generated_inputs", [])) + list(metadata.get("missing_generated_inputs", []))
    if not report.get("ready") or issues or missing:
        details = issues + ["Missing generated input: " + str(name) for name in dict.fromkeys(missing)]
        raise ValueError("H2RES input package was not published because input validation failed. "
                         + ("; ".join(details[:8]) if details else "Complete input coverage is required."))
    reference_files = metadata.get("reference_files")
    if reference_files is None:
        reference_files = json.loads((bundle / "reference_manifest.json").read_text(encoding="utf-8"))["files"]
    names = set(reference_files)
    names.update(name for name in metadata.get("generated_files", []) if name.endswith(".csv"))
    names.update([technology, "policy.xlsx", "policy_efuel.xlsx", "policy_fuels.xlsx", "h2_terminals.xlsx"])
    if mode == "complex":
        names.add(selected_complex_workbook(efuels, case))
    data = bundle / "data"
    for name in names:
        path = data / name
        if not path.resolve().is_relative_to(data.resolve()):
            raise ValueError(f"Input filename points outside the bundle: {name}")
        if not path.is_file():
            raise FileNotFoundError(f"Native input required for packaging is missing: {path}")

    # Keep staging beside the bundle on the same volume. Nesting another
    # package under model_inputs can push the technical-2050 path to MAX_PATH
    # even though both the source and final paths fit on older Windows setups.
    print('Packaging native H2RES inputs...',flush=True)
    with TemporaryDirectory(dir=bundle.parent, prefix="_ip_") as folder:
        delivery = Path(folder) / FOLDER
        (delivery / "data").mkdir(parents=True)
        for name in metadata.get("data_directories", []):
            path = delivery / "data" / name
            if not path.resolve().is_relative_to((delivery / "data").resolve()):
                raise ValueError(f"Input subdirectory points outside the bundle: {name}")
            path.mkdir(parents=True, exist_ok=True)
        for name in sorted(names):
            destination = delivery / "data" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(data / name, destination)
        for name in ("bundle_manifest.json", "reference_manifest.json", "scenario.json", "complex_generation.json",
                     "variant_inventory.json", "input_provenance.json", "regional_input_quality.json", "generator_input_links.json", "network_input_assumptions.json",
                     "native_reader_verification.json", "policy_input_assumptions.json"):
            if (bundle / name).is_file():
                shutil.copy2(bundle / name, delivery / name)
        if (bundle / "scenario.json").is_file():
            for name in ("run_model_scenario.py", "scenario_runtime.py"):
                if not (bundle / name).is_file():
                    raise FileNotFoundError(f"Scenario package dependency is missing: {name}")
                shutil.copy2(bundle / name, delivery / name)
        (delivery / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        if report.get("model_reader", {}).get("reader_completed") and (bundle / "scenario_reader_validation.json").is_file():
            shutil.copy2(bundle / "scenario_reader_validation.json", delivery / "scenario_reader_validation.json")
        generated = set(metadata.get("generated_sectors", []))
        flags = {"model_efuel": efuels, "model_industry_categories": mode == "categories",
                 "industry_storage": mode == "categories", "model_transport_and_industry": True,
                 "model_complex_industry": mode == "complex", "model_complex_non_metallic_minerals": mode == "complex",
                 "industry_category_electricity_case": case, "industry_complex_electricity_case": case}
        selection = dict(model_version=metadata.get("model_version", MODEL_VERSION),
                         technology_workbook="data/" + technology,
                         policy_workbook="data/" + ("policy_efuel.xlsx" if efuels else "policy.xlsx"),
                         industry_mode=mode, efuels=efuels, industry_electricity_case=case,
                         model_flags=flags, countries=metadata.get("countries", []),
                         active_zones=report.get("active_zones", []),
                         sector_sources={name: "generated" if name in generated else "portable reference" for name in SECTORS},
                         scenario_launcher_required=(delivery / "scenario.json").is_file(),
                         ready=bool(report["ready"]))
        variants = metadata.get("technology_variants", [])
        selection["updated_technology_workbooks"] = ["data/" + v["technology_workbook"] for v in variants] or ["data/" + technology]
        selection["technology_variants"] = variants
        selection["reference_model_root"] = metadata.get("reference_model_root")
        expected_files = set(reference_files)
        actual_files = {path.relative_to(delivery / "data").as_posix() for path in (delivery / "data").rglob("*") if path.is_file()}
        layout = dict(matches_reference=actual_files == expected_files, reference_model=metadata.get("reference_model_root"),
                      missing_files=sorted(expected_files - actual_files), extra_files=sorted(actual_files - expected_files),
                      expected_files=len(expected_files), exported_files=len(actual_files))
        if metadata.get("data_layout") == "model-directory-mirror" and not layout["matches_reference"]:
            raise ValueError(f"Generated data folder differs from the model data layout: {layout}")
        (delivery / "model_input_selection.json").write_text(json.dumps(selection, indent=2), encoding="utf-8")
        status = "INPUT COVERAGE PASSED" if report["ready"] else "INCOMPLETE INPUT COVERAGE"
        readme = ["# H2RES native model input files", "", "**" + status + "**", "",
                  f"Selected technology workbook: `data/{technology}`.", "",
                  "The workbook contains the selected technology, industry, transport and heating sheets. "
                  "Hourly demand, availability and distribution tables are in `data/*.csv`, using the model's native filenames and calendar.", "",
                  "The complete model data tree is retained, including inactive technology workbooks, `sources` and `variants`. " +
                  ("All native technology variants receive the prepared country data and their matching industry/e-fuel assumptions. "
                   "Choose the corresponding model flags listed in variant_inventory.json." if variants else
                   "The selected workbook listed above receives the generated sector data; other variants retain reference data. Re-export after changing the model configuration."), "",
                  "Copy/use the contents of `data` with a separate H2RES installation configured for the flags in "
                  "`model_input_selection.json`. This package prepares inputs; it does not execute an optimization.", "",
                  "## Sector provenance", ""]
        readme += [f"- {name}: {selection['sector_sources'][name]}." for name in SECTORS]
        readme += ["", "Unselected sectors retain portable-reference observations and assumptions. "
                   "Inspect `bundle_manifest.json` for generated files, replaced sheets and source hashes.", "",
                   "`validation.json` reports input coverage. Passing coverage does not certify scenario feasibility."]
        if selection["scenario_launcher_required"]:
            readme += ["", "Use the included launcher with the separate model to apply the selected flags, "
                       "generated plant policy aliases and the legacy regional industry-reader correction in memory. "
                       "An uncorrected model started directly from main.py does not apply that correction.","",
                       'From this folder, using the model Python environment: `python run_model_scenario.py --model-root "D:\\POSAO\\H2RES_2.11.2026_novi" --bundle .`. Add `--solve` to optimize.']
        if not report["ready"]:
            readme += ["", "## Inputs to complete", ""]
            readme += ["- " + str(issue) for issue in report.get("errors", [])]
            readme += ["- Missing generated input: " + str(issue) for issue in report.get("missing_generated_inputs", [])]
        (delivery / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")

        records = []
        for path in sorted((delivery / "data").rglob("*")):
            if not path.is_file():
                continue
            name = path.relative_to(delivery / "data").as_posix()
            role = "selected technology workbook" if name == technology else "generated technology variant" if any(v["technology_workbook"] == name for v in variants) else "reference technology workbook" if name in TECH_WORKBOOKS else "hourly distribution/profile" if name in DISTRIBUTIONS else "supporting model input"
            records.append(dict(file="data/" + name, role=role, bytes=path.stat().st_size, sha256=sha256(path)))
        with (delivery / "FILES.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["file", "role", "bytes", "sha256"])
            writer.writeheader(); writer.writerows(records)
        with pd.ExcelFile(data / technology) as workbook:
            sheets = workbook.sheet_names
        package = dict(format="H2RES_native_inputs_v2", created_utc=datetime.now(timezone.utc).isoformat(),
                       **selection, technology_sheets=sheets, data_layout=layout, files=records)
        (delivery / "package_manifest.json").write_text(json.dumps(package, indent=2), encoding="utf-8")
        archive = Path(folder) / ARCHIVE
        with ZipFile(archive, "w", ZIP_DEFLATED) as target:
            for path in sorted(delivery.rglob("*")):
                if path.is_file():
                    target.write(path, (Path(FOLDER) / path.relative_to(delivery)).as_posix())
        with ZipFile(archive) as target:
            if target.testzip() is not None:
                raise ValueError("Native model input archive integrity check failed")
        archive.replace(delivery / ARCHIVE)
        # Publish the folder and its ZIP together, including for standalone use.
        existing = bundle / FOLDER
        backup = bundle / ("_h2res_inputs_previous_" + Path(folder).name.removeprefix("_ip_"))
        had_previous = existing.exists()
        if existing.exists():
            if existing.is_symlink() or existing.resolve().parent != bundle:
                raise ValueError("Refusing to replace a package folder outside its bundle")
            existing.replace(backup)
        try:
            from filesystem_publish import replace_with_retry
            replace_with_retry(delivery, existing)
        except OSError:
            if had_previous:
                try:
                    backup.replace(existing)
                except OSError as exc:
                    raise OSError(f"Package publication failed. Previous package remains at {backup}") from exc
            raise
        if had_previous:
            if backup.resolve().parent != bundle or not backup.name.startswith("_h2res_inputs_previous_"):
                raise ValueError("Refusing to remove a package backup outside its bundle")
            try:
                shutil.rmtree(backup)
            except OSError:
                print(f"Package completed; previous copy remains at {backup} because an open file prevented cleanup")
    return dict(folder=FOLDER, archive=FOLDER + "/" + ARCHIVE, ready=bool(report["ready"]), data_files=len(records), technology_workbook=technology)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True, help="Existing model_inputs folder with manifest and validation")
    args = parser.parse_args()
    try:
        result = build_package(args.bundle)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(2, f"ERROR: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
