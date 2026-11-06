#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build capacity-weighted hourly CF curves for PV/Wind from an aggregation schema,
using Open-Meteo historical ("archive") weather data, and (optionally) calibrate
the *national average* CF to IRENA (capacity+generation).

- Calibration is applied BEFORE aggregation:
    scale+clip per-site CF series first,
    then compute capacity-weighted unit curves.
  This avoids forcing all regions to end up with identical annual CFs.

INPUTS
- Schema CSV (e.g. genco_*_schema.csv), must contain at least:
    new_unit_name, technology, cap_mw_old, lat, lon, System
  (this script auto-detects common variants)

- Open-Meteo archive API hourly variables:
    PV proxy: shortwave_radiation (W/m2)
    Wind proxy: windspeed_100m if available else windspeed_10m

- IRENA xlsx (optional): IRENA_Statistics_Extract_2025H2.xlsx
  Uses sheet name "Country" and columns:
    ISO3 code
    Year
    Technology
    Electricity Generation (GWh)
    Electricity Installed Capacity (MW)

  Technology strings expected:
    - Solar photovoltaic
    - Onshore wind energy
    - Offshore wind energy

OUTPUTS
- <out-dir>/vre_cf_<COUNTRY>_<YEAR>.csv
    time + one column per aggregated unit (CF 0..1)
- <out-dir>/vre_cf_<COUNTRY>_<YEAR>_long.csv
    time, unit, cf
- <out-dir>/summary.csv
    group status + calibration alpha/targets

"""

import argparse
import datetime as dt
from email.utils import parsedate_to_datetime
import hashlib
import io
import os
import re
import sys
import time
from tempfile import NamedTemporaryFile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote,quote_plus

import numpy as np
import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from openmeteo_quota import OpenMeteoQuotaWaitError, reserve_request

# ----------------------------
# Helpers: schema detection
# ----------------------------
def detect_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    cols = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in cols:
            return cols[cand.lower()]
    return None


def norm(s: str) -> str:
    s = "" if s is None else str(s)
    s = s.strip()
    s = s.replace(" ", "_")
    s = s.replace("/", "_").replace("\\", "_")
    s = "".join(ch for ch in s if ch.isalnum() or ch in ("_", "-", "."))
    while "__" in s:
        s = s.replace("__", "_")
    return s


# ----------------------------
# Open-Meteo fetching
# ----------------------------
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
CUSTOMER_ARCHIVE_URL = "https://customer-archive-api.open-meteo.com/v1/archive"
NINJA_URL = "https://www.renewables.ninja/api/data"


class OpenMeteoRateLimitError(RuntimeError):
    """The provider's quota cannot be recovered within this bounded retry."""


class WeatherAcquisitionError(RuntimeError):
    """Expected resumable acquisition failure, reported without a CLI traceback."""


def _wait_weather(seconds, message):
    print(f'[Open-Meteo] {message}; waiting {seconds:g}s. Completed weather stays cached.',flush=True)
    remaining=float(seconds)
    elapsed=0.
    while remaining>0:
        step=min(30.,remaining)
        time.sleep(step)
        remaining-=step;elapsed+=step
        if remaining>0 and elapsed>=60:
            print(f'[Open-Meteo] Waiting for the request budget/reset: {remaining:g}s remaining.',flush=True)
            elapsed=0.


def _retry_after(headers, now=None):
    value=(headers or {}).get('Retry-After')
    if value is None:value=(headers or {}).get('retry-after')
    if value is None:return None
    try:
        seconds=float(value)
    except (ValueError,TypeError):
        try:
            reset=parsedate_to_datetime(value)
            if reset.tzinfo is None:reset=reset.replace(tzinfo=dt.timezone.utc)
            seconds=(reset-(now or dt.datetime.now(dt.timezone.utc))).total_seconds()
        except (ValueError,TypeError,OverflowError):return None
    return max(1.,seconds) if np.isfinite(seconds) else None


def _weather_reason(response, secret=''):
    try:
        payload=response.json()
        reason=str(payload.get('reason','')) if isinstance(payload,dict) else ''
    except (ValueError,TypeError):reason=''
    if secret:
        for token in {secret,quote(secret,safe=''),quote_plus(secret)}:
            reason=re.sub(re.escape(token),'[redacted]',reason,flags=re.IGNORECASE)
    return reason[:300]


def _quota_scope(reason):
    text=reason.lower()
    if 'month' in text:return 'monthly'
    if 'daily' in text or 'day' in text:return 'daily'
    if 'hour' in text:return 'hourly'
    if 'minut' in text:return 'minutely'
    return 'unspecified'


def _weather_frame(frame,date_from,date_to,timezone,want_pv,want_wind):
    frame=frame.copy()
    frame.index=pd.to_datetime(frame.index,utc=True,errors='raise')
    frame=frame.sort_index()
    if frame.empty or frame.index.hasnans or frame.index.duplicated().any():
        raise ValueError('Weather timestamps are empty, invalid or duplicated')
    if timezone.upper() in {'UTC','GMT'}:
        expected=pd.date_range(date_from,pd.Timestamp(date_to)+pd.Timedelta(days=1),freq='h',inclusive='left',tz='UTC')
        if not frame.index.equals(expected):raise ValueError('Weather does not cover every requested UTC hour')
    for column in frame:frame[column]=pd.to_numeric(frame[column],errors='coerce')
    for name in ('100m','10m'):
        if f'windspeed_{name}' not in frame and f'wind_speed_{name}' in frame:
            frame=frame.rename(columns={f'wind_speed_{name}':f'windspeed_{name}'})
    if want_pv and ('shortwave_radiation' not in frame or not np.isfinite(frame.shortwave_radiation).all()):
        raise ValueError('Solar radiation is missing or incomplete')
    if want_wind and not any(c in frame and np.isfinite(frame[c]).all() for c in ('windspeed_100m','windspeed_10m')):
        raise ValueError('Neither wind-speed height has a complete series')
    return frame


def _write_weather_cache(frame,path):
    temporary=None
    try:
        with NamedTemporaryFile(dir=path.parent,prefix='.weather_',suffix='.tmp',mode='w',encoding='utf-8',newline='',delete=False) as stream:
            temporary=Path(stream.name)
            frame.rename_axis('time').reset_index().to_csv(stream,index=False)
        temporary.replace(path)
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)


def fetch_openmeteo_hourly(
    lat: float,
    lon: float,
    date_from: str,
    date_to: str,
    timezone: str,
    want_pv: bool,
    want_wind: bool,
    sleep_s: float = 0.,
    max_retries: int = 8,
    cache_dir: Optional[Path] = None,
    max_rate_limit_wait: float = 3600.,
) -> pd.DataFrame:
    """
    Returns DataFrame indexed by UTC timestamps with numeric hourly series.
    Columns:
      - shortwave_radiation (if want_pv)
      - windspeed_100m / windspeed_10m (if want_wind)
    """
    hourly = []
    if want_pv:
        hourly.append("shortwave_radiation")
    if want_wind:
        hourly.extend(["windspeed_100m", "windspeed_10m"])

    params = {
        "latitude": float(lat),
        "longitude": float(lon),
        "start_date": date_from,
        "end_date": date_to,
        "hourly": ",".join(hourly),
        "timezone": timezone,
    }
    if want_wind:
        # The power-curve thresholds below are in metres per second. Including
        # the unit in the cache key also excludes older default-unit responses.
        params["wind_speed_unit"] = "ms"
    if not hourly:raise ValueError('Select solar radiation or wind speed')
    if max_retries<1 or not np.isfinite(sleep_s) or sleep_s<0 or not np.isfinite(max_rate_limit_wait) or max_rate_limit_wait<0:
        raise ValueError('Invalid weather retries, request spacing or rate-limit wait budget')
    days=(pd.Timestamp(date_to)-pd.Timestamp(date_from)).days+1
    if days<1:raise ValueError('Weather end date precedes start date')

    cache_path = None
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(repr(sorted(params.items())).encode("utf-8")).hexdigest()[:24]
        cache_path = cache_dir / f"openmeteo_{key}.csv"
        if cache_path.exists():
            try:
                cached=pd.read_csv(cache_path).set_index('time')
                return _weather_frame(cached,date_from,date_to,timezone,want_pv,want_wind)
            except (OSError,ValueError,KeyError):
                print(f'[Open-Meteo] Incomplete/unreadable weather cache for {lat:g},{lon:g}; requesting a complete replacement.',flush=True)

    # Credentials never enter the cache key, saved settings or command line.
    api_key=os.environ.get('OPEN_METEO_API_KEY','').strip() or os.environ.get('OPENMETEO_API_KEY','').strip()
    request_params=dict(params)
    url=ARCHIVE_URL
    if api_key:
        url=CUSTOMER_ARCHIVE_URL
        request_params['apikey']=api_key
    waited=0.
    last_err='No usable weather response'
    for k in range(max_retries):
        if not api_key:
            reserve_request(params, max_wait=max(0., max_rate_limit_wait-waited), wait=_wait_weather)
        try:
            r=requests.get(url,params=request_params,timeout=60)
        except requests.RequestException as error:
            # requests exception strings can include a customer API key URL.
            last_err=f'Open-Meteo connection failed ({type(error).__name__})'
        else:
            reason=_weather_reason(r,api_key)
            if r.status_code==429:
                scope=_quota_scope(reason)
                wait=_retry_after(r.headers)
                if wait is None and scope not in {'daily','monthly'}:
                    wait=3600. if scope=='hourly' else 65. if scope=='minutely' else min(60.*2**k,900.)
                if wait is None or waited+wait>max_rate_limit_wait or k+1==max_retries:
                    reset=f' Provider asks for at least {wait:g}s before retry.' if wait is not None else ''
                    raise OpenMeteoRateLimitError(
                        f'Open-Meteo {scope} quota exhausted (HTTP 429): {reason or "provider rate limit"}. '
                        f'Automatic retry stopped after {waited:g}s of quota waits.{reset} '
                        'Resume with the same weather cache after the provider quota resets, or configure an authorized '
                        'Historical Weather customer key with OPEN_METEO_API_KEY. Existing weather and curves are retained.'
                    ) from None
                _wait_weather(wait,f'{scope} quota (HTTP 429); retry {k+2}/{max_retries}')
                waited+=wait
                continue
            if 400<=r.status_code<500:
                raise RuntimeError(f'Open-Meteo HTTP {r.status_code}: {reason or "request rejected; check parameters or customer-key access"}') from None
            if r.status_code>=500:
                last_err=f'Open-Meteo HTTP {r.status_code}: {reason or "temporary provider failure"}'
            else:
                try:
                    j=r.json()
                    data=_weather_frame(pd.DataFrame(j['hourly']).set_index('time'),date_from,date_to,timezone,want_pv,want_wind)
                except (ValueError,KeyError,TypeError):
                    last_err='Open-Meteo returned an invalid or incomplete hourly response'
                else:
                    if cache_path is not None:_write_weather_cache(data,cache_path)
                    if sleep_s>0:_wait_weather(float(sleep_s),'request spacing')
                    return data
        if k+1<max_retries:
            _wait_weather(min(max(1.,sleep_s)*2**k,60.),f'{last_err}; retry {k+2}/{max_retries}')
    raise RuntimeError(f'Open-Meteo fetch failed after retries: {last_err}') from None


def fetch_renewables_ninja_hourly(
    lat: float, lon: float, date_from: str, date_to: str, technology: str,
    token: str, dataset: str, cache_dir: Optional[Path] = None,
) -> pd.Series:
    """Fetch a unit-capacity PV or wind series, with a persistent site cache."""
    if not token:
        raise ValueError("Set --ninja-token or RENEWABLES_NINJA_TOKEN.")
    model = "pv" if technology == "PHOT" else "wind"
    params = {
        "lat": lat, "lon": lon, "date_from": date_from, "date_to": date_to,
        "dataset": dataset, "capacity": 1, "format": "csv", "header": "false",
        "local_time": "false",
    }
    if model == "pv":
        params.update({"system_loss": 0.1, "tracking": 0, "tilt": 35, "azim": 180})
    else:
        params.update({"height": 100, "turbine": "Vestas V80 2000"})
    cache_path = None
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(repr(sorted(params.items())).encode("utf-8")).hexdigest()[:24]
        cache_path = cache_dir / f"ninja_{key}.csv"
        if cache_path.exists():
            frame = pd.read_csv(cache_path)
            return pd.Series(frame["cf"].to_numpy(float), index=pd.to_datetime(frame["time"], utc=True))
    response = requests.get(
        f"{NINJA_URL}/{model}", params=params,
        headers={"Authorization": f"Token {token}"}, timeout=180,
    )
    response.raise_for_status()
    frame = pd.read_csv(io.StringIO(response.text))
    time_col = detect_col(frame, ["time", "datetime", "date"])
    value_col = detect_col(frame, ["electricity", "power", "generation"])
    if time_col is None or value_col is None:
        raise ValueError(f"Unexpected Renewables.ninja columns: {list(frame.columns)}")
    curve = pd.Series(
        pd.to_numeric(frame[value_col], errors="coerce").fillna(0.0).clip(0.0, 1.0).to_numpy(),
        index=pd.to_datetime(frame[time_col], utc=True),
    )
    if cache_path is not None:
        pd.DataFrame({"time": curve.index, "cf": curve.to_numpy()}).to_csv(cache_path, index=False)
    return curve


# ----------------------------
# Convert weather -> CF
# ----------------------------
def pv_cf_from_shortwave(shortwave_wm2: pd.Series, pv_ghi_ref: float) -> pd.Series:
    """
    Simple proxy: CF ~ GHI / pv_ghi_ref, clipped 0..1.
    """
    s = pd.to_numeric(shortwave_wm2, errors="coerce").fillna(0.0)
    s = s.clip(lower=0.0)
    return (s / float(pv_ghi_ref)).clip(0.0, 1.0)


def wind_cf_from_speed(
    windspeed: pd.Series,
    cut_in: float,
    rated: float,
    cut_out: float,
) -> pd.Series:
    """
    Simple piecewise power curve:
      v < cut_in => 0
      cut_in..rated => cubic ramp 0..1
      rated..cut_out => 1
      v >= cut_out => 0
    """
    v = pd.to_numeric(windspeed, errors="coerce")
    cf = pd.Series(0.0, index=v.index, dtype=float)

    m1 = (v >= cut_in) & (v < rated)
    if m1.any():
        x = (v[m1] - cut_in) / max(1e-9, (rated - cut_in))
        cf.loc[m1] = (x ** 3).clip(0.0, 1.0)

    m2 = (v >= rated) & (v < cut_out)
    cf.loc[m2] = 1.0

    m3 = v >= cut_out
    cf.loc[m3] = 0.0

    return cf.clip(0.0, 1.0)


# ----------------------------
# Calibration to IRENA (pre-aggregation)
# ----------------------------
ISO2_TO_ISO3 = {
    "HR": "HRV", "IT": "ITA", "SI": "SVN", "AT": "AUT", "DE": "DEU", "FR": "FRA",
    "ES": "ESP", "PT": "PRT", "NL": "NLD", "BE": "BEL", "DK": "DNK", "SE": "SWE",
    "FI": "FIN", "PL": "POL", "CZ": "CZE", "SK": "SVK", "HU": "HUN", "RO": "ROU",
    "BG": "BGR", "GR": "GRC", "IE": "IRL", "LU": "LUX", "MT": "MLT", "CY": "CYP",
    "EE": "EST", "LV": "LVA", "LT": "LTU", "NO": "NOR", "CH": "CHE", "UK": "GBR",
}


def read_irena_targets_from_xlsx(xlsx_path: str, iso2: str, year: int) -> Dict[str, float]:
    """
    Returns CF targets for keys:
      - "PHOT": Solar photovoltaic
      - "WTON": Onshore wind energy
      - "WTOF": Offshore wind energy
    Reads from sheet "Country".
    """
    iso2 = iso2.upper()
    iso3 = ISO2_TO_ISO3.get(iso2)
    if not iso3:
        raise ValueError(f"Unknown ISO2->ISO3 mapping for '{iso2}'. Add it to ISO2_TO_ISO3.")

    df = pd.read_excel(xlsx_path, sheet_name="Country")

    col_iso3 = detect_col(df, ["ISO3 code", "ISO3", "iso3 code", "iso3"])
    col_year = detect_col(df, ["Year", "year"])
    col_tech = detect_col(df, ["Technology", "technology"])
    col_gen = detect_col(df, ["Electricity Generation (GWh)", "Electricity Generation", "generation (gwh)", "generation_gwh"])
    col_cap = detect_col(df, ["Electricity Installed Capacity (MW)", "Electricity Installed Capacity", "installed capacity (mw)", "capacity_mw"])

    missing = [name for name, col in [
        ("ISO3 code", col_iso3),
        ("Year", col_year),
        ("Technology", col_tech),
        ("Electricity Generation (GWh)", col_gen),
        ("Electricity Installed Capacity (MW)", col_cap),
    ] if col is None]
    if missing:
        raise ValueError(f"IRENA xlsx missing columns: {missing}. Found columns={list(df.columns)}")

    df = df.copy()
    df[col_iso3] = df[col_iso3].astype(str).str.strip().str.upper()
    df[col_year] = pd.to_numeric(df[col_year], errors="coerce")
    df[col_tech] = df[col_tech].astype(str).str.strip()
    df[col_gen] = pd.to_numeric(df[col_gen], errors="coerce")
    df[col_cap] = pd.to_numeric(df[col_cap], errors="coerce")

    df = df[(df[col_iso3] == iso3) & (df[col_year] == float(year))].copy()

    tech_map = {
        "PHOT": "Solar photovoltaic",
        "WTON": "Onshore wind energy",
        "WTOF": "Offshore wind energy",
    }

    targets: Dict[str, float] = {}
    for key, tech_str in tech_map.items():
        sub = df[df[col_tech] == tech_str]
        if sub.empty:
            continue
        gen_gwh = float(sub[col_gen].sum(skipna=True))
        cap_mw = float(sub[col_cap].sum(skipna=True))
        if cap_mw > 0:
            cf = gen_gwh / (cap_mw * 8760.0 / 1000.0)
            targets[key] = float(cf)
    return targets


def national_mean_after_clip(alpha: float, items: List[Dict]) -> float:
    """
    mean_t( sum_i cap_i * clip(alpha*cf_i(t)) / sum_i cap_i )
    items: list of {"cap": float, "cf": Series}
    """
    if not items:
        return 0.0

    idx = None
    for it in items:
        s = it["cf"]
        idx = s.index if idx is None else idx.union(s.index)

    num = pd.Series(0.0, index=idx)
    den = pd.Series(0.0, index=idx)

    for it in items:
        cap = float(it["cap"])
        s = it["cf"].reindex(idx)
        m = s.notna()
        clipped = np.clip(alpha * s[m].astype(float), 0.0, 1.0)
        num.loc[m] += cap * clipped
        den.loc[m] += cap

    nat = (num / den).fillna(0.0)
    return float(nat.mean())


def find_alpha_sites_for_target(items: List[Dict], target_mean: float) -> float:
    """
    Bisection on alpha for national_mean_after_clip(alpha) == target_mean.
    """
    target_mean = float(target_mean)
    if not np.isfinite(target_mean) or target_mean <= 0:
        return 0.0
    if not items:
        return 1.0

    # quick all-zero check
    any_nonzero = False
    for it in items:
        s = it["cf"]
        if s is not None and np.nanmax(s.to_numpy(dtype=float)) > 0:
            any_nonzero = True
            break
    if not any_nonzero:
        return 0.0

    lo, hi = 0.0, 10.0
    for _ in range(40):
        m = national_mean_after_clip(hi, items)
        if m >= target_mean or m >= 0.999999:
            break
        hi *= 2.0
        if hi > 1e6:
            break

    for _ in range(60):
        mid = 0.5 * (lo + hi)
        m = national_mean_after_clip(mid, items)
        if m < target_mean:
            lo = mid
        else:
            hi = mid
    return float(0.5 * (lo + hi))


# ----------------------------
# Main
# ----------------------------
def main():
    ap = argparse.ArgumentParser()

    ap.add_argument("--schema", required=True, help="Schema CSV (genco_*_schema.csv)")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--country", default="HR", help="ISO2 (matches schema System). Default HR")
    ap.add_argument("--date-from", required=True, help="YYYY-MM-DD")
    ap.add_argument("--date-to", required=True, help="YYYY-MM-DD")
    ap.add_argument("--timezone", default="UTC", help="Open-Meteo timezone (default UTC)")
    ap.add_argument("--unit-column", default=None, help="Schema unit column (new_unit_name or old_unit_name)")
    ap.add_argument("--output-suffix", default="", help="Suffix added before .csv, e.g. _individual")
    ap.add_argument("--cache-dir", default=None, help="Persistent weather-response cache")
    ap.add_argument(
        "--weather-source", choices=("openmeteo", "renewables-ninja"),
        default="openmeteo",
    )
    ap.add_argument("--ninja-token", default=os.environ.get("RENEWABLES_NINJA_TOKEN"))
    ap.add_argument("--ninja-dataset", default="merra2")

    # IRENA calibration
    ap.add_argument("--irena-xlsx", default=None, help="IRENA_Statistics_Extract_2025H2.xlsx")
    ap.add_argument("--irena-year", type=int, default=None, help="Year to use (default from --date-from)")
    ap.add_argument("--calibrate", action="store_true", help="Calibrate national annual CF to IRENA")

    # PV + Wind conversion params
    ap.add_argument("--pv-ghi-ref", type=float, default=1000.0, help="W/m2 giving CF=1 for PV proxy")
    ap.add_argument("--wind-cut-in", type=float, default=3.0)
    ap.add_argument("--wind-rated", type=float, default=12.0)
    ap.add_argument("--wind-cut-out", type=float, default=25.0)

    # throttling
    ap.add_argument("--sleep-s", type=float, default=0., help="Optional delay after a new download; default uses counted request budgets only")
    ap.add_argument("--max-retries", type=int, default=8)
    ap.add_argument('--openmeteo-max-wait',type=float,default=3600.,help='Maximum seconds spent honoring HTTP 429 delays for a site; daily/monthly limits without a reset delay stop resumably')
    ap.add_argument("--verbose", action="store_true")

    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    weather_cache=Path(args.cache_dir) if args.cache_dir else out_dir/'weather_cache'
    summary_path = out_dir / f"summary_{args.country.upper()}{args.output_suffix}.csv"

    # -------- read schema
    df = pd.read_csv(args.schema)

    # detect columns from schema
    if args.unit_column:
        if args.unit_column not in df.columns:
            raise ValueError(f"--unit-column '{args.unit_column}' not found in schema")
        col_unit = args.unit_column
    else:
        col_unit = detect_col(df, ["new_unit_name", "unit_name", "name"])
    col_tech = detect_col(df, ["technology", "tech"])
    col_cap = detect_col(df, ["cap_mw_old", "cap_mw", "capacity_mw"])
    col_lat = detect_col(df, ["lat", "latitude"])
    col_lon = detect_col(df, ["lon", "longitude"])
    col_country = detect_col(df, ["System", "country", "iso2", "Country"])

    needed = [("unit", col_unit), ("tech", col_tech), ("cap", col_cap), ("lat", col_lat), ("lon", col_lon), ("country", col_country)]
    missing = [n for n, c in needed if c is None]
    if missing:
        raise ValueError(f"Schema missing required columns: {missing}. Columns={list(df.columns)}")

    if args.verbose:
        print(f"[schema] detected cols: unit={col_unit} tech={col_tech} cap={col_cap} lat={col_lat} lon={col_lon} country={col_country}")

    df = df.copy()
    df[col_country] = df[col_country].astype(str).str.strip().str.upper()
    df = df[df[col_country] == args.country.upper()].copy()
    if df.empty:
        raise SystemExit(f"No rows for country={args.country} found in schema.")

    df[col_tech] = df[col_tech].astype(str).str.strip().str.upper()

    if args.verbose:
        vc = dict(df[col_tech].value_counts().head(30))
        print(f"[schema] tech values (top 30): {vc}")
        print("[schema] allowed techs:", ["PHOT", "WTOF", "WTON"])

    vre = df[df[col_tech].isin(["PHOT", "WTON", "WTOF"])].copy()

    vre["cap_mw"] = pd.to_numeric(vre[col_cap], errors="coerce")
    vre["lat"] = pd.to_numeric(vre[col_lat], errors="coerce")
    vre["lon"] = pd.to_numeric(vre[col_lon], errors="coerce")
    vre["unit"] = vre[col_unit].astype(str)
    vre["tech"] = vre[col_tech].astype(str)
    vre = vre[vre["cap_mw"].notna() & vre["lat"].notna() & vre["lon"].notna() & (vre["cap_mw"] > 0)].copy()

    if args.verbose:
        dropped = int((pd.to_numeric(df[col_cap], errors="coerce").isna() |
                       pd.to_numeric(df[col_lat], errors="coerce").isna() |
                       pd.to_numeric(df[col_lon], errors="coerce").isna()).sum())
        print(f"[schema] kept VRE rows={len(vre)}, dropped for missing CAP/LAT/LON={dropped}")

    if vre.empty:
        raise SystemExit("No valid VRE rows with cap+lat+lon > 0.")

    year = int(str(args.date_from)[:4])
    irena_year = args.irena_year if args.irena_year is not None else year

    # group by aggregated unit + tech (each group holds multiple sites)
    groups = list(vre.groupby(["unit", "tech"], sort=True))
    query_count=len(vre.assign(weather_kind=np.where(vre.tech.eq('PHOT'),'solar','wind'))[['lat','lon','weather_kind']].drop_duplicates())
    print(f'[{args.country}] Weather sites: {len(vre)} records, {query_count} distinct coordinate/technology queries before cache reuse.',flush=True)

    if args.verbose:
        print(f"\n[{args.country}] processing {args.date_from} .. {args.date_to} (year {year})")

    # Store per-site curves for calibration BEFORE aggregation
    site_curves_by_tech: Dict[str, List[Dict]] = {"PHOT": [], "WTON": [], "WTOF": []}
    summary_rows = []

    # ---- fetch per-site curves for each unit-tech group
    for group_number, ((unit, tech), g) in enumerate(groups, start=1):
        unit_str = str(unit)
        tech_str = str(tech).upper()
        print(f"[{args.country}] Wind/solar profiles {group_number}/{len(groups)}: {unit_str}", flush=True)
        cap_total = float(g["cap_mw"].sum())
        errs = []
        rate_limited = False
        ok_sites = 0

        want_pv = tech_str == "PHOT"
        want_wind = tech_str in ("WTON", "WTOF")

        for row in g.itertuples(index=False):
            # access via known processed columns
            lat = float(getattr(row, "lat"))
            lon = float(getattr(row, "lon"))
            cap = float(getattr(row, "cap_mw"))

            try:
                if args.weather_source == "renewables-ninja":
                    cf = fetch_renewables_ninja_hourly(
                        lat=lat, lon=lon, date_from=args.date_from,
                        date_to=args.date_to, technology=tech_str,
                        token=args.ninja_token, dataset=args.ninja_dataset,
                        cache_dir=weather_cache,
                    )
                else:
                    met = fetch_openmeteo_hourly(
                        lat=lat,
                        lon=lon,
                        date_from=args.date_from,
                        date_to=args.date_to,
                        timezone=args.timezone,
                        want_pv=want_pv,
                        want_wind=want_wind,
                        sleep_s=args.sleep_s,
                        max_retries=args.max_retries,
                        cache_dir=weather_cache,
                        max_rate_limit_wait=args.openmeteo_max_wait,
                    )

                    if want_pv:
                        if "shortwave_radiation" not in met.columns or not met["shortwave_radiation"].notna().any():
                            raise ValueError("Open-Meteo missing shortwave_radiation")
                        cf = pv_cf_from_shortwave(met["shortwave_radiation"], pv_ghi_ref=args.pv_ghi_ref)
                    else:
                        ws = None
                        if "windspeed_100m" in met.columns and met["windspeed_100m"].notna().all():
                            ws = met["windspeed_100m"]
                        elif "windspeed_10m" in met.columns and met["windspeed_10m"].notna().all():
                            ws = met["windspeed_10m"]
                        else:
                            raise ValueError("Open-Meteo missing windspeed_100m and windspeed_10m")

                        cf = wind_cf_from_speed(
                            ws,
                            cut_in=args.wind_cut_in,
                            rated=args.wind_rated,
                            cut_out=args.wind_cut_out,
                        )

                site_curves_by_tech[tech_str].append(
                    {"unit": unit_str, "cap": cap, "cf": cf}
                )
                ok_sites += 1

            except (OpenMeteoRateLimitError, OpenMeteoQuotaWaitError) as e:
                rate_limited=True
                errs.append(str(e))
                break
            except Exception as e:
                errs.append(str(e))
                break

        if ok_sites == 0:
            summary_rows.append({
                "country": args.country,
                "year": year,
                "unit": unit_str,
                "tech": tech_str,
                "status": "ALL_SITES_FAILED",
                "n_sites": int(len(g)),
                "ok_sites": 0,
                "cap_total_mw": cap_total,
                "errors": " | ".join(errs)[:2000],
            })
        else:
            summary_rows.append({
                "country": args.country,
                "year": year,
                "unit": unit_str,
                "tech": tech_str,
                "status": "OK",
                "n_sites": int(len(g)),
                "ok_sites": int(ok_sites),
                "cap_total_mw": cap_total,
                "errors": "",
            })

        if errs:
            # Retain successful site caches for retry, but never publish a
            # partial fleet or report success when the weather service failed.
            summary_rows[-1]["status"] = 'RATE_LIMITED' if rate_limited else "ALL_SITES_FAILED" if ok_sites == 0 else "SOME_SITES_FAILED"
            summary_rows[-1]["errors"] = " | ".join(errs)[:2000]
            pd.DataFrame(summary_rows).to_csv(summary_path, index=False)
            raise WeatherAcquisitionError(
                f"Wind/solar weather acquisition failed for {unit_str}: {errs[0]}. "
                f"See {summary_path}. Existing curves were retained; retry reuses successful weather downloads."
            )

    # If no sites worked at all
    total_ok = sum(1 for r in summary_rows if r.get("status") == "OK")
    if total_ok == 0:
        summ = pd.DataFrame(summary_rows)
        summ.to_csv(summary_path, index=False)
        if args.verbose:
            print(f"[{args.country} {year}] no curves produced (all sites failed).")
            print(f"[write] {summary_path}")
        print("Done.")
        return

    # ---- calibration (PRE-aggregation): find alpha per tech so national mean matches IRENA
    tech_scale_alpha = {"PHOT": 1.0, "WTON": 1.0, "WTOF": 1.0}
    irena_targets: Dict[str, float] = {}

    if args.calibrate:
        if not args.irena_xlsx:
            raise ValueError("--calibrate requires --irena-xlsx")
        irena_targets = read_irena_targets_from_xlsx(args.irena_xlsx, args.country, irena_year)

        if args.verbose:
            print("\n[calibrate] IRENA CF targets:")
            if not irena_targets:
                print("  (none found for this country/year)")
            for k, v in irena_targets.items():
                print(f"  {k}: {v:.4f}")

        for tech, target in irena_targets.items():
            items = site_curves_by_tech.get(tech, [])
            if not items:
                continue
            alpha = find_alpha_sites_for_target(items, target_mean=float(target))
            tech_scale_alpha[tech] = float(alpha)
            if args.verbose:
                after = national_mean_after_clip(alpha, items)
                print(f"[calibrate] {tech}: target={float(target):.4f} alpha={alpha:.4f} after_mean={after:.4f}")

        # apply scaling per site (clip)
        for tech, items in site_curves_by_tech.items():
            alpha = float(tech_scale_alpha.get(tech, 1.0))
            if not np.isfinite(alpha):
                alpha = 1.0
            for it in items:
                it["cf"] = (it["cf"] * alpha).clip(0.0, 1.0)

    # ---- build aggregated unit curves from (possibly calibrated) site curves
    group_curves: Dict[Tuple[str, str], pd.Series] = {}

    for (unit, tech), g in groups:
        unit_str = str(unit)
        tech_str = str(tech).upper()
        items = [it for it in site_curves_by_tech.get(tech_str, []) if it["unit"] == unit_str]
        if not items:
            continue

        # union index
        idx = None
        for it in items:
            s = it["cf"]
            idx = s.index if idx is None else idx.union(s.index)

        wsum = pd.Series(0.0, index=idx)
        wtot = pd.Series(0.0, index=idx)

        for it in items:
            cap = float(it["cap"])
            s = it["cf"].reindex(idx)
            m = s.notna()
            wsum.loc[m] += cap * s.loc[m].astype(float)
            wtot.loc[m] += cap

        agg = (wsum / wtot).fillna(0.0).clip(0.0, 1.0)
        group_curves[(unit_str, tech_str)] = agg

    if not group_curves:
        summ = pd.DataFrame(summary_rows)
        if args.calibrate:
            summ["irena_year"] = irena_year
            summ["irena_cf_target"] = summ["tech"].map(irena_targets).astype(float)
            summ["calib_alpha"] = summ["tech"].map(tech_scale_alpha).astype(float)
        summ.to_csv(summary_path, index=False)
        if args.verbose:
            print(f"[{args.country} {year}] no aggregated curves produced (no successful sites).")
        print("Done.")
        return

    # ---- write wide output
    union_idx = None
    for ser in group_curves.values():
        union_idx = ser.index if union_idx is None else union_idx.union(ser.index)

    wide = pd.DataFrame({"time": pd.to_datetime(union_idx, utc=True)})
    wide = wide.sort_values("time").reset_index(drop=True)

    colnames_used = set()
    for (unit, tech), ser in sorted(group_curves.items()):
        base_name = str(unit)
        col_name = base_name
        if col_name in colnames_used:
            col_name = f"{base_name}_{tech}"
        colnames_used.add(col_name)

        s = ser.reindex(union_idx).fillna(0.0).astype(float).clip(0.0, 1.0)
        wide[col_name] = s.to_numpy()

    out_wide = out_dir / f"vre_cf_{args.country.upper()}_{year}{args.output_suffix}.csv"
    wide.to_csv(out_wide, index=False)

    long = wide.melt(id_vars=["time"], var_name="unit", value_name="cf")
    out_long = out_dir / f"vre_cf_{args.country.upper()}_{year}{args.output_suffix}_long.csv"
    long.to_csv(out_long, index=False)

    # ---- summary (append calibration info)
    summ = pd.DataFrame(summary_rows)
    if args.calibrate:
        summ["irena_year"] = irena_year
        summ["irena_cf_target"] = summ["tech"].map(irena_targets).astype(float)
        summ["calib_alpha"] = summ["tech"].map(tech_scale_alpha).astype(float)

    out_summ = summary_path
    summ.to_csv(out_summ, index=False)

    if args.verbose:
        ok = int((summ["status"] == "OK").sum())
        fail = int((summ["status"] != "OK").sum())
        print(f"[{args.country} {year}] groups OK={ok}, failed={fail}")
        print(f"[write] {out_wide}")
        print(f"[write] {out_long}")
        print(f"[write] {out_summ}")

    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except (WeatherAcquisitionError,OpenMeteoRateLimitError) as error:
        print('ERROR: '+str(error),file=sys.stderr)
        raise SystemExit(2) from None
