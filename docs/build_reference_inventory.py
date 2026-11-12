"""Read the preparation/model sources and generate documentation inventories.

No model module is imported, no model is built, and live input files are read only.
"""
from __future__ import annotations
import argparse
import ast
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import quote

from openpyxl import load_workbook

DOCS = Path(__file__).resolve().parent
ROOT = DOCS.parent


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_csv(name, rows, columns):
    with (DOCS / "inventory" / name).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def text_expr(node):
    return ast.unparse(node).replace("\n", " ") if node is not None else ""


class CallInventory(ast.NodeVisitor):
    def __init__(self, filename):
        self.filename = filename
        self.context = []
        self.rows = []
        self.variables = []

    def visit_If(self, node):
        self.context.append(text_expr(node.test))
        for item in node.body: self.visit(item)
        self.context.pop()
        self.context.append("else: " + text_expr(node.test))
        for item in node.orelse: self.visit(item)
        self.context.pop()

    def visit_FunctionDef(self, node):
        self.context.append("function " + node.name)
        self.generic_visit(node)
        self.context.pop()

    def visit_Call(self, node):
        if isinstance(node.func, (ast.Attribute, ast.Name)):
            method = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            kw = {k.arg: k.value for k in node.keywords}
            if method in ("addConstr", "addConstrs", "addLConstr", "addQConstr", "_add_industry_named_constraints"):
                self.rows.append(dict(file=self.filename, line=node.lineno, method=method,
                                      name=text_expr(kw.get("name")), context=" | ".join(self.context)))
            if method in ("addVar", "addVars", "_add_vars"):
                self.variables.append(dict(file=self.filename, line=node.lineno, method=method,
                                           name=text_expr(kw.get("name")), vtype=text_expr(kw.get("vtype")) or "Gurobi default continuous",
                                           lower_bound=text_expr(kw.get("lb")) or "Gurobi default 0",
                                           upper_bound=text_expr(kw.get("ub")) or "Gurobi default infinity",
                                           context=" | ".join(self.context)))
        self.generic_visit(node)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-root", type=Path, default=Path(r"D:\POSAO\H2RES_12.11.2026"))
    parser.add_argument("--date", default="2026-11-12")
    args = parser.parse_args()
    model = args.model_root.resolve()
    (DOCS / "inventory").mkdir(parents=True, exist_ok=True)
    runtime = ["main.py", "policy/model_policy.py", "policy/runtime_policy.py", "policy/transport_pathways.py"]
    runtime += ["scripts/" + name for name in (
        "read_process_data.py", "reading_prev_and_vars_def_dual_industry_categories1.py", "energy_accounting.py",
        "energy_balance_audit.py", "scoped_policy.py", "network_checks.py", "solution_quality.py",
        "Build_model_dual_industry_categories_named_debug.py", "CAPEX_OPEX_Gurobi_settings_dual_industry_categories1.py",
        "complex_industry_support.py", "complex_industry_accounting.py", "complex_industry_investment_limits.py",
        "industry_heat_pumps.py", "industry_annual_s_curve.py", "transport_pathways.py", "transport_emissions.py",
        "transport_annual_history.py", "transport_sampling.py", "scaled_transport_variables.py", "heating_history.py",
        "h2_terminals.py", "flex_asset_data.py", "physical_solution_audit.py", "investment_windows.py",
        "run_stage2_rolling_dispatch.py", "export_stage2_dispatch_bundle.py", "export_plot_myopic_step_shadowprice_fixed.py",
        "export_plot_PF_new.py", "export_plot_rolling_stitched.py", "export_plot.py", "combine_plot.py")]
    runtime += ["scripts/" + name for name in (
        "electricity_dsm.py", "electricity_cbam.py", "industrial_carbon_balances.py",
        "simple_industry_inputs.py", "simple_industry_trade_inputs.py", "simple_industry_model.py",
        "simple_industry_policy.py", "simple_industry_results.py", "hydrogen_supply_accounting.py",
        "numeric_scaling.py", "transport_history.py")]
    runtime += ["h2res_gui_complete.py", "h2res_web_gui.py"]
    constraints, variables, settings, flags, hashes, urls = [], [], [], [], {}, []
    prep = ["generate_all_sector_inputs.py", "h2res_input_gui.py", "preparation_dependencies.py", "model_input_bundle.py",
            "h2res_input_schema.py", "scenario_config.py", "scenario_runtime.py", "run_model_scenario.py",
            "industry/generate_industry_inputs_standalone.py", "industry/generate_complex_industry_inputs.py",
            "industry/complex_sources.py", "transport/script/generate_transport_inputs_standalone.py",
            "heating/generate_heating_inputs_standalone.py", "power/generators/generate_genco_power_sector.py",
            "power/generators/build_genco_union_plus_template_defaults_all.py",
            "power/hydro/generate_hydro_inputs_standalone.py", "power/demand/generate_electricity_demand_standalone.py",
            "power/VRES_distributions/build_vre_capacity_weighted_cf_from_schema_openmeteo_weighted.py"]
    for kind, base, names in [("model", model, runtime), ("preparation", ROOT, prep)]:
        for name in names:
            path = base / name
            if not path.exists(): continue
            payload = path.read_text(encoding="utf-8-sig")
            hashes[kind + "/" + name] = digest(path)
            tree = ast.parse(payload)
            if kind == "model":
                visitor = CallInventory(name); visitor.visit(tree)
                constraints += visitor.rows; variables += visitor.variables
            for n in tree.body:
                if isinstance(n, ast.Assign) and (kind == "model" and name.startswith("policy/") or name == "main.py"):
                    for target in n.targets:
                        if isinstance(target, ast.Name):
                            settings.append(dict(file=name, line=n.lineno, name=target.id, value=text_expr(n.value)))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) < 6000:
                    for url in re.findall(r"https?://[^\s\"'<>)}]+", node.value):
                        urls.append(dict(component=kind, file=name, line=node.lineno, url=url.rstrip(".,;")))
                if kind == "preparation" and isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument":
                    options = [a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
                    kw = {k.arg: text_expr(k.value) for k in node.keywords}
                    flags.append(dict(file=name, line=node.lineno, options=", ".join(options),
                                      default=kw.get("default", "argparse default"), choices=kw.get("choices", ""),
                                      action=kw.get("action", "store"), help=kw.get("help", "")))
    write_csv("model_constraint_calls.csv", constraints, ["file", "line", "method", "name", "context"])
    write_csv("model_variable_calls.csv", variables, ["file", "line", "method", "name", "vtype", "lower_bound", "upper_bound", "context"])
    write_csv("model_configuration.csv", settings, ["file", "line", "name", "value"])
    write_csv("preparation_cli_options.csv", flags, ["file", "line", "options", "default", "choices", "action", "help"])
    write_csv("source_urls_from_code.csv", urls, ["component", "file", "line", "url"])

    for relative in ('requirements_local_reference.txt', 'docs/UNIFIED_MODEL.md', 'docs/SIMPLE_INDUSTRY.md',
                     'docs/ELECTRICITY_DSM.md', 'data/README.md', 'reports/unified_integration/README.md'):
        path = model / relative
        if path.is_file(): hashes['model/' + relative] = digest(path)
    books, sheets, references, schemas, files = [], [], [], [], []
    for path in sorted((model / "data").rglob("*")):
        if not path.is_file(): continue
        relative = path.relative_to(model / "data").as_posix()
        files.append(dict(file=relative, bytes=path.stat().st_size, sha256=digest(path)))
        if path.suffix.lower() == ".csv":
            with path.open(encoding="utf-8-sig", newline="") as stream:
                header = next(csv.reader(stream), [])
            schemas.append(dict(file=relative, column_count=len(header), columns=header))
        if path.suffix.lower() != ".xlsx": continue
        book = load_workbook(path, read_only=True, data_only=True)
        books.append(dict(file=relative, sheets=book.sheetnames))
        for sheet in book:
            header = next(sheet.values, ())
            columns = [str(v) if v is not None else "" for v in header]
            sheets.append(dict(file=relative, sheet=sheet.title, rows=sheet.max_row - 1 if sheet.max_row is not None else "not stored in workbook",
                               columns=sheet.max_column if sheet.max_column is not None else len(columns),
                               headers=json.dumps(columns, ensure_ascii=False)))
            if any(token in sheet.title.casefold() for token in ("ref", "source", "literature", "method", "assum", "compatib", "heat_pumps", "limit")):
                for row in sheet.iter_rows():
                    for cell in row:
                        if isinstance(cell.value, str):
                            for url in re.findall(r"https?://[^\s\"'<>]+", cell.value):
                                references.append(dict(file=relative, sheet=sheet.title, cell=cell.coordinate,
                                                       url=url.rstrip(".,;)"), context=cell.value[:1600]))
        book.close()
    write_csv("model_data_files.csv", files, ["file", "bytes", "sha256"])
    write_csv("workbook_schema.csv", sheets, ["file", "sheet", "rows", "columns", "headers"])
    write_csv("workbook_reference_urls.csv", references, ["file", "sheet", "cell", "url", "context"])
    (DOCS / "inventory/csv_schema.json").write_text(json.dumps(schemas, ensure_ascii=False, indent=2), encoding="utf-8")
    (DOCS / "inventory/model_workbooks.json").write_text(json.dumps(books, indent=2), encoding="utf-8")
    manifest = dict(documentation_date=args.date, created_utc=datetime.now(timezone.utc).isoformat(),
                    model_root=str(model), preparation_root=str(ROOT), source_hashes=hashes,
                    constraint_call_sites=len(constraints), variable_call_sites=len(variables),
                    configuration_assignments=len(settings), cli_options=len(flags), model_data_files=len(files),
                    workbook_sheets=len(sheets), workbook_reference_occurrences=len(references),
                    notice="Static source/input inventory. Call sites are not instantiated model rows or columns. No optimization executed.")
    (DOCS / "inventory/documented_version.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    lines = ["# Code and configuration reference", "", "Generated by `build_reference_inventory.py` from the documented local copy.", "",
             "These are static call sites. Loops and flags determine the instantiated optimization model; counts are not solver matrix dimensions.", "",
             "## Configuration snapshot", "", "| Source | Setting | Value |", "|---|---|---|"]
    for row in settings:
        lines.append(f"| `{row['file']}:{row['line']}` | `{row['name']}` | `{row['value'].replace('|', '&#124;')}` |")
    lines += ["", "## Constraint families and locations", "", "See [full constraint inventory](inventory/model_constraint_calls.csv) for flag/function context.", "",
              "| Source | Line | Name / naming expression |", "|---|---:|---|"]
    for row in constraints:
        lines.append(f"| `{row['file']}` | {row['line']} | `{row['name'].replace('|', '&#124;') or '(unnamed)'}` |")
    lines += ["", "## Variable definitions", "", "See [variable inventory](inventory/model_variable_calls.csv) for bounds, types and flag context.", "",
              "| Source | Line | Name / naming expression | Type |", "|---|---:|---|---|"]
    for row in variables:
        lines.append(f"| `{row['file']}` | {row['line']} | `{row['name'].replace('|', '&#124;') or '(unnamed)'}` | `{row['vtype']}` |")
    (DOCS / "CODE_REFERENCE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in manifest.items() if k not in ("source_hashes",)}, indent=2))


if __name__ == "__main__": main()
