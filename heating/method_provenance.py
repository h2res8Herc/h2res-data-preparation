"""Bind cached heat calculations to their actual paper-method inputs."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path


@lru_cache(maxsize=128)
def _hash(path, size, modified):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_hash(path):
    path = Path(path).resolve()
    stat = path.stat()
    return _hash(str(path), stat.st_size, stat.st_mtime_ns)


def raw_fingerprint(args, sources, country):
    from heating.generate_heating_inputs_standalone import find_idees_workbook
    files = {name: sources[name] for name in ("nuts", "population", "hotmaps", "powerplants", "calculator")}
    for sector in ("Residential", "Tertiary"):
        files[sector] = find_idees_workbook(sources["idees"], country, sector)
    for path in sorted(sources["eigl"].glob("*.tif")):
        files["EIGL/" + path.name] = path
    for name in ("paper_weather.py", "paper_calculator.py"):
        files[name] = Path(__file__).parent / name
    if sources["era5"].is_file():
        files["ERA5_NetCDF"] = sources["era5"]
    inputs = {name: dict(file=str(Path(path).resolve()), sha256=file_hash(path)) for name, path in files.items()}
    parameters = dict(country=country, year=args.source_year, weather_points=args.weather_points,
                      weather_seed=args.weather_seed, dh_chp_lambda=args.dh_chp_lambda,
                      weather_source="open_meteo_era5_land" if sources["era5"].is_dir() else "ERA5_NetCDF")
    payload = dict(method_id="paper_heating_v1", parameters=parameters,
                   inputs={key: value["sha256"] for key, value in inputs.items()})
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return dict(fingerprint=fingerprint, inputs=inputs, **{k:v for k,v in payload.items() if k != "inputs"})


def raw_cache_matches(output, identity):
    path = output / "paper_generation.json"
    if not path.is_file():
        return False
    saved = json.loads(path.read_text(encoding="utf-8"))
    return (saved.get("fingerprint") == identity["fingerprint"] and saved.get("complete") and bool(saved.get("outputs"))
            and all((output / name).is_file() and file_hash(output / name) == digest
                    for name, digest in saved.get("outputs", {}).items()))


def write_raw_manifest(output, identity):
    details = json.loads((output / "paper_method_details.json").read_text(encoding="utf-8"))
    if details.get("weather_points") != identity["parameters"]["weather_points"]:
        raise ValueError("Heating weather sampling differs from requested configuration")
    files = [path for path in output.glob("*.csv")]
    saved = dict(**identity, complete=True, method_details=details,
                 outputs={path.name: file_hash(path) for path in files})
    (output / "paper_generation.json").write_text(json.dumps(saved, indent=2), encoding="utf-8")
