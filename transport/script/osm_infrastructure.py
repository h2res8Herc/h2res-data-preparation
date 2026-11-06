"""OSM infrastructure indicators used by the transport method in the paper.

Read PBF through the Python libosmium bindings, without an external osmium
executable. Parser failures propagate instead of masquerading as absent rail,
airports or ports. Lengths and areas are clipped to regional boundaries.
"""
from functools import lru_cache
import hashlib
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point, mapping
from shapely import wkb

KINDS = ("rail_lines", "rail_stations", "ports_polys", "ports_points",
         "quays_lines", "runways_lines", "aerodrome_points")
VERSION = "paper-infrastructure-1"


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _port(tags):
    return (tags.get("landuse") == "port" or tags.get("industrial") == "port"
            or tags.get("harbour") not in (None, "no", "false", "0")
            or tags.get("seamark:type") == "harbour" or tags.get("amenity") == "ferry_terminal")


@lru_cache(maxsize=1)
def read_features(path_string, digest):
    import osmium

    path = Path(path_string)
    cache = path.parent / (path.name + ".h2res_infrastructure")
    metadata = cache / "source.json"
    if metadata.is_file():
        saved = json.loads(metadata.read_text(encoding="utf-8"))
        if saved.get("sha256") == digest and saved.get("version") == VERSION and all((cache / (kind + ".geojson")).is_file() for kind in KINDS):
            return {kind: gpd.read_file(cache / (kind + ".geojson")) for kind in KINDS}, saved
    rows = {kind: [] for kind in KINDS}
    geometry = osmium.geom.WKBFactory()
    counts = dict(nodes=0, ways=0, invalid_geometries=0)

    def add(kind, tags, shape, identity):
        rows[kind].append({**tags, "osm_id": identity, "geometry": shape})

    class Handler(osmium.SimpleHandler):
        def node(self, node):
            counts["nodes"] += 1
            tags = dict(node.tags)
            railway = tags.get("railway")
            station = railway in {"station", "halt", "stop", "tram_stop", "subway_entrance"}
            station |= (tags.get("public_transport") in {"station", "stop_position"}
                        and any(tags.get(mode) == "yes" for mode in ("train", "tram", "subway", "light_rail")))
            kinds = (["rail_stations"] if station else [])
            if _port(tags):
                kinds.append("ports_points")
            if tags.get("aeroway") == "aerodrome":
                kinds.append("aerodrome_points")
            if kinds and node.location.valid():
                point = Point(node.location.lon, node.location.lat)
                for kind in kinds:
                    add(kind, tags, point, "n" + str(node.id))

        def way(self, way):
            counts["ways"] += 1
            tags = dict(way.tags)
            kinds = []
            if tags.get("railway") in {"rail", "narrow_gauge", "monorail", "funicular", "tram", "subway", "light_rail"}:
                kinds.append("rail_lines")
            if tags.get("man_made") == "quay" or tags.get("harbour") == "quay":
                kinds.append("quays_lines")
            if tags.get("aeroway") == "runway":
                kinds.append("runways_lines")
            if kinds:
                try:
                    line = wkb.loads(geometry.create_linestring(way), hex=True)
                    for kind in kinds:
                        add(kind, tags, line, "w" + str(way.id))
                except (RuntimeError, ValueError):
                    counts["invalid_geometries"] += 1

        def area(self, area):
            tags = dict(area.tags)
            if not (_port(tags) or tags.get("aeroway") == "aerodrome"):
                return
            try:
                polygon = wkb.loads(geometry.create_multipolygon(area), hex=True)
                if not polygon.is_valid:
                    polygon = polygon.buffer(0)
                if polygon.is_empty:
                    return
                identity = ("w" if area.from_way() else "r") + str(area.orig_id())
                if _port(tags):
                    add("ports_polys", tags, polygon, identity)
                if tags.get("aeroway") == "aerodrome":
                    add("aerodrome_points", tags, polygon.representative_point(), identity)
            except (RuntimeError, ValueError):
                counts["invalid_geometries"] += 1

    print(f"Reading actual OSM transport infrastructure: {path.name}", flush=True)
    Handler().apply_file(str(path), locations=True, filters=[osmium.filter.KeyFilter(
        "railway", "public_transport", "harbour", "seamark:type", "landuse",
        "industrial", "man_made", "aeroway", "amenity")])
    cache.mkdir(parents=True, exist_ok=True)
    frames = {}
    for kind, records in rows.items():
        frames[kind] = (gpd.GeoDataFrame(records, crs="EPSG:4326") if records
                        else gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"))
        collection = dict(type="FeatureCollection", features=[dict(type="Feature", geometry=mapping(record["geometry"]),
                          properties={key: value for key, value in record.items() if key != "geometry"}) for record in records])
        target = cache / (kind + ".geojson")
        partial = target.with_suffix(".geojson.part")
        partial.write_text(json.dumps(collection), encoding="utf-8")
        partial.replace(target)
    saved = dict(version=VERSION, source=str(path.resolve()), sha256=digest, parser="pyosmium",
                 object_counts=counts, feature_counts={kind: len(value) for kind, value in frames.items()})
    metadata.write_text(json.dumps(saved, indent=2), encoding="utf-8")
    print("OSM infrastructure feature counts: " + str(saved["feature_counts"]), flush=True)
    return frames, saved


def measure(features, nuts, mode):
    """Allocate each clipped piece once; boundary points go to one region."""
    if features.empty:
        return np.zeros(len(nuts))
    local = features.to_crs(nuts.crs).copy().reset_index(drop=True)
    local["_feature"] = np.arange(len(local))
    regions = gpd.GeoDataFrame(dict(_region=np.arange(len(nuts))), geometry=list(nuts.geometry), crs=nuts.crs)
    joined = gpd.sjoin(local[["_feature", "geometry"]], regions, how="inner", predicate="intersects")
    if joined.empty:
        return np.zeros(len(nuts))
    if mode == "count":
        joined = joined.sort_values("_region").drop_duplicates("_feature")
        values = np.ones(len(joined))
    else:
        clips = [shape.intersection(regions.geometry.iloc[int(index)])
                 for shape, index in zip(joined.geometry, joined._region)]
        values = np.array([shape.length / 1000 if mode == "length" else shape.area / 1e6 for shape in clips])
    return np.bincount(joined._region.to_numpy(dtype=int), weights=values, minlength=len(nuts))


def weights(nuts, pbf_path, coastal_types, metric_crs="EPSG:3035", include_inland=False):
    path = Path(pbf_path)
    features, provenance = read_features(str(path.resolve()), file_hash(path))
    regions = nuts.to_crs(metric_crs)
    rail = features["rail_lines"].copy()
    if rail.empty:
        rail["railway"] = pd.Series(dtype=str)
    electrified = rail.get("electrified", pd.Series("", index=rail.index)).fillna("").str.lower()
    electric = electrified.isin({"yes", "contact_line", "rail", "overhead", "third_rail", "fourth_rail"})
    urban = rail.railway.isin({"tram", "subway", "light_rail"})
    rail_table = pd.DataFrame(index=nuts.index)
    for name, selected in {
        "rail_main_km_el": ~urban & electric, "rail_main_km_nonel": ~urban & ~electric,
        "rail_urban_km_el": urban & electric, "rail_urban_km_nonel": urban & ~electric,
    }.items():
        rail_table[name] = measure(rail.loc[selected], regions, "length")
    rail_table["rail_station_ct"] = measure(features["rail_stations"], regions, "count")
    quay = measure(features["quays_lines"], regions, "length")
    ports = measure(features["ports_points"], regions, "count")
    area = measure(features["ports_polys"], regions, "area")
    points = features["ports_points"]
    cargo = points.loc[points.get("industrial", pd.Series("", index=points.index)).str.contains("port|harbour|cargo", case=False, na=False)]
    cargo_count = measure(cargo, regions, "count")
    coast = nuts.NUTS_ID.map(coastal_types).isin([1, 2]).to_numpy()
    freight = 20 * quay + 50 * cargo_count + 50 * area + .5 * ports
    passenger = 30 * quay + 2 * ports + 5 * area
    shipping = pd.DataFrame(dict(ship_freight=freight * coast,
                                 ship_passenger=passenger * coast), index=nuts.index)
    if include_inland:
        shipping['ship_inland_freight'] = freight
        shipping['ship_inland_passenger'] = passenger
    aviation = pd.Series(100 * measure(features["runways_lines"], regions, "length")
                         + 50 * measure(features["aerodrome_points"], regions, "count"), index=nuts.index)
    return rail_table, shipping, aviation, provenance
