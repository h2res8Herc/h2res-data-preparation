"""Airport passenger arrivals and departures, separately for domestic and international traffic."""
from io import BytesIO
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

import geopandas as gpd
import numpy as np
import pandas as pd
import requests

EUROSTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/avia_paoa"
LOCATIONS = "https://raw.githubusercontent.com/davidmegginson/ourairports-data/main/airports.csv"
BUNDLED = Path(__file__).with_name("international_airport_passengers_2020.csv")
BASIS = "international_airport_passengers"
FALLBACK = "assumed_OSM_aviation_no_located_passenger_evidence"
OSIJEK = "https://osijek-airport.hr/wp-content/uploads/2022/03/Godisnje-izvjesce-Uprave-o-stanju-Drustva-za-2020.-godinu.pdf"
OSIJEK_DOMESTIC = "https://osijek-airport.hr/files/documents/53/Srednjoro%C4%8Dni%20plan%20poslovanja%202022.%20-2024..pdf"
# DZS annual airport traffic, December release, table 2. Only fills Eurostat gaps.
HR_TOTALS = {
    2019: {"LDZA": 3409977, "LDSP": 3271045, "LDDU": 2877801, "LDZD": 782574,
           "LDPL": 765508, "LDRI": 197151, "LDOS": 45697, "LDLO": 3385, "LDSB": 23777},
    2020: {"LDZA": 913703, "LDSP": 659350, "LDDU": 322601, "LDZD": 111179,
           "LDPL": 78832, "LDRI": 25460, "LDOS": 6382, "LDLO": 1156, "LDSB": 3369},
}
# Airport host counties in NUTS 2021, including island and boundary airports.
HR_HOSTS = {"LDZA": "HR065", "LDSP": "HR035", "LDDU": "HR037", "LDZD": "HR033",
            "LDPL": "HR036", "LDRI": "HR031", "LDOS": "HR025", "LDLO": "HR031", "LDSB": "HR035"}
HOSTS = {"HR": HR_HOSTS, "DE": {"EDDT": "DE300"}, "IT": {"LICD": "ITG14"}, "FR": {"FMCZ": "FRY50"}}


def counts(year, coverage):
    params = dict(time=year, freq="A", unit="PAS", schedule="TOTAL", tra_meas="PAS_CRD", tra_cov=coverage)
    response = requests.get(EUROSTAT, params=params, timeout=90)
    response.raise_for_status()
    data = response.json()
    axis = data["id"].index("rep_airp")
    if any(size != 1 for i, size in enumerate(data["size"]) if i != axis):
        raise ValueError(f"Unexpected Eurostat airport dimensions for {year}/{coverage}")
    codes = data["dimension"]["rep_airp"]["category"]["index"]
    return pd.Series({key: data["value"][str(pos)] for key, pos in codes.items()
                      if str(pos) in data["value"] and data["value"][str(pos)] is not None},
                     dtype=float)


def passenger_table(year, domestic, international, total):
    df = pd.concat([domestic.rename("domestic"), international.rename("international"), total.rename("total")], axis=1)
    df = df.loc[df.index.str.fullmatch(r"[A-Z]{2}_[A-Z0-9]{4}")].copy()
    if df.empty:
        raise ValueError(f"No Eurostat airport passenger observations for {year}")
    # Subtract only matched Eurostat series, before introducing other sources or estimates.
    residual = df.total - df.international
    derived = df.domestic.isna() & residual.ge(0)
    df["domestic_basis"] = "Eurostat_reported_domestic"
    df.loc[derived, "domestic"] = residual[derived]
    df.loc[derived, "domestic_basis"] = "Eurostat_total_minus_reported_international"
    # Same-source pairs provide a domestic fraction for airports reporting only total traffic.
    paired = df.loc[df.domestic.ge(0) & df.domestic.le(df.total) & df.total.gt(0)].copy()
    domestic_pairs = paired.groupby(paired.index.str[:2])[["domestic", "total"]].sum()
    domestic_fraction = domestic_pairs.domestic / domestic_pairs.total
    df["basis"] = "Eurostat_reported_international"
    if year in HR_TOTALS:
        for airport, total in HR_TOTALS[year].items():
            key = "HR_" + airport
            if key not in df.index or pd.isna(df.at[key, "total"]):
                df.loc[key, "total"] = total
        if pd.isna(df.at["HR_LDOS", "international"]):
            df.loc["HR_LDOS", ["international", "basis"]] = (
                {2019: 32963 + 1066, 2020: 868 + 407}[year], "Osijek_operator_international")
        if pd.isna(domestic.get("HR_LDOS")):
            df.loc["HR_LDOS", ["domestic", "domestic_basis"]] = (
                {2019: 12354, 2020: 5351}[year], "Osijek_operator_reported_domestic")
    df["country"] = df.index.str[:2]
    df["icao"] = df.index.str[3:]
    pairs = df.loc[df.international.notna() & df.total.gt(0)].groupby("country")[["international", "total"]].sum()
    ratios = pairs.international.div(pairs.total).clip(0, 1)
    missing = df.international.isna()
    df.loc[missing, "basis"] = "all_passengers_times_country_international_fraction"
    df.loc[missing, "international"] = df.loc[missing, "total"] * df.loc[missing, "country"].map(ratios)
    missing = df.domestic.isna()
    df.loc[missing, "domestic"] = df.loc[missing, "total"] * df.loc[missing, "country"].map(domestic_fraction)
    df.loc[missing, "domestic_basis"] = "all_passengers_times_country_domestic_fraction"
    # A total-only airport must use one coherent estimated split for both traffic types.
    shared_split = missing & df.basis.eq("all_passengers_times_country_international_fraction") & df.international.notna()
    df.loc[shared_split, "domestic"] = df.loc[shared_split, "total"] - df.loc[shared_split, "international"]
    return df


def download(year):
    df = passenger_table(year, counts(year, "NAT"), counts(year, "INTL"), counts(year, "TOTAL"))
    response = requests.get(LOCATIONS, timeout=90)
    response.raise_for_status()
    airports = pd.read_csv(BytesIO(response.content), usecols=["ident", "latitude_deg", "longitude_deg"])
    df = df.join(airports.set_index("ident"), on="icao", validate="many_to_one")
    df["year"] = year
    return df[["year", "country", "icao", "international", "total", "basis", "longitude_deg", "latitude_deg",
               "domestic", "domestic_basis"]]


def snapshot(cache, year, refresh):
    path = Path(cache) / "airport_passengers" / f"airport_passengers_by_traffic_{year}.csv"
    existing = path if path.is_file() else BUNDLED if year == 2020 and BUNDLED.is_file() else None
    if existing and not refresh:
        return existing
    try:
        frame = download(year)
    except (requests.RequestException, ValueError, KeyError) as exc:
        if existing is None:
            raise ValueError(f"Cannot obtain airport passenger observations for {year}: {exc}") from exc
        print(f"WARNING: Airport refresh failed for {year}; using {existing}: {exc}", flush=True)
        return existing
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, mode="w", encoding="utf-8", newline="", delete=False) as temp:
        frame.to_csv(temp, index=False)
    os.replace(temp.name, path)
    return path


def regional_weights(source, regions, country, year, traffic="international"):
    if traffic not in ("domestic", "international"):
        raise ValueError(f"Unknown airport traffic type: {traffic}")
    frame = pd.read_csv(source)
    country_code = {"GR": "EL", "GB": "UK"}.get(country, country)
    airports = frame.loc[frame.country.eq(country_code) & frame.year.eq(year)]
    missing = airports.loc[airports[traffic].isna(), "icao"].tolist()
    airports = airports.loc[airports[traffic].notna()]
    if (airports.icao.duplicated().any() or not np.isfinite(airports[traffic]).all()
            or airports[traffic].lt(0).any()):
        raise ValueError(f"Invalid passenger observations for {country}/{year}")
    polygons = regions.set_index("NUTS_ID").to_crs(3035)
    sums = pd.Series(0., index=polygons.index)
    report = dict(year=year, snapshot=str(source.resolve()), eurostat=EUROSTAT, coordinates=LOCATIONS,
                  airports=[], traffic=traffic, airports_without_counts=missing, basis=f"{traffic}_airport_passengers")
    if country == "HR" and year in HR_TOTALS:
        report.update(osijek_report=OSIJEK_DOMESTIC if traffic == "domestic" else OSIJEK,
                      all_passenger_source=f"https://web.dzs.hr/Hrv_Eng/publication/{year}/05-01-03_12_{year}.htm")
    located = airports.dropna(subset=["longitude_deg", "latitude_deg"])
    points = gpd.GeoSeries(gpd.points_from_xy(located.longitude_deg, located.latitude_deg),
                           index=located.icao, crs=4326).to_crs(3035)
    for airport in airports.itertuples():
        zone = HOSTS.get(country, {}).get(airport.icao)
        location_basis = "airport_host_region"
        if zone not in polygons.index:
            zone = None
            location_basis = "unlocated"
            if airport.icao in points.index:
                distances = polygons.distance(points[airport.icao])
                nearest = distances.idxmin()
                if distances[nearest] <= 5000:
                    zone = nearest
                    location_basis = "airport_coordinates"
        value = getattr(airport, traffic)
        if zone is not None:
            sums[zone] += value
        report["airports"].append(dict(icao=airport.icao, nuts3=zone, passengers=value,
                                       basis=airport.domestic_basis if traffic == "domestic" else airport.basis,
                                       location_basis=location_basis))
    report["located_passengers"] = float(sums.sum())
    report["unlocated_passengers"] = sum(a["passengers"] for a in report["airports"] if a["nuts3"] is None)
    if not sums.sum():
        report["basis"] = FALLBACK
    return sums, report
