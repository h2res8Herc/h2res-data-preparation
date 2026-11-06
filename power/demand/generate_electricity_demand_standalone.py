#!/usr/bin/env python3
"""Download ENTSO-E actual load and allocate it to NUTS3/model zones.

National hourly load is downloaded from the ENTSO-E Transparency Platform and
cached as monthly XML. JRC EIGL 2019 NUTS3 electricity-demand totals provide
normalized spatial shares. The shares are suitable for other load years: every
hour is reconciled exactly to the corresponding national ENTSO-E value.
"""

from __future__ import annotations

import argparse
import calendar
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pandas as pd
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from h2res_input_schema import model_calendar


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_WEIGHTS = SCRIPT_DIR / "eigl_nuts3_2019_correct"
ENDPOINT = "https://web-api.tp.entsoe.eu/api"

# ENTSO-E domains used for Actual Total Load (A65/A16). EL is the NUTS code for
# Greece. Germany uses the post-2018 DE-LU bidding zone.
AREAS = {
    "AT": "10YAT-APG------L", "BE": "10YBE----------2",
    "BG": "10YCA-BULGARIA-R", "CY": "10YCY-1001A0003J",
    "CZ": "10YCZ-CEPS-----N", "DE": "10Y1001A1001A83F",
    "DK": "10Y1001A1001A65H", "EE": "10Y1001A1001A39I",
    "EL": "10YGR-HTSO-----Y", "ES": "10YES-REE------0",
    "FI": "10YFI-1--------U", "FR": "10YFR-RTE------C",
    "HR": "10YHR-HEP------M", "HU": "10YHU-MAVIR----U",
    "IE": "10YIE-1001A00010", "IT": "10YIT-GRTN-----B",
    "LT": "10YLT-1001A0008Q", "LU": "10YLU-CEGEDEL-NQ",
    "LV": "10YLV-1001A00074", "MT": "10Y1001A1001A93C",
    "NL": "10YNL----------L", "PL": "10YPL-AREA-----S",
    "PT": "10YPT-REN------W", "RO": "10YRO-TEL------P",
    "SE": "10YSE-1--------K", "SI": "10YSI-ELES-----O",
    "SK": "10YSK-SEPS-----K",
}


def parse_csv(value: str) -> list[str]:
    return [x.strip().upper() for x in value.split(",") if x.strip()]


def month_bounds(year: int, month: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = pd.Timestamp(year=year, month=month, day=1, tz="UTC")
    end = start + pd.offsets.MonthBegin(1)
    return start, end


def download_month(country: str, year: int, month: int, token: str,
                   cache_dir: Path, refresh: bool, retries: int = 5) -> Path:
    out = cache_dir / country / str(year) / f"{month:02d}.xml"
    if out.exists() and out.stat().st_size > 100 and not refresh:
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    start, end = month_bounds(year, month)
    params = {
        "securityToken": token,
        "documentType": "A65",
        "processType": "A16",
        "outBiddingZone_Domain": AREAS[country],
        "out_Domain": AREAS[country],
        "periodStart": start.strftime("%Y%m%d%H%M"),
        "periodEnd": end.strftime("%Y%m%d%H%M"),
    }
    request = urllib.request.Request(
        ENDPOINT + "?" + urllib.parse.urlencode(params),
        headers={"User-Agent": "H2RES-portable-input-generator/1.0"},
    )
    last: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                payload = response.read()
            root = ET.fromstring(payload)
            reason = next((e.text for e in root.iter() if e.tag.endswith("reason") and e.text), None)
            text = next((e.text for e in root.iter() if e.tag.endswith("text") and e.text), None)
            if root.tag.endswith("Acknowledgement_MarketDocument"):
                raise RuntimeError(f"ENTSO-E rejected {country} {year}-{month:02d}: {reason or ''} {text or ''}".strip())
            out.write_bytes(payload)
            return out
        except Exception as exc:
            last = exc
            if attempt + 1 < retries:
                time.sleep(min(30, 2 ** attempt))
    raise RuntimeError(f"ENTSO-E download failed for {country} {year}-{month:02d}: {last}")


def duration_minutes(text: str) -> int:
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?", text or "")
    if not match:
        raise ValueError(f"Unsupported ENTSO-E resolution: {text}")
    return int(match.group(1) or 0) * 60 + int(match.group(2) or 0)


def parse_load_xml(path: Path) -> pd.Series:
    root = ET.parse(path).getroot()
    pieces: list[pd.Series] = []
    for period in (e for e in root.iter() if e.tag.endswith("Period")):
        interval = next((e for e in period if e.tag.endswith("timeInterval")), None)
        resolution = next((e.text for e in period if e.tag.endswith("resolution")), None)
        if interval is None or not resolution:
            continue
        start_text = next((e.text for e in interval if e.tag.endswith("start")), None)
        if not start_text:
            continue
        minutes = duration_minutes(resolution)
        values: dict[pd.Timestamp, float] = {}
        for point in (e for e in period if e.tag.endswith("Point")):
            pos = next((e.text for e in point if e.tag.endswith("position")), None)
            qty = next((e.text for e in point if e.tag.endswith("quantity")), None)
            if pos and qty:
                stamp = pd.Timestamp(start_text) + pd.Timedelta(minutes=(int(pos) - 1) * minutes)
                values[stamp] = float(qty)
        if values:
            pieces.append(pd.Series(values, dtype=float))
    if not pieces:
        raise ValueError(f"No load time series found in {path}")
    series = pd.concat(pieces).groupby(level=0).sum().sort_index()
    # Quantities are average MW for each market interval. Hourly model demand is
    # therefore the mean of 15/30-minute values, while multiple time series sum.
    return series.resample("1h").mean()


def national_load(country: str, year: int, token: str, cache_dir: Path,
                  refresh: bool) -> pd.Series:
    monthly = []
    for month in range(1, 13):
        print(f"ENTSO-E {country} {year}-{month:02d}", flush=True)
        monthly.append(parse_load_xml(download_month(country, year, month, token, cache_dir, refresh)))
    result = pd.concat(monthly).groupby(level=0).mean().sort_index()
    expected = pd.date_range(f"{year}-01-01", f"{year + 1}-01-01", inclusive="left", freq="1h", tz="UTC")
    result = result.reindex(expected)
    missing = int(result.isna().sum())
    if missing:
        result = result.interpolate(limit=6).ffill().bfill()
        print(f"WARNING: {country} filled {missing} missing hourly ENTSO-E values", flush=True)
    if result.isna().any():
        raise ValueError(f"Unresolved ENTSO-E gaps for {country} {year}")
    return result.clip(lower=0)


def load_weights(country: str, weights_dir: Path) -> pd.Series:
    path = weights_dir / f"{country}_NUTS3_2019_tot.csv"
    if not path.exists():
        raise FileNotFoundError(f"Packaged EIGL NUTS3 weights missing: {path}")
    frame = pd.read_csv(path)
    zone_col = next((c for c in frame if "nuts3" in c.lower()), None)
    value_col = next((c for c in frame if c.lower() == "gwh_tot"), None)
    if not zone_col or not value_col:
        raise ValueError(f"Cannot identify NUTS3/value columns in {path}")
    values = pd.to_numeric(frame[value_col], errors="coerce").fillna(0)
    weights = values.groupby(frame[zone_col].astype(str).str.upper()).sum()
    weights = weights[weights > 0]
    if weights.empty:
        raise ValueError(f"No positive EIGL weights in {path}")
    return weights / weights.sum()


def load_zone_map(path: Path | None) -> pd.DataFrame | None:
    if path is None:
        return None
    frame = pd.read_csv(path)
    aliases = {"country": "country", "System": "country", "nuts3": "nuts3", "NUTS3": "nuts3", "zone": "zone"}
    frame = frame.rename(columns={c: aliases[c] for c in frame if c in aliases})
    needed = {"country", "nuts3", "zone"}
    if not needed.issubset(frame.columns):
        raise ValueError("Zone map must contain country,nuts3,zone columns")
    return frame[list(needed)].astype(str)


def generate(args: argparse.Namespace) -> None:
    token = args.token or os.environ.get("ENTSOE_API_TOKEN") or os.environ.get("ENTSOE_TOKEN")
    if not token:
        raise ValueError("ENTSO-E token required: set ENTSOE_API_TOKEN or use --token")
    if any(country in {"ALL", "EU", "EUROPE"} for country in args.countries):
        args.countries = list(AREAS)
    unsupported = sorted(set(args.countries) - set(AREAS))
    if unsupported:
        raise ValueError(f"No ENTSO-E area mapping for: {unsupported}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    zone_map = load_zone_map(args.zone_map)
    final_paths = {
        "national": args.out_dir / f"national_load_{args.year}.csv",
        "nuts": args.out_dir / f"electricity_demand_nuts3_{args.year}.csv",
        "model": args.out_dir / f"electricity_demand_{args.year}.csv",
        "wide": args.out_dir / f"electricity_demand_wide_{args.year}.csv",
    }
    parts = {key: path.with_suffix(path.suffix + ".part") for key, path in final_paths.items()}
    for path in parts.values():
        path.unlink(missing_ok=True)
    national_rows: list[pd.DataFrame] = []
    wide_total: pd.DataFrame | None = None
    max_error = 0.0
    try:
        for country_number, country in enumerate(args.countries):
            load = national_load(country, args.year, token, args.cache_dir, args.refresh)
            weights = load_weights(country, args.weights_dir)
            timestamps = load.index.tz_convert(None)
            national = pd.DataFrame({"timestamp": timestamps, "System": country, "el_dem_mw": load.values})
            national_rows.append(national)
            matrix = np.outer(load.values, weights.values)
            long = pd.DataFrame(matrix, index=timestamps, columns=weights.index)
            long.index.name = "timestamp"
            long = long.stack().rename("el_dem_mw").reset_index()
            long.columns = ["timestamp", "zone", "el_dem_mw"]
            long.insert(1, "System", country)
            long.to_csv(parts["nuts"], mode="a", header=country_number == 0, index=False)
            model = long
            if zone_map is not None:
                local = zone_map[zone_map["country"].str.upper().eq(country)].copy()
                local["nuts3"] = local["nuts3"].str.upper()
                model = long.merge(local[["nuts3", "zone"]], left_on="zone", right_on="nuts3", how="left")
                if model["zone_y"].isna().any():
                    missing = sorted(model.loc[model["zone_y"].isna(), "zone_x"].unique())
                    raise ValueError(f"Unmapped demand NUTS3 zones for {country}: {missing}")
                model = model.drop(columns=["zone_x", "nuts3"]).rename(columns={"zone_y": "zone"})
                model = model.groupby(["timestamp", "System", "zone"], as_index=False)["el_dem_mw"].sum()
            model.insert(0, "period", model.groupby("timestamp", sort=True).ngroup() + 1)
            model.to_csv(parts["model"], mode="a", header=country_number == 0, index=False)
            check = model.groupby("timestamp")["el_dem_mw"].sum().reindex(timestamps)
            max_error = max(max_error, float(np.max(np.abs(check.values - load.values))))
            wide_country = model.pivot_table(
                index=["period", "timestamp"], columns="zone", values="el_dem_mw", aggfunc="sum"
            )
            wide_total = wide_country if wide_total is None else wide_total.add(wide_country, fill_value=0)
        pd.concat(national_rows, ignore_index=True).to_csv(parts["national"], index=False)
        if wide_total is None:
            raise ValueError("No electricity-demand data generated")
        wide_total.reset_index().to_csv(parts["wide"], index=False)
        for key, path in final_paths.items():
            parts[key].replace(path)
        canonical = model_calendar(pd.read_csv(final_paths["model"])).rename(
            columns={"zone": "Zone", "el_dem_mw": "Power"}
        )
        canonical[["period", "Power", "System", "Zone"]].to_csv(args.out_dir / "electricity_demand.csv", index=False)
    finally:
        for path in parts.values():
            path.unlink(missing_ok=True)
    print(f"Wrote electricity demand for {len(args.countries)} countries; max reconciliation error={max_error:.9f} MW", flush=True)


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Generate cached ENTSO-E national and EIGL-weighted regional electricity demand.")
    ap.add_argument("--countries", type=parse_csv, required=True)
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--cache-dir", type=Path, required=True)
    ap.add_argument("--weights-dir", type=Path, default=DEFAULT_WEIGHTS)
    ap.add_argument("--zone-map", type=Path)
    ap.add_argument("--token", help="ENTSO-E API token; preferably set ENTSOE_API_TOKEN instead.")
    ap.add_argument("--refresh", action="store_true")
    return ap


def main() -> int:
    try:
        generate(parser().parse_args())
    except Exception as exc:
        print(f"ERROR: {exc}", flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
