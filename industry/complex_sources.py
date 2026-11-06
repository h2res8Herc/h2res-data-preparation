"""Resolve and validate the three public JRC-IDEES industry source workbooks."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import urllib.request
from zipfile import ZipFile
import xml.etree.ElementTree as ET
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from model_input_bundle import sha256

JRC_URL = "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/JRC-IDEES/JRC-IDEES-2023_v1/"
KINDS = ("Industry", "EnergyBalance", "EmissionBalance")
COUNTRIES = set("AT BE BG CY CZ DE DK EE EL ES FI FR HR HU IE IT LT LU LV MT NL PL PT RO SE SI SK".split())


def source_files(country: str, cache: Path, source_root: Path | None = None, *, download=True, refresh=False):
    if country not in COUNTRIES:
        raise ValueError(f"JRC-IDEES-2023 country not supported: {country}")
    names = [f"JRC-IDEES-2023_{kind}_{country}.xlsx" for kind in KINDS]
    if source_root:
        found = []
        for name in names:
            candidates = list(source_root.rglob(name))
            if len(candidates) != 1:
                raise ValueError(f"Expected exactly one {name} under {source_root}; found {len(candidates)}")
            found.append(candidates[0])
        # The parser resolves the balance files relative to the industry file.
        if len({p.parent for p in found}) != 1:
            raise ValueError("The Industry, EnergyBalance and EmissionBalance workbooks must share a directory")
        return found
    cache = cache / country
    cache.mkdir(parents=True, exist_ok=True)
    targets = [cache / name for name in names]
    if all(p.exists() for p in targets) and not refresh:
        return targets
    # The supplied original HR observations are an offline source, not a proxy for another country.
    archived = Path(__file__).parent / "handoff/model/data/sources"
    if country == "HR" and all((archived / name).exists() for name in names) and not refresh:
        for name, target in zip(names, targets):
            shutil.copy2(archived / name, target)
        origin = {"origin": "user_supplied_handoff", "country": country}
    else:
        if not download:
            raise FileNotFoundError(f"No cached JRC sources for {country}; supply --industry-source-root or enable downloads")
        url = JRC_URL + f"JRC-IDEES-2023_{country}.zip"
        archive = cache / f"JRC-IDEES-2023_{country}.zip"
        partial = archive.with_suffix(".zip.part")
        print(f"Downloading JRC-IDEES source for {country}: {url}", flush=True)
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "H2RES-industry-loader/1.0"})
            with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as output:
                shutil.copyfileobj(response, output)
            with ZipFile(partial) as book:
                for name, target in zip(names, targets):
                    members = [member for member in book.infolist() if Path(member.filename).name == name]
                    if len(members) != 1:
                        raise ValueError(f"JRC archive does not contain one unique {name}")
                    # Write only explicitly named files, never extract archive paths.
                    with book.open(members[0]) as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)
            partial.replace(archive)
        finally:
            partial.unlink(missing_ok=True)
        origin = {"origin": url, "country": country, "archive_sha256": sha256(archive)}
    origin["files"] = {p.name: sha256(p) for p in targets}
    (cache / "source_manifest.json").write_text(json.dumps(origin, indent=2), encoding="utf-8")
    return targets


def require_formula_caches(path: Path):
    """Never interpret a numeric source formula with no cached result as zero."""
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.startswith("xl/worksheets/sheet") or not name.endswith(".xml"):
                continue
            root = ET.fromstring(archive.read(name))
            for cell in root.findall(".//s:sheetData/s:row/s:c", ns):
                if cell.find("s:f", ns) is not None and cell.get("t", "n") == "n":
                    value = cell.find("s:v", ns)
                    if value is None or value.text is None:
                        raise ValueError(f"Uncached numeric source formula: {path.name}:{name}:{cell.get('r')}; recalculate the source workbook first")


def sector_waste_proofs(industry_path: Path, mode="strict"):
    """Optional sector-blend proxy where several fossil waste classes occur.

    Sector fossil energy and CO2 are observed; a common blend across its
    processes is an assumption. The original exact single-class proof wins.
    """
    from industry.methods.jrc_source import read_fossil_waste_proof
    strict = read_fossil_waste_proof(industry_path)
    if mode == "strict":
        return {}, []
    codes = dict(ISI="IS", NFM="NFM", CHI="CPC", NMM="NMM", PPA="PPP", FBT="FBT",
                 TRE="TE", MAE="MAC", TEL="TL", WWP="WP", OIS="NSP")
    energy = load_workbook(industry_path.with_name(industry_path.name.replace("_Industry_", "_EnergyBalance_")), read_only=True, data_only=True)
    emissions = load_workbook(industry_path.with_name(industry_path.name.replace("_Industry_", "_EmissionBalance_")), read_only=True, data_only=True)
    result, notes = {}, []
    try:
        for code, balance in codes.items():
            sheets = ["FC_IND_MQ_E", "FC_IND_CON_E", "FC_IND_NSP_E"] if code == "OIS" else [f"FC_IND_{balance}_E"]
            for year, proof in strict.items():
                if proof["single_fossil_class"]:
                    continue
                final, carbon, source_cells = 0., 0., []
                for sheet in sheets:
                    for book, kind in [(energy, "energy_ktoe"), (emissions, "CO2_kt")]:
                        rows = list(book[sheet].values)
                        col = next(i for i, v in enumerate(rows[0]) if v == year)
                        row = next(i for i, r in enumerate(rows) if len(r) > 1 and r[1] == "W6100_6220")
                        value = float(rows[row][col] or 0.)
                        if kind == "energy_ktoe":
                            final += value
                        else:
                            carbon += value
                        source_cells.append(f"{kind}:{sheet}!{get_column_letter(col + 1)}{row + 1}")
                if final <= 0 or carbon <= 0:
                    continue
                factor = carbon / final
                note = "ASSUMED common sector fossil-waste blend across processes; observed sector fossil waste energy and emissions: " + "; ".join(source_cells)
                result[code, year] = dict(single_fossil_class=True, waste_factor_t_per_toe=factor,
                                          factor_cell=note, composition_cells=note, basis_note=note)
                notes.append(dict(JRC_sector=code, year=year, fossil_waste_ktoe=final, fossil_waste_CO2_kt=carbon,
                                  weighted_factor_t_per_toe=factor, basis=note))
        return result, notes
    finally:
        energy.close()
        emissions.close()
