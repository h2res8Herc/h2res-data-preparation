"""Extract the handoff's pure calculation functions without running migrations."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    handoff = ROOT / "handoff"
    destination = ROOT / "methods"
    destination.mkdir(exist_ok=True)
    sources = {
        "jrc_source.py": ("model/scripts/expand_complex_industry_sectors.py", None),
        "fuel_policy.py": ("model/scripts/update_industry_fuel_compatibility.py", {
            "LIGNIN_ADDITIONAL_SHARE", "COMMON", "HEAT", "SOLID", "LIQUID", "COMBUSTIBLE", "ALTERNATIVE",
            "FAMILIES", "BLOCKED", "CHEMICAL_ROUTE", "OIL_SOURCE", "classify", "fractions", "service_pools", "ceiling"}),
        "electricity_policy.py": ("preparation_history/analysis/complex_electricity_review_2026_10_31/review_complex_electricity.py",
                                   {"MATURE", "envelope"}),
        "heat_pump_policy.py": ("preparation_history/scripts/update_all_industry_share_limits.py", {"HP_FIELDS", "hp_eligibility"}),
    }
    provenance = {}
    for target, (relative, selected) in sources.items():
        source = handoff / relative
        tree = ast.parse(source.read_text(encoding="utf-8-sig"))
        nodes = [] if selected is None else ast.parse("import re").body
        for node in tree.body:
            if selected is None:
                if isinstance(node, ast.FunctionDef) and node.name == "build_workbook":
                    break
                nodes.append(node)
            else:
                names = {node.name} if isinstance(node, ast.FunctionDef) else {
                    item.id for item in node.targets if isinstance(item, ast.Name)} if isinstance(node, ast.Assign) else set()
                if names & selected:
                    nodes.append(node)
        adaptations = []
        if target == "jrc_source.py":
            # Optional, explicit sector blend evidence extends the original strict
            # single-class proof without altering its original default behavior.
            for node in nodes:
                if isinstance(node, ast.FunctionDef) and node.name == "extract_source":
                    node.args.args.append(ast.arg(arg="waste_proof_by_sector"))
                    node.args.defaults.append(ast.Constant(None))
                    for item in ast.walk(node):
                        if isinstance(item, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "proof" for t in item.targets):
                            item.value = ast.parse("(waste_proof_by_sector or {}).get((code, reference_year), waste_proof.get(reference_year, {}))", mode="eval").body
                        if isinstance(item, ast.Assign) and any(isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant) and t.slice.value == "waste_split_source" for t in item.targets):
                            item.value = ast.BoolOp(op=ast.Or(), values=[ast.parse("proof.get('basis_note')", mode="eval").body, item.value])
            adaptations = ["Optional waste_proof_by_sector overrides only the explicitly supplied sector/year waste proof; strict original behavior is the default."]
        payload = (f'# Pure methods extracted from the supplied handoff: {relative}\n'
                   '# No installer, workbook migration, or historical entry point is executed.\n'
                   + ast.unparse(ast.Module(body=nodes, type_ignores=[])) + "\n")
        (destination / target).write_text(payload, encoding="utf-8")
        provenance[target] = {"handoff_path": relative, "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                              "extracted_sha256": hashlib.sha256(payload.encode()).hexdigest(),
                              "functions": [node.name for node in nodes if isinstance(node, ast.FunctionDef)], "local_adaptations": adaptations}
    (destination / "__init__.py").write_text('"""Provenance-preserving pure methods from the industry handoff."""\n', encoding="utf-8")
    (destination / "METHOD_PROVENANCE.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    print(f"Prepared {len(sources)} pure method modules in {destination}")


if __name__ == "__main__":
    main()
