"""Facility evidence for the industrial allocation described in the paper.

National sector totals follow the spatial distribution of industrial activity.
EU ETS verified emissions in the selected year provide an activity/capacity
proxy; EEA industrial-site counts cover branches outside the ETS. The paper
does not specify a numerical source blend: this source-priority rule is recorded
explicitly. A missing branch uses industrial-site density, never population.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import shutil
import urllib.parse
import urllib.request
from zipfile import ZipFile

import geopandas as gpd
import numpy as np
import pandas as pd

ETS_URL = "https://zenodo.org/api/records/21414185/files/eutl_data_package_2026-07-21.zip/content"
ETS_MD5 = "629595320851d20bd1b610878a2ecd1e"
IED_QUERY = "https://air.discomap.eea.europa.eu/arcgis/rest/services/Air/IED_SiteMap/MapServer/0/query"
EIGL_QUERY = "https://arcgis.jrc.ec.europa.eu/server/rest/services/eigl/EIGL_SERVICES_Industrial_infrastructure_PUB/MapServer/0/query"
TABLES = ("installations.csv", "compliance.csv", "installation_locations.csv", "nace_mappings.csv",
          "map_installation_to_eid_facility.csv", "datapackage.json")
BRANCHES = ("iron_steel", "chemicals_petrochem", "non_ferrous_metals", "non_metallic_minerals",
            "transport_equipment", "machinery", "mining_quarrying", "food_bev_tobacco",
            "paper_pulp_printing", "wood_products", "construction", "textile_leather", "nes_industry")
MODEL_LABELS = dict(zip(BRANCHES, ("Iron_steel", "Chemical_petrochemical", "Non_ferrous_metals",
    "Non_metallic_minerals", "Transport_equipment", "Machinery", "Mining_quarrying",
    "Food_beverages_tobacco", "Paper_pulp_printing", "Wood_wood_products", "Construction",
    "Textile_leather", "Not_elsewhere_specified_(industry)")))
NACE = {"24": "iron_steel", "244": "non_ferrous_metals", "2453": "non_ferrous_metals", "2454": "non_ferrous_metals", "23": "non_metallic_minerals",
        **dict.fromkeys(("20", "21"), "chemicals_petrochem"),
        **dict.fromkeys(("29", "30"), "transport_equipment"),
        **dict.fromkeys(("25", "26", "27", "28"), "machinery"),
        **dict.fromkeys(("07", "08", "099"), "mining_quarrying"),
        **dict.fromkeys(("41", "42", "43"), "construction"),
        **dict.fromkeys(("10", "11", "12"), "food_bev_tobacco"),
        **dict.fromkeys(("17", "18"), "paper_pulp_printing"), "16": "wood_products",
        **dict.fromkeys(("13", "14", "15"), "textile_leather"),
        **dict.fromkeys(("22", "31", "32", "33"), "nes_industry")}


def digest(path, algorithm="sha256"):
    result = hashlib.new(algorithm)
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "H2RES-paper-method/1.0"})
    with urllib.request.urlopen(request, timeout=180) as response:
        return response.read()


def country_aliases(country):
    # GISCO/JRC use EL and UK, while the ETS registry uses GR and GB.
    return {'EL':('EL','GR'),'GR':('EL','GR'),'UK':('UK','GB'),'GB':('UK','GB')}.get(country,(country,))


def ensure_ets(cache, *, download=True, refresh=False):
    cache = Path(cache)
    tables = cache / "EUTL"
    if not refresh and all((tables / name).is_file() for name in TABLES):
        return tables
    archive = cache / "eutl_data_package_2026-07-21.zip"
    if (not archive.exists() or refresh) and download:
        cache.mkdir(parents=True, exist_ok=True)
        partial = archive.with_suffix(".zip.part")
        print("Downloading EU ETS installation evidence (499 MB; cached for subsequent runs)", flush=True)
        request = urllib.request.Request(ETS_URL, headers={"User-Agent": "H2RES-paper-method/1.0"})
        with urllib.request.urlopen(request, timeout=180) as response, partial.open("wb") as output:
            shutil.copyfileobj(response, output, 1024 * 1024)
        partial.replace(archive)
    if not archive.is_file():
        raise FileNotFoundError("EU ETS facility evidence is missing; enable source downloads or provide a source cache")
    if digest(archive, "md5") != ETS_MD5:
        raise ValueError("EU ETS archive checksum differs from the pinned public dataset")
    tables.mkdir(parents=True, exist_ok=True)
    with ZipFile(archive) as source:
        for name in TABLES:
            with source.open(name) as incoming, (tables / name).open("wb") as output:
                shutil.copyfileobj(incoming, output, 1024 * 1024)
    return tables


def ensure_ied(cache, country, year, *, download=True, refresh=False):
    path = Path(cache) / f"EEA_IED_{country}_{year}.geojson"
    if path.is_file() and not refresh:
        return path
    if not download:
        raise FileNotFoundError(f"EEA industrial-site evidence is missing for {country}/{year}; enable source downloads")
    features, offset = [], 0
    while True:
        selection = ','.join("'"+code+"'" for code in country_aliases(country))
        query = urllib.parse.urlencode(dict(where=f"countryCode IN ({selection}) AND Site_reporting_year={int(year)}",
            outFields="*", outSR=4326, f="geojson", resultRecordCount=1000,
            resultOffset=offset, orderByFields="OBJECTID"))
        response = json.loads(fetch(IED_QUERY + "?" + query))
        if "error" in response:
            raise ValueError("EEA industrial-site query failed: " + str(response["error"]))
        batch = response["features"]
        features.extend(batch)
        if len(batch) < 1000:
            break
        offset += len(batch)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".geojson.part")
    partial.write_text(json.dumps(dict(type="FeatureCollection", features=features)), encoding="utf-8")
    partial.replace(path)
    print(f"{country}: loaded {len(features)} EEA industrial sites for {year}", flush=True)
    return path


def ensure_eigl(cache, country, nuts, *, download=True, refresh=False):
    path = Path(cache) / f"EIGL_industrial_facilities_{country}.geojson"
    if path.is_file() and not refresh:
        return path
    if not download:
        raise FileNotFoundError(f"EIGL industrial installation evidence is missing for {country}")
    bounds = ",".join(map(str, nuts.to_crs("EPSG:4326").total_bounds))
    features, offset = [], 0
    while True:
        parameters = dict(where="1=1", geometry=bounds, geometryType="esriGeometryEnvelope",
                          spatialRel="esriSpatialRelIntersects", inSR=4326, outSR=4326,
                          outFields="*", f="geojson", resultRecordCount=1000,
                          resultOffset=offset, orderByFields="objectid")
        response = json.loads(fetch(EIGL_QUERY + "?" + urllib.parse.urlencode(parameters)))
        if "error" in response:
            raise ValueError("EIGL industrial facility query failed: " + str(response["error"]))
        batch = response["features"]
        features.extend(batch)
        if len(batch) < 1000:
            break
        offset += len(batch)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".geojson.part")
    partial.write_text(json.dumps(dict(type="FeatureCollection", features=features)), encoding="utf-8")
    partial.replace(path)
    return path


def nace_branch(value):
    if pd.isna(value):
        return None
    text = str(value).strip()
    if re.fullmatch(r"\d\.\d+", text):
        text = "0" + text
    if re.fullmatch(r"\d{3,}\.0", text):
        text = text[:-2]
    digits = re.sub(r"[^0-9]", "", text)
    return NACE.get(digits[:4], NACE.get(digits[:3], NACE.get(digits[:2])))


def label_branch(value):
    text = str(value).lower()
    patterns = [
        ("chemicals_petrochem", r"chemical|ammonia|nitric acid|adipic|glyoxal|hydrogen"),
        ("non_ferrous_metals", r"non.?ferrous|alumini|copper|zinc"),
        ("iron_steel", r"steel|pig iron|ferrous|coke|metal ore"),
        ("non_metallic_minerals", r"cement|lime|glass|ceramic|mineral wool|gypsum|non.?metallic|mineral processing"),
        ("paper_pulp_printing", r"pulp|paper|cardboard|printing"),
        ("food_bev_tobacco", r"food|drink|beverage|slaughter|milk|dairy|sugar|starch|malting"),
        ("wood_products", r"wood|sawmill"), ("textile_leather", r"textile|leather|tanning"),
        ("transport_equipment", r"motor vehicle|ship.?building|transport equipment"),
        ("machinery", r"machinery|electrical equipment|fabricated metal"),
        ("mining_quarrying", r"mining|quarry"), ("construction", r"construction of|building construction"),
        ("nes_industry", r"other manufacturing"),
    ]
    return next((branch for branch, pattern in patterns if re.search(pattern, text)), None)


def assign_regions(frame, nuts):
    """Use installation coordinates, with no operator/head-office geocoding."""
    frame = frame.copy()
    for field in ("longitude", "latitude"):
        frame[field] = pd.to_numeric(frame[field], errors="coerce")
    frame = frame.dropna(subset=["longitude", "latitude"])
    frame = frame.loc[np.isfinite(frame.longitude) & np.isfinite(frame.latitude)]
    points = gpd.GeoDataFrame(frame, geometry=gpd.points_from_xy(frame.longitude, frame.latitude), crs="EPSG:4326")
    regions = nuts[["NUTS_ID", "geometry"]].to_crs("EPSG:4326")
    result = gpd.sjoin(points, regions, how="inner", predicate="intersects")
    # Boundary points must not duplicate facility activity in two counties.
    return result.sort_values("NUTS_ID").drop_duplicates("facility_id").rename(columns={"NUTS_ID": "nuts"})


def observations(tables, ied_path, country, year, nuts, eigl_path=None):
    installations = pd.read_csv(tables / "installations.csv")
    installations = installations.loc[installations.registry_id.isin(country_aliases(country))].rename(columns={"id": "installation_id", "name": "facility_name"})
    compliance = pd.read_csv(tables / "compliance.csv", usecols=["installation_id", "year", "verified"])
    compliance = compliance.loc[compliance.year.eq(year) & compliance.verified.gt(0)]
    if compliance.duplicated("installation_id").any():
        raise ValueError("Multiple ETS compliance records for the same installation and year")
    location = pd.read_csv(tables / "installation_locations.csv")
    nace = pd.read_csv(tables / "nace_mappings.csv")
    ets = installations.merge(compliance, on="installation_id", validate="one_to_one")
    ets = ets.merge(location, on="installation_id", validate="one_to_one").merge(nace, on="installation_id", how="left", validate="one_to_one")
    ets["nace"] = ets["nace_2020"].fillna(ets["nace_2015"]) if year >= 2015 else ets["nace_2015"]
    ets["branch"] = ets.nace.map(nace_branch)
    # Refineries and energy extraction/transformation are excluded from final
    # industrial consumption in the Eurostat/JRC sector classification.
    excluded = ets.nace.astype(str).str.match(r"^(19|35|05|06|5\.|6\.|9\.1|09\.1)")
    excluded |= ets.activity_name.str.contains("refining|mineral oil|extraction of", case=False, na=False)
    fallback = ets.branch.isna() & ~excluded
    ets.loc[fallback, "branch"] = ets.loc[fallback, "activity_name"].map(label_branch)
    ets = ets.loc[ets.branch.notna() & ~excluded].copy()
    ets["facility_id"] = ets.installation_id
    ets["metric"], ets["metric_unit"], ets["evidence_source"] = ets.verified, "t_CO2_verified", "EU_ETS"
    ets["evidence_year"] = year
    ets = assign_regions(ets, nuts)

    features = json.loads(Path(ied_path).read_text(encoding="utf-8"))["features"]
    rows = []
    for feature in features:
        props, point = feature["properties"], feature["geometry"]
        if point is None or point["type"] != "Point":
            continue
        sectors = str(props.get("eprtr_sectors", ""))
        if sectors and all(part.strip() in {"WASTE AND WASTEWATER", "INTENSIVE LIVESTOCK PRODUCTION AND AQUACULTURE", "ENERGY"}
                           for part in sectors.split(",")):
            continue
        branch = label_branch(str(props.get("eea_activities", "")) + " " + str(props.get("activity_details", "")))
        if branch is None:
            continue  # Power, livestock and waste sites are not residual industry.
        rows.append(dict(facility_id=props["InspireSiteId"], facility_name=props.get("siteName"),
                         longitude=point["coordinates"][0], latitude=point["coordinates"][1],
                         branch=branch, metric=max(float(props.get("nFacilities") or 1), 1.),
                         metric_unit="facility_count", evidence_source="EEA_IED", evidence_year=year))
    ied = assign_regions(pd.DataFrame(rows, columns=["facility_id", "facility_name", "longitude", "latitude", "branch",
                         "metric", "metric_unit", "evidence_source", "evidence_year"]), nuts)
    extra_rows = []
    if eigl_path is not None:
        features = json.loads(Path(eigl_path).read_text(encoding="utf-8"))["features"]
        for feature in features:
            props, point = feature["properties"], feature["geometry"]
            if point is None or point["type"] != "Point":
                continue
            branch = nace_branch(props.get("eigl_nace")) or label_branch(props.get("eigl_sector"))
            if branch is None:
                continue
            extra_rows.append(dict(facility_id="EIGL_" + str(props["objectid"]),
                facility_name=props.get("ets_name") or props.get("e_prtr_2_productionfacility_nam"),
                longitude=point["coordinates"][0], latitude=point["coordinates"][1], branch=branch,
                metric=1., metric_unit="facility_count", evidence_source="EIGL_facility", evidence_year=None))
    extra = assign_regions(pd.DataFrame(extra_rows, columns=["facility_id", "facility_name", "longitude", "latitude", "branch",
                "metric", "metric_unit", "evidence_source", "evidence_year"]), nuts)
    return ets, ied, extra


def branch_weights(ets, ied, zones, branches=BRANCHES, eigl=None):
    records, choices = [], []
    zones = sorted(set(zones))
    # Used only for branches without sector-specific registry coverage. This is
    # an explicitly flagged default from industrial sites, not a population map.
    density = ied.groupby("nuts").metric.sum().reindex(zones, fill_value=0.)
    if density.sum() <= 0:
        density = ets.groupby("nuts").size().reindex(zones, fill_value=0.).astype(float)
    if density.sum() <= 0 and eigl is not None:
        density = eigl.groupby("nuts").size().reindex(zones, fill_value=0.).astype(float)
    for branch in branches:
        evidence = ets.loc[ets.branch.eq(branch)]
        basis = "EU_ETS_verified_emissions_selected_year"
        if evidence.empty:
            evidence = ied.loc[ied.branch.eq(branch)]
            basis = "EEA_IED_sector_facility_density"
        if evidence.empty and eigl is not None:
            evidence = eigl.loc[eigl.branch.eq(branch)]
            basis = "EIGL_sector_facility_density_static_inventory"
        values = evidence.groupby("nuts").metric.sum().reindex(zones, fill_value=0.)
        if values.sum() <= 0:
            values = density
            basis = "assumed_all_industrial_site_density_missing_sector_coverage"
        if values.sum() <= 0:
            raise ValueError(f"No industrial facility evidence for {branch}; population/equal allocation is not a paper-method substitute")
        shares = values / values.sum()
        for zone in zones:
            records.append(dict(nuts=zone, branch=branch, weight=float(shares.loc[zone]), allocation_basis=basis))
        choices.append(dict(branch=branch, basis=basis, facility_records=len(evidence),
                            assumption=basis.startswith("assumed_")))
    return pd.DataFrame(records), choices


def prepare_weights(cache, nuts, country, year, *, download=True, refresh=False):
    cache = Path(cache)
    tables = ensure_ets(cache, download=download, refresh=refresh)
    ied = ensure_ied(cache, country, year, download=download, refresh=refresh)
    eigl = ensure_eigl(cache, country, nuts, download=download, refresh=refresh)
    ets, sites, extra = observations(tables, ied, country, year, nuts, eigl)
    weights, choices = branch_weights(ets, sites, nuts.NUTS_ID, eigl=extra)
    source_files = [tables / name for name in TABLES if name.endswith(".csv")] + [ied, eigl]
    provenance = dict(source_priority="Within each sector: ETS selected-year verified emissions; otherwise IED, then EIGL sector facility density. Missing-sector coverage uses explicitly flagged industrial-site density. Overlapping inventories are alternatives and are not added twice.",
                      year=year, ETS_installations=len(ets), IED_sites=len(sites), EIGL_sites=len(extra), sectors=choices,
                      sources=[dict(file=str(path.resolve()), sha256=digest(path),
                                    url=IED_QUERY if path == ied else EIGL_QUERY if path == eigl else ETS_URL) for path in source_files])
    evidence = pd.concat([pd.DataFrame(frame.drop(columns="geometry")) for frame in (ets, sites, extra)], ignore_index=True)
    return weights, evidence, provenance
