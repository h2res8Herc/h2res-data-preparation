"""European regional weights for international seaborne freight (thousand tonnes)."""
import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile

import geopandas as gpd
import numpy as np
import pandas as pd
import requests


EUROSTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
PORTS = "https://ows.emodnet-humanactivities.eu/wfs"
BUNDLED = Path(__file__).resolve().parent / "international_port_freight_2020.csv"
BASIS = "Eurostat_international_port_freight"
PORT_CODE = re.compile(r"[A-Z]{2}_[A-Z0-9]([A-Z0-9]{5})$")


def observations(dataset, params):
    response = requests.get(EUROSTAT + dataset, params={"direct": "TOTAL", "unit": "THS_T", **params}, timeout=90)
    response.raise_for_status()
    data = response.json()
    dimensions = data["id"]
    axes = []
    for key in dimensions:
        index = data["dimension"][key]["category"]["index"]
        axes.append(sorted(index, key=index.get))
    rows = []
    for index, value in data["value"].items():
        if value is not None:
            row = dict(zip(dimensions, (axis[i] for axis, i in zip(axes, np.unravel_index(int(index), data["size"])))))
            rows.append(dict(**row, tonnes_k=float(value)))
    return pd.DataFrame(rows, columns=[*dimensions, "tonnes_k"])


def download_snapshot(year):
    period = {"sinceTimePeriod": f"{year}-Q1", "untilTimePeriod": f"{year}-Q4"}
    pairs = ["EU27_2020", "EU28", "EU27_2007", "EU25", "EU15"]
    categories = [prefix + pair for pair in pairs for prefix in ("INTL_I", "INTL_X")]
    quarterly = observations("mar_go_qm", {**period, "tra_cov": ["TOTAL", "NAT", "UNK", *categories]})
    annual = observations("mar_go_aa", {"time": year}).set_index("rep_mar").tonnes_k
    if annual.empty or quarterly.empty:
        raise ValueError(f"No European port freight observations for {year}; select an available port freight year")
    wide = quarterly.pivot(index=["rep_mar", "time"], columns="tra_cov", values="tonnes_k")
    intl = pd.Series(np.nan, index=wide.index)
    for pair in pairs:
        intra, extra = wide.reindex(columns=["INTL_I" + pair, "INTL_X" + pair]).T.to_numpy()
        subtotal = np.nan_to_num(intra) + np.nan_to_num(extra)
        # One category may be omitted when zero. Accept it only if reported
        # components reconcile to the reported quarterly total within rounding.
        remainder = wide["TOTAL"] - wide.reindex(columns=["NAT", "UNK"]).fillna(0).sum(axis=1) - subtotal
        usable = (np.isfinite(intra) & np.isfinite(extra)) | (
            (np.isfinite(intra) | np.isfinite(extra)) & remainder.abs().le(1))
        intl = intl.fillna(pd.Series(subtotal, index=wide.index).where(usable))
    measured = intl.groupby(level="rep_mar").sum(min_count=4)
    main_total = wide["TOTAL"].groupby(level="rep_mar").sum(min_count=4)
    response = requests.get(PORTS, params=dict(service="WFS", version="1.0.0", request="GetFeature",
        typename="emodnet:portlocations", outputFormat="application/json", srsName="EPSG:4326"), timeout=90)
    response.raise_for_status()
    locations = response.json()
    if int(locations["totalFeatures"]) != len(locations["features"]):
        raise ValueError("Incomplete EMODnet port location catalogue")
    xy = {f["properties"]["port_id"]: f["geometry"]["coordinates"][:2] for f in locations["features"]}
    rows = []
    for code in annual.index.union(measured.dropna().index):
        match = PORT_CODE.fullmatch(code)
        if not match:
            continue
        country = code[:2]
        ratio = measured.get(country, np.nan) / main_total.get(country, np.nan) if main_total.get(country, 0) > 0 else np.nan
        has_ratio = np.isfinite(ratio)
        ratio = float(np.clip(ratio, 0, 1)) if has_ratio else 1.
        total = annual.get(code, main_total.get(code, np.nan))
        known = measured.get(code, np.nan)
        weight = known if pd.notna(known) else total * ratio
        if not weight > 0:
            continue
        lon, lat = xy.get(match[1], (np.nan, np.nan))
        basis = "annual_cargo_times_main_port_international_share" if has_ratio else "all_cargo_proxy_no_national_traffic_split"
        rows.append((year, country, code, lon, lat, total, weight, "reported_international" if pd.notna(known) else basis))
    # Country totals occasionally include smaller ports without an individual row.
    # Only add the uncovered all-cargo residual; never count an aggregate as a port.
    for country in sorted({row[1] for row in rows}):
        port_totals = annual.combine_first(main_total)
        listed = port_totals[[bool(PORT_CODE.fullmatch(c)) and c.startswith(country + "_") for c in port_totals.index]]
        if country in annual:
            residual = annual[country] - listed.sum()
            if residual > max(1, .5 * len(listed.dropna())):
                ratio = measured.get(country, np.nan) / main_total[country] if main_total.get(country, 0) > 0 else np.nan
                rows.append((year, country, "unlisted", np.nan, np.nan, residual,
                             residual * (float(np.clip(ratio, 0, 1)) if pd.notna(ratio) else 1.),
                             "unlisted_cargo_times_main_port_international_share" if pd.notna(ratio) else "unlisted_all_cargo_proxy"))
    if not rows:
        raise ValueError(f"No usable European international port freight weights for {year}")
    return pd.DataFrame(rows, columns=["year", "country", "port_code", "lon", "lat", "all_cargo_kt", "international_kt", "basis"])


def snapshot(cache, year, refresh):
    target = Path(cache) / "port_freight" / f"international_port_freight_{year}.csv"
    existing = target if target.is_file() else BUNDLED if year == 2020 and BUNDLED.is_file() else None
    if existing and not refresh:
        return existing
    try:
        frame = download_snapshot(year)
    except (requests.RequestException, ValueError, KeyError) as exc:
        if existing is None:
            raise
        print(f"WARNING: Could not refresh port freight for {year}: {exc}. Using {existing}.", flush=True)
        return existing
    target.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=target.parent, delete=False, mode="w", encoding="utf-8", newline="") as stream:
        frame.to_csv(stream, index=False)
    os.replace(stream.name, target)
    return target


def regional_weights(path, country, nuts, osm, year):
    table = pd.read_csv(path)
    country = {"GR": "EL", "GB": "UK"}.get(country, country)
    ports = table.loc[table.country.eq(country) & table.year.eq(year)].copy()
    report = dict(year=year, source_tables=["mar_go_qm", "mar_go_aa"], locations="EMODnet portlocations",
                  ports=[], fallback=None)
    if ports.empty:
        report["fallback"] = "No country observations for the selected year; use existing coastal OSM weights"
        return None, report
    if ports.port_code.duplicated().any() or not np.isfinite(ports.international_kt).all() or ports.international_kt.lt(0).any():
        raise ValueError(f"Invalid Eurostat weights for {country}")
    regions = nuts.set_index("NUTS_ID").to_crs(3035)
    coast = pd.to_numeric(regions.COAST_TYPE).isin([1, 2])
    assigned = pd.Series(0., index=regions.index)
    residual = 0.
    known = ports.dropna(subset=["lon", "lat"])
    points = gpd.GeoSeries(gpd.points_from_xy(known.lon, known.lat), index=known.index, crs=4326).to_crs(3035)
    for row in ports.itertuples():
        zone = None
        if row.Index in points.index:
            distances = regions.distance(points[row.Index])
            nearest = distances.idxmin()
            # Generalised coastal polygons can leave a quay just offshore.
            if distances[nearest] <= 5000 and coast[nearest]:
                zone = nearest
        if zone is None:
            residual += row.international_kt
        else:
            assigned[zone] += row.international_kt
        report["ports"].append(dict(port=row.port_code, nuts3=zone, basis=row.basis, international_kt=row.international_kt))
    if assigned.sum() == 0:
        report["fallback"] = "No freight port matched eligible country regions; use existing coastal OSM weights"
        return None, report
    if residual:
        proxy = pd.Series(np.asarray(osm, dtype=float), index=regions.index).where(coast, 0.)
        uncovered = proxy.where(assigned.eq(0), 0.)
        if uncovered.sum() > 0:
            proxy = uncovered
        if proxy.sum() <= 0:
            proxy = assigned.copy()
        assigned += residual * proxy / proxy.sum()
    report["spatially_unassigned_kt_distributed"] = residual
    np.testing.assert_allclose(assigned.sum(), ports.international_kt.sum())
    return assigned, report
