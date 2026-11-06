#!/usr/bin/env python3
"""Build the loader-compatible NUTS3-to-macroregion CSV."""

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BOUNDARIES = ROOT / "power" / "data" / "NUTS_RG_20M_2021_4326_LEVL_3.geojson"
GENCO_DIR = ROOT / "power" / "generators" / "genco_built_all"
OUTPUT = ROOT / "macroregion_map.csv"

MACROREGIONS = {
    "AL": "East_EU", "AT": "Central_EU", "BE": "West_EU",
    "BA": "East_EU", "BG": "East_EU", "HR": "Central_EU",
    "CZ": "Central_EU", "DK": "Nordics", "EE": "Baltics",
    "FI": "Nordics", "FR": "West_EU", "DE": "Central_EU",
    "HU": "East_EU", "IT": "South_EU", "XK": "East_EU",
    "LV": "Baltics", "LT": "Baltics", "LU": "West_EU",
    "ME": "East_EU", "NL": "West_EU", "MK": "East_EU",
    "NO": "Nordics", "PL": "East_EU", "PT": "Iberia",
    "RO": "East_EU", "RS": "East_EU", "SK": "East_EU",
    "SI": "Central_EU", "ES": "Iberia", "SE": "Nordics",
    "CH": "Central_EU", "GR": "South_EU",
}


def packaged_power_nuts3(country: str) -> set[str]:
    path = GENCO_DIR / f"genco_{country}_built.csv"
    if not path.exists():
        return set()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {
            row["NUTS3"].strip()
            for row in csv.DictReader(handle)
            if row.get("NUTS3", "").strip()
        }


def main() -> None:
    geojson = json.loads(BOUNDARIES.read_text(encoding="utf-8"))
    official: dict[str, set[str]] = {}
    for feature in geojson["features"]:
        props = feature["properties"]
        official.setdefault(str(props["CNTR_CODE"]), set()).add(str(props["NUTS_ID"]))

    rows: list[tuple[str, str, str, str]] = []
    for country, macroregion in MACROREGIONS.items():
        boundary_country = "EL" if country == "GR" else country
        nuts3_codes = official.get(boundary_country, set())
        if country in {"BA", "XK"}:
            nuts3_codes = packaged_power_nuts3(country)
        if not nuts3_codes:
            raise ValueError(f"No usable NUTS3 codes found for {country}")
        rows.extend(
            (country, nuts3, f"{macroregion}1", macroregion)
            for nuts3 in sorted(nuts3_codes)
        )

    with OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["country", "nuts3", "zone", "system_new"])
        writer.writerows(rows)
    print(f"Wrote {len(rows)} mappings to {OUTPUT.name}")


if __name__ == "__main__":
    main()
