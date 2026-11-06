"""Separate regional data quality checks from model file-format checks."""
import json
from pathlib import Path

import numpy as np
import pandas as pd


def check_prepared_industry(args):
    from industry.regional_allocation import file_hash

    if "industry" not in getattr(args, "sectors", ()) or (args.industry_mode == "complex" and not getattr(args, "all_model_variants", False)):
        return None
    mapping = args.out_root / "_zone_maps" / "zone_map_common.csv"
    if not mapping.exists():
        return None
    zones = pd.read_csv(mapping)
    regional = zones.groupby("country").zone.nunique().gt(1)
    countries = [country for country in args.countries if regional.get(country, False)]
    if not countries:
        return None
    base = args.out_root / "industry" / "combined"
    path = base / "regional_generation.json"
    if not path.is_file():
        raise ValueError("Regional industry has no verified allocation provenance. Regenerate Industry with the updated loader; "
                         "old equal-share outputs cannot be certified by Export existing.")
    metadata = json.loads(path.read_text(encoding="utf-8"))
    for name, digest in metadata["files"].items():
        if file_hash(base / name) != digest:
            raise ValueError(f"Regional industry outputs changed after allocation: {name}. Regenerate Industry.")
    reports = {}
    for country in countries:
        report = metadata["countries"][country]
        if report.get("method_id") not in {"paper_facility_activity_v1", "explicit_equal"}:
            raise ValueError("Regional industry was not allocated using the paper's industrial installation method. Regenerate Industry with facility evidence.")
        if report.get("national_energy_year") != getattr(args, "industry_base_year", 2020):
            raise ValueError(f"Regional industry year differs from selected year for {country}; regenerate Industry.")
        if not report.get("national_sector_category_fuel_conserved"):
            raise ValueError(f"National industrial margins were not reconciled for {country}")
        if any("explicit equal" in item["basis"] for item in report["fuels"]) and getattr(args, "industry_regional_allocation", None) != "equal":
            raise ValueError("Equal regional industry allocation was not selected. Regenerate Industry with facility evidence.")
        for source in report["sources"]:
            if file_hash(source["file"]) != source["sha256"]:
                raise ValueError(f"Regional source changed for {country}; regenerate Industry")
        annual = pd.read_csv(base / "industry_heat.csv", usecols=["System", "zone", "all"])
        annual = annual.loc[annual.System.eq(country)].groupby("zone")["all"].sum()
        if report.get("method_id") == "paper_facility_activity_v1":
            raw = pd.Series(report["regional_totals"], dtype=float)
            local_map = zones.loc[zones.country.eq(country)]
            lookup = (local_map.set_index("nuts3").zone.to_dict() if "nuts3" in local_map
                      else {zone: zone for zone in local_map.zone})
            expected = raw.groupby(raw.index.map(lambda zone: lookup.get(zone, zone))).sum()
            if (set(annual.index) != set(expected.index)
                    or not np.allclose(annual.sort_index(), expected.sort_index(), rtol=1e-8, atol=1e-4)):
                raise ValueError(f"Regional industrial demand disagrees with the facility allocation for {country}; regenerate Industry")
        reports[country] = dict(method=report["method"], spatial_data_kind=report["spatial_data_kind"],
                                branch_prior=report.get("branch_prior"), raster_year=report["raster_year"],
                                method_id=report.get("method_id"), facility_evidence=report.get("facility_evidence"),
                                national_energy_year=report["national_energy_year"],
                                national_sector_category_fuel_conserved=True,
                                regional_annual_input_energy_MWh=annual.to_dict(),
                                fuel_allocation=report["fuels"], sources=report["sources"])
    return dict(industry=reports,
                interpretation="Regional quantities follow recorded industrial-facility activity. Capacities are estimates derived from energy and technology parameters; missing-sector coverage is explicitly flagged.",
                shared_defaults=["Technology costs, efficiencies, lifetimes and scenario assumptions may be common.",
                                 "Normalized transport/CO2/NH3 profiles may share timing; annual quantities carry scale.",
                                 "Unsourced default national stocks and annual quantities are allocated with prepared demand shares.",
                                 "Solar thermal availability retained from the reference is an explicit shared weather assumption."])


def check_prepared_methods(args):
    """Require verifiable paper methods for every selected regional sector."""
    quality = check_prepared_industry(args) or {}
    mapping = args.out_root / "_zone_maps/zone_map_common.csv"
    if not mapping.exists():
        return quality or None
    zones = pd.read_csv(mapping)
    if not zones.groupby("country").zone.nunique().gt(1).any():
        return quality or None
    from sector_method_provenance import file_hash, verify_records
    for sector, relative, expected in [
        ("transport", "transport/combined/paper_generation.json", "paper_transport_v1"),
        ("heating", "heating/paper_generation.json", "paper_heating_v1"),
    ]:
        if sector not in getattr(args,"sectors",()):
            continue
        path = args.out_root / relative
        if not path.is_file():
            raise ValueError(f"Regional {sector} has no verified paper-method provenance; regenerate that sector")
        details = json.loads(path.read_text(encoding="utf-8"))
        if details.get("method_id") != expected:
            raise ValueError(f"Regional {sector} uses a different allocation method; regenerate it")
        for name, digest in details["files"].items():
            if file_hash(path.parent/name) != digest:
                raise ValueError(f"Prepared {sector} output changed after method verification: {name}")
        verify_records(details["sources"])
        for source in details["sources"]:
            child_path = Path(source["file"])
            child = json.loads(child_path.read_text(encoding="utf-8"))
            verify_records(child.get("sources",[]))
            verify_records(list(child.get("inputs",{}).values()))
            outputs = child.get("outputs",[])
            if isinstance(outputs,dict):
                outputs = [dict(file=str(child_path.parent/name),sha256=digest) for name,digest in outputs.items()]
            verify_records(outputs)
        quality[sector] = details
    return quality or None
