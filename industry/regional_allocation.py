"""Conserve JRC national margins using sector-filtered industrial facilities.

The paper-method default allocates proportionally to observed installation
activity. The older raster-only reconciler remains an explicit utility and is
not used as the default source of industrial geography.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

EIGL_URL = "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/EIGL-Data/RASTER/"
EIGL_YEAR = "2019"
RASTER_FUELS = ("electricity", "gas", "oil", "heat", "renewables", "solid", "others")
FUEL_RASTER = {"coal": "solid", "biomass": "renewables", "renewables_waste": "renewables"}


def raster_totals(directory, nuts, year):
    """Sum pixel centres once per region; exclude nodata and negative values."""
    import rasterio
    from rasterstats import zonal_stats

    columns, sources = {}, []
    for fuel in RASTER_FUELS:
        path = Path(directory) / f"{fuel}_ind_demand_{year}.tif"
        if not path.is_file():
            continue
        with rasterio.open(path) as raster:
            crs = raster.crs
            # These public rasters may label ETRS-LAEA as a local CRS.
            if crs and not crs.to_epsg() and "LAEA" in crs.to_wkt().upper():
                crs = rasterio.crs.CRS.from_epsg(3035)
            if not crs:
                raise ValueError(f"Industrial raster has no CRS: {path}")
            stats = zonal_stats(nuts.to_crs(crs), str(path), stats="sum",
                                nodata=raster.nodata, all_touched=False)
        values = np.array([item["sum"] or 0. for item in stats], dtype=float)
        if not np.isfinite(values).all() or (values < 0).any():
            raise ValueError(f"Invalid industrial raster totals: {path}")
        columns[fuel] = values
        sources.append(dict(file=str(path.resolve()), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                            url=EIGL_URL + path.name, geography_year=str(year)))
    return pd.DataFrame(columns, index=nuts.NUTS_ID.astype(str)), sources


def allocate_margins(national, zones, site_weights, rasters, *, equal=False):
    """Balance each fuel's regional and branch/category margins separately."""
    keys = ["sector", "category", "fuel"]
    national = national.groupby(keys, as_index=False).national_total_MWh.sum()
    if not np.isfinite(national.national_total_MWh).all() or (national.national_total_MWh < 0).any():
        raise ValueError("Invalid national industrial energy margins")
    zones = sorted(set(zones))
    if not zones:
        raise ValueError("No industrial allocation zones")
    raster = rasters.reindex(zones, fill_value=0.).fillna(0.)
    if not np.isfinite(raster.to_numpy()).all() or (raster.to_numpy() < 0).any():
        raise ValueError("Invalid EIGL industrial geography weights")
    # Combined industry geography is a stated fallback for an empty fuel map.
    # Each map has the same physical units, so this is an energy-weighted sum.
    combined = raster.sum(axis=1)
    site = site_weights.pivot_table(index="nuts", columns="branch", values="weight", aggfunc="sum")
    site = site.reindex(zones, fill_value=0.).fillna(0.)
    if not np.isfinite(site.to_numpy()).all() or (site.to_numpy() < 0).any():
        raise ValueError("Invalid industrial facility weights")
    facility_geography = len(zones) > 1 and site.nunique().gt(1).any()
    rows, notes = [], []
    for fuel, table in national.groupby("fuel", sort=True):
        total = float(table.national_total_MWh.sum())
        if total <= 0:
            continue
        name = FUEL_RASTER.get(fuel, fuel)
        weights = raster[name] if name in raster else pd.Series(0., index=zones)
        basis = f"EIGL industrial {name} raster"
        if len(zones) == 1:
            weights = pd.Series(1., index=zones)
            basis = "single national zone"
        elif equal:
            weights = pd.Series(1., index=zones)
            basis = "explicit equal allocation assumption"
        elif weights.sum() <= 0:
            weights = combined
            basis = "EIGL combined industrial energy proxy; fuel map missing or zero"
            if weights.sum() <= 0 and facility_geography:
                weights = site.sum(axis=1)
                basis = "supplied industrial facility mass proxy; no usable EIGL map"
        if weights.sum() <= 0:
            raise ValueError("Regional industry has no usable EIGL industrial geography or facility weights. "
                             "Download the industrial rasters, supply facilities, or explicitly select equal allocation.")
        shares = weights.to_numpy(dtype=float) / float(weights.sum())
        targets = table.national_total_MWh.to_numpy(dtype=float)
        # A complete positive prior allows RAS to honour both sets of margins.
        # Tiny values are a numerical support assumption, never plant records.
        prior = site.reindex(columns=table.sector.tolist(), fill_value=0.).to_numpy(dtype=float, copy=True)
        if equal:
            prior[:] = 1.
        prior = np.maximum(prior, max(float(prior.max()), 1.) * 1e-12)
        matrix = prior * targets[None, :]
        regional = shares * total
        converged = False
        for iteration in range(10000):
            matrix *= np.divide(regional, matrix.sum(axis=1), out=np.zeros(len(zones)),
                                where=matrix.sum(axis=1) > 0)[:, None]
            sums = matrix.sum(axis=0)
            matrix *= np.divide(targets, sums, out=np.zeros(len(targets)), where=sums > 0)[None, :]
            if np.allclose(matrix.sum(axis=1), regional, rtol=1e-9, atol=1e-6):
                converged = True
                break
        if not converged or not np.allclose(matrix.sum(axis=0), targets, rtol=1e-10, atol=1e-6):
            raise ValueError(f"Industrial regional reconciliation failed for {fuel}")
        for i, zone in enumerate(zones):
            for j, item in enumerate(table.itertuples(index=False)):
                if matrix[i, j] > 0:
                    rows.append(dict(nuts=zone, branch=item.sector, category=item.category,
                                     fuel=fuel, MWh=float(matrix[i, j])))
        notes.append(dict(fuel=fuel, basis=basis, national_MWh=total,
                          regional_MWh=float(matrix.sum()), shares=dict(zip(zones, shares.tolist())),
                          iterations=iteration + 1))
    result = pd.DataFrame(rows, columns=["nuts", "branch", "category", "fuel", "MWh"])
    return result, notes


def allocate_facility_margins(national, weights):
    keys = ["sector", "category", "fuel"]
    national = national.groupby(keys, as_index=False).national_total_MWh.sum()
    if weights.duplicated(["nuts", "branch"]).any() or weights.weight.lt(0).any():
        raise ValueError("Invalid facility allocation weights")
    if not np.isfinite(weights.weight).all() or not np.allclose(weights.groupby("branch").weight.sum(), 1., atol=1e-12):
        raise ValueError("Facility weights must sum to one for every industrial sector")
    result = national.rename(columns={"sector": "branch"}).merge(weights, on="branch", how="left")
    if result.weight.isna().any():
        raise ValueError("An industrial sector has no facility allocation")
    result["MWh"] = result.national_total_MWh * result.weight
    actual = result.groupby(["branch", "category", "fuel"]).MWh.sum()
    expected = national.rename(columns={"sector": "branch"}).set_index(["branch", "category", "fuel"]).national_total_MWh
    if not np.allclose(actual.reindex(expected.index), expected, rtol=1e-10, atol=1e-6):
        raise ValueError("Facility allocation did not conserve national sector/category/fuel margins")
    return result[["nuts", "branch", "category", "fuel", "MWh"]]


def reconcile_allocation(alloc_dir, nuts_path, country, nuts_level, eigl_dir, eigl_year, *, equal=False,
                         facility_cache=None, year=2020, download=True, refresh=False):
    import geopandas as gpd

    directory = Path(alloc_dir)
    nuts = gpd.read_file(nuts_path)
    boundary_country = {'GR':'EL','GB':'UK'}.get(country,country)
    nuts = nuts.loc[nuts.NUTS_ID.astype(str).str.startswith(boundary_country)
                    & nuts.NUTS_ID.astype(str).str.len().eq(nuts_level + 2)].copy()
    if nuts.empty:
        raise ValueError(f'No NUTS{nuts_level} polygons for {country} in {nuts_path}')
    national = pd.read_csv(directory / "national_margins_sector_category_fuel.csv")
    if equal:
        sites = pd.read_csv(directory / "site_weights_nuts_branch.csv")
        allocated, notes = allocate_margins(national, nuts.NUTS_ID.astype(str), sites, pd.DataFrame(), equal=True)
        facility = dict(sources=[], sectors=[], source_priority="explicit equal regional scenario assumption")
    else:
        if facility_cache is None:
            raise ValueError("Paper-method industry requires a facility evidence cache")
        from industry.facility_sources import prepare_weights
        sites, evidence, facility = prepare_weights(facility_cache, nuts, country, year, download=download, refresh=refresh)
        sites.to_csv(directory / "site_weights_nuts_branch.csv", index=False)
        evidence.to_csv(directory / "facility_observations.csv", index=False)
        allocated = allocate_facility_margins(national, sites)
        notes = []
        for fuel, block in allocated.groupby("fuel"):
            totals = block.groupby("nuts").MWh.sum()
            total = float(totals.sum())
            notes.append(dict(fuel=fuel, basis="sector-filtered industrial installation activity; no population allocation",
                              national_MWh=total, regional_MWh=total,
                              shares=(totals / total).to_dict() if total else totals.to_dict()))
    allocated.to_csv(directory / "allocated_nuts_sector_category_fuel.csv", index=False)
    allocated.groupby(["nuts", "branch", "fuel"], as_index=False).MWh.sum().to_csv(
        directory / "allocated_nuts_sector_fuel.csv", index=False)
    allocated.groupby(["nuts", "fuel"], as_index=False).MWh.sum().rename(
        columns={"MWh": "regional_total_MWh"}).to_csv(directory / "nuts_margins_fuel.csv", index=False)
    report = dict(method_id="explicit_equal" if equal else "paper_facility_activity_v1",
                  method="JRC national sector/category/fuel totals proportionally allocated using sector-filtered facility activity",
                  spatial_data_kind="geolocated industrial installation activity proxies; capacities derived from energy/efficiency/CF",
                  branch_prior=facility["source_priority"], facility_evidence=facility,
                  national_energy_year=year, facility_year=year, raster_year=None,
                  sources=facility["sources"], fuels=notes,
                  national_sector_category_fuel_conserved=True,
                  regional_totals=allocated.groupby("nuts").MWh.sum().to_dict())
    (directory / "regional_allocation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"{country}: reconciled industrial geography for {len(nuts)} regions; national sector/category/fuel totals conserved", flush=True)
    return report


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_generation_provenance(final_dirs, output):
    """Bind the combined observations to the allocation that produced them."""
    countries = {}
    for directory in final_dirs:
        path = directory.parent / "01_allocated" / "regional_allocation.json"
        if path.is_file():
            countries[directory.parent.name] = dict(file=str(path.resolve()), sha256=file_hash(path),
                                                    **json.loads(path.read_text(encoding="utf-8")))
    names = ["industry_heat.csv", "industry_category_profiles.csv", "industry_electricity.csv"]
    names.extend(f"Industry_data_{fuel}{category}.csv" for fuel in ("regular", "efuels")
                 for category in ("", "_heat_categories"))
    names.extend(name for name in ("industry_fuel_representation.json", "Industry_data_regular_fuel_redistribution.csv",
                                  "Industry_data_regular_heat_categories_fuel_redistribution.csv")
                 if (output / name).is_file())
    branch_rows = []
    from industry.facility_sources import MODEL_LABELS
    mapping_path = output.parent.parent / "_zone_maps/zone_map_common.csv"
    mapping = pd.read_csv(mapping_path) if mapping_path.exists() else None
    for directory in final_dirs:
        source = directory.parent / "01_allocated/site_weights_nuts_branch.csv"
        if not source.exists():
            continue
        frame = pd.read_csv(source)
        country = directory.parent.name
        zone_lookup = (mapping.loc[mapping.country.eq(country)].set_index("nuts3").zone.to_dict()
                       if mapping is not None else {})
        frame["zone"] = frame.nuts.map(zone_lookup).fillna(frame.nuts)
        frame["Industry"] = frame.branch.map(MODEL_LABELS)
        if frame.Industry.isna().any():
            raise ValueError("Unknown facility branch in model allocation")
        frame["country"] = country
        for (zone, branch), group in frame.groupby(["zone", "Industry"]):
            branch_rows.append(dict(country=country, zone=zone, Industry=branch, weight=float(group.weight.sum()),
                                    allocation_basis=";".join(sorted(group.allocation_basis.unique()))
                                    if "allocation_basis" in group else "explicit_equal"))
    if branch_rows:
        name = "regional_branch_weights.csv"
        pd.DataFrame(branch_rows).to_csv(output / name, index=False)
        names.append(name)
    details = dict(countries=countries, files={name: file_hash(output / name) for name in names})
    (output / "regional_generation.json").write_text(json.dumps(details, indent=2), encoding="utf-8")
