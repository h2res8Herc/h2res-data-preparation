"""Aggregate mapped OSM electricity lines crossing regional boundaries for H2RES."""
from collections import Counter, defaultdict
import hashlib
import json
import math
import re
from pathlib import Path
from tempfile import NamedTemporaryFile

import pandas as pd

METHOD = "osm_boundary_crossings_v2"
DEFAULT_VOLTS = 35000
FILENAME = "transmission_osm.json"
LINE_TYPES = "https://github.com/PyPSA/PyPSA/blob/master/pypsa/data/standard_types/line_types.csv"
# Representative overhead line types (nominal current in kA per circuit).
AC_CURRENTS = ((750000, 4.16), (380000, 2.58), (300000, 1.935), (220000, 1.29),
               (110000, .645), (1000, .21), (0, .105))


def map_signature(mapping):
    systems = mapping.get("system_new", mapping.country)
    rows = sorted(set(zip(mapping.country, mapping.nuts3, systems, mapping.zone)))
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()


def tagged_volts(token):
    """OSM uses volts by default. Accept explicitly labelled volts and kilovolts."""
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(kv|v)?", token.strip(), re.I)
    if match:
        value = float(match[1]) * (1000 if (match[2] or "").lower() == "kv" else 1)
        if value > 0 and value.is_integer():
            return int(value)
    return None


def rating(tags):
    """Use explicitly aligned voltage/circuit tags and conservative model assumptions."""
    try:
        volts = [tagged_volts(v) for v in tags.get("voltage", "").split(";")]
        circuits = [int(v) for v in tags["circuits"].split(";")] if tags.get("circuits") else [1] * len(volts)
        frequencies = [float(f) for f in tags.get("frequency", "50").split(";")]
    except ValueError:
        return []
    if len(frequencies) == 1:
        frequencies *= len(volts)
    if len(circuits) != len(volts) or len(frequencies) != len(volts):
        return []
    result = []
    cables = tags.get("cables", "").split(";")
    for i, (mapped_voltage, count, frequency) in enumerate(zip(volts, circuits, frequencies)):
        if count <= 0 or frequency not in (0, 50, 60):
            continue
        voltage = mapped_voltage or DEFAULT_VOLTS
        dc = frequency == 0
        circuit_basis = "tag" if tags.get("circuits") else "one per voltage"
        if not dc and not tags.get("circuits") and len(cables) == len(volts) and cables[i].isdigit():
            conductors = int(cables[i])
            if conductors >= 3 and conductors % 3 == 0:
                count = conductors // 3
                circuit_basis = "three AC conductors per circuit"
        if dc:
            current = 1.  # Scenario DC current, assuming line voltage is the transfer voltage.
        elif tags.get("power") == "cable":
            current = .588  # 300 mm² AC cable as a common proxy.
        else:
            current = next(amps for threshold, amps in AC_CURRENTS if voltage >= threshold)
        mw = voltage / 1000 * current * count * (1 if dc else math.sqrt(3))
        result.append(dict(unit_name="HVDC" if dc else "400kV_AC", volts=voltage,
                           assumed_voltage=mapped_voltage is None,
                           circuits=count, circuit_basis=circuit_basis, assumed_current_kA=current,
                           frequency_hz=frequency, assumed_frequency=not bool(tags.get("frequency")),
                           estimated_mw=mw))
    return result


def line_parts(geometry):
    if geometry.geom_type == "LineString":
        yield geometry
    elif hasattr(geometry, "geoms"):
        for part in geometry.geoms:
            yield from line_parts(part)


def trace_regions(line, regions):
    """Return ordered runs through polygon interiors, with distances along the way."""
    from shapely.geometry import Point
    runs = []
    for idx in regions.sindex.query(line, predicate="intersects"):
        polygon = regions.geometry.iloc[idx]
        for part in line_parts(line.intersection(polygon)):
            if part.length == 0 or not polygon.contains(part.interpolate(.5, normalized=True)):
                continue  # Tangencies and sections lying on a boundary have no assigned side.
            ends = [line.project(Point(part.coords[i])) for i in (0, -1)]
            runs.append((min(ends), max(ends), regions.index[idx]))
    return sorted(runs)


def corridor_capacities(crossings, geography):
    capacities = Counter()
    counted = set()
    for event in crossings:
        a = geography.get(event["nuts3_from"])
        b = geography.get(event["nuts3_to"])
        if a is None or b is None or a == b:
            continue
        a, b = sorted((a, b))
        identity = (tuple(event["way_ids"]), a, b)
        if identity in counted:
            continue
        counted.add(identity)
        for r in event["ratings"]:
            capacities[a, b, r["unit_name"]] += r["estimated_mw"]
    return capacities


def extract(paths, nuts, mapping):
    import geopandas as gpd
    import osmium
    from shapely import wkb
    from transport.script.osm_infrastructure import file_hash

    regions = gpd.read_file(nuts).to_crs(4326).set_index("NUTS_ID")
    if not regions.index.is_unique or set(mapping.nuts3) - set(regions.index):
        raise ValueError("Transmission geography does not match the selected NUTS3 boundaries")
    regions.geometry = regions.geometry.make_valid()
    zones = dict(zip(mapping.nuts3, zip(mapping.get("system_new", mapping.country), mapping.zone)))
    model_geo = regions.loc[mapping.nuts3].copy()
    model_geo["key"] = [zones[n] for n in model_geo.index]
    centers = model_geo.to_crs(3035).dissolve(by="key").geometry.representative_point().to_dict()
    crossings, endpoints, seen = {}, defaultdict(list), set()
    counts = Counter()
    factory = osmium.geom.WKBFactory()

    def record(ids, a, b, ratings):
        if a == b or (a not in zones and b not in zones):
            return
        a, b = sorted((a, b))
        crossings[tuple(ids), a, b] = dict(way_ids=list(ids), nuts3_from=a, nuts3_to=b, ratings=ratings)

    class Handler(osmium.SimpleHandler):
        def way(self, way):
            if way.tags.get("power") not in ("line", "minor_line", "cable") or way.id in seen:
                return
            tags = dict(way.tags)
            if any(tags.get(k) == "yes" for k in ("disused", "abandoned", "construction", "proposed")):
                return
            ratings = rating(tags)
            if not ratings:
                counts["unusable_circuit_or_frequency_tags"] += 1
                return
            try:
                line = wkb.loads(factory.create_linestring(way), hex=True)
            except (RuntimeError, ValueError):
                counts["unusable_geometry"] += 1
                return
            seen.add(way.id)
            runs = trace_regions(line, regions)
            if not runs:
                return
            counts["qualified_ways_intersecting_regions"] += 1
            if any(r["assumed_voltage"] for r in ratings):
                counts["ways_with_assumed_voltage_intersecting_regions"] += 1
            for previous, following in zip(runs, runs[1:]):
                gap = following[0] - previous[1]
                submarine = tags.get("location") in ("underwater", "submarine") and tags["power"] == "cable"
                if abs(gap) < 1e-8 or (submarine and gap > 0):
                    record([way.id], previous[2], following[2], ratings)
            # Adjacent ways may end exactly at a border. Join only a unique
            # continuous pair at a shared OSM node with matching electrical tags.
            for pos, node, run, edge in ((0., way.nodes[0], runs[0], 0),
                                         (line.length, way.nodes[-1], runs[-1], 1)):
                if abs(run[edge] - pos) < 1e-8:
                    endpoints[node.ref].append((way.id, run[2], ratings))

    sources = []
    for country, path in sorted(paths.items()):
        print(f"Extracting OSM transmission lines from {path.name}", flush=True)
        sources.append(dict(country=country, file=path.name, sha256=file_hash(path)))
        Handler().apply_file(str(path), locations=True, filters=[osmium.filter.KeyFilter("power")])
    def electrical_signature(ratings):
        return [(r["volts"], r["circuits"], r["assumed_current_kA"], r["frequency_hz"]) for r in ratings]

    for members in endpoints.values():
        if len(members) == 2:
            first, second = members
            if first[0] != second[0] and electrical_signature(first[2]) == electrical_signature(second[2]):
                joined = []
                for i, r in enumerate(first[2]):
                    assumed_ids = sorted(m[0] for m in members if m[2][i]["assumed_voltage"])
                    joined.append(dict(r, assumed_voltage=bool(assumed_ids), assumed_voltage_way_ids=assumed_ids))
                record(sorted([first[0], second[0]]), first[1], second[1], joined)

    capacities = corridor_capacities(crossings.values(), zones)
    country_by_region = (regions.CNTR_CODE.to_dict() if "CNTR_CODE" in regions
                         else {n: n[:2] for n in regions.index})
    national = corridor_capacities(crossings.values(), country_by_region)
    corridors = [dict(System=a[0], zone=a[1], To=b[0], zoneTo=b[1], unit_name=tech,
                      cap_mw=mw, km=centers[a].distance(centers[b]) / 1000)
                 for (a, b, tech), mw in sorted(capacities.items())]
    return dict(method=METHOD, attribution="© OpenStreetMap contributors (ODbL), Geofabrik extracts",
                mapping_sha256=map_signature(mapping), boundary_sha256=file_hash(nuts),
                sources=sources, counts=dict(counts),
                voltage_default_V=DEFAULT_VOLTS,
                capacity_basis="Representative overhead currents by voltage, including 0.105 kA below 1 kV and 0.21 kA from 1 to below 110 kV. AC cable 0.588 kA, unity AC power factor. DC 1 kA at transfer voltage.",
                line_type_source=LINE_TYPES,
                distance_basis="EPSG:3035 distance between model-zone representative points",
                crossings=list(crossings.values()), corridors=corridors,
                country_border_estimates=[dict(country_from=a, country_to=b, unit_name=t, cap_mw=mw)
                                          for (a,b,t), mw in sorted(national.items())])


def prepare(countries, data_root, nuts, mapping, output, refresh=False):
    from transport.script.generate_transport_inputs_standalone import download_country_pbfs
    cache = Path(data_root) / "transport"
    paths = {c: cache / "osm" / (c + ".osm.pbf") for c in countries}
    required = [c for c, p in paths.items() if refresh or not p.is_file()]
    if required:
        download_country_pbfs(required, cache, refresh)
    result = extract(paths, nuts, mapping[mapping.country.isin(countries)])
    output.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=output, delete=False) as tmp:
        json.dump(result, tmp, indent=2)
    Path(tmp.name).replace(output / FILENAME)
    print(f"Prepared {len(result['corridors'])} OSM zone-pair/technology records in {output / FILENAME}", flush=True)


def read_prepared(path, mapping, targets):
    grid = json.loads(path.read_text(encoding="utf-8"))
    if grid.get("method") != METHOD:
        raise ValueError("Prepared OSM transmission inventory uses an older or unknown voltage method. Regenerate the grid using the existing OSM cache (python -m power.osm_transmission).")
    if grid.get("mapping_sha256") != map_signature(mapping):
        raise ValueError("Prepared OSM transmission geography differs from this export. Generate the power data again.")
    seen = set()
    for row in grid["corridors"]:
        a, b = (row["System"], row["zone"]), (row["To"], row["zoneTo"])
        key = (*sorted((a, b)), row["unit_name"])
        if (a not in targets or b not in targets or a == b or key in seen
                or row["unit_name"] not in ("400kV_AC", "HVDC")
                or any(not math.isfinite(row[k]) or row[k] <= 0 for k in ("cap_mw", "km"))):
            raise ValueError(f"Invalid prepared OSM transmission corridor {key}")
        seen.add(key)
    return grid


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Prepare only the OSM grid for an existing H2RES zone map.")
    parser.add_argument("--out-root", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--nuts3", type=Path, default=Path(__file__).parent / "data/NUTS_RG_20M_2021_4326_LEVL_3.geojson")
    parser.add_argument("--refresh-sources", action="store_true")
    args = parser.parse_args()
    zone_map = pd.read_csv(args.out_root / "_zone_maps/zone_map_common.csv")
    prepare(sorted(zone_map.country.unique()), args.data_root, args.nuts3, zone_map,
            args.out_root / "power", args.refresh_sources)
