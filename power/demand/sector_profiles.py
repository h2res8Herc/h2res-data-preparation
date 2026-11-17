"""Source-backed regional electricity priors and two-margin reconciliation.

No learned model and no new weather requests. All final MW are reconciled to
ENTSO-E, with the packaged JRC annual regional shares as hard constraints.
"""
from __future__ import annotations

import hashlib
import json
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
LIBRARY = Path(__file__).resolve().parent / "profile_library"
METHODS = ("national-scaled", "sector-weighted")
SECTORS = ("households", "industry", "services", "agriculture", "tourism", "other")
# Disjoint A10 partition: never add C to B-E or G-J to G-I/J.
SERVICES = ("G-I", "J", "K", "L", "M_N", "O-Q", "R-U")
INDUSTRIAL_PROFILES = ("WZ10", "WZ11", "WZ12", "WZ17", "WZ21", "WZ22", "WZ26", "WZ28", "WZ29", "WZ32")
SERVICE_PROFILES = {
    "G-I": ("WZ46", "WZ47", "WZ52"), "J": ("WZ62", "WZ63"),
    "K": ("WZ64-71",), "L": ("WZ64-71",),
    "M_N": ("WZ64-71", "WZ72", "WZ77", "WZ82"),
    "O-Q": ("WZ84", "WZ85", "WZ86", "WZ87", "WZ88"),
    "R-U": ("WZ90", "WZ91", "WZ93", "WZ94"),
}
TIMEZONES = dict(AT="Vienna", BE="Brussels", BG="Sofia", CH="Zurich", CZ="Prague", DE="Berlin",
                 DK="Copenhagen", EE="Tallinn", ES="Madrid", FI="Helsinki", FR="Paris", GR="Athens",
                 EL="Athens", HR="Zagreb", HU="Budapest", IE="Dublin", IT="Rome", LT="Vilnius",
                 LU="Luxembourg", LV="Riga", NL="Amsterdam", NO="Oslo", PL="Warsaw", PT="Lisbon",
                 RO="Bucharest", RS="Belgrade", SE="Stockholm", SI="Ljubljana", SK="Bratislava",
                 GB="London", UK="London", CY="Nicosia", MT="Malta", BA="Sarajevo", ME="Podgorica",
                 MK="Skopje", AL="Tirane")


def balance(prior, hourly, annual, *, rtol=1e-12, max_iterations=10000):
    """KL/IPF projection, hours x components, preserving both margins.

    Zero annual components and zero national-load hours stay zero. A positive
    target without positive prior support is an error, not an invented load.
    """
    matrix = np.asarray(prior, dtype=float).copy()
    hourly = np.asarray(hourly, dtype=float)
    annual = np.asarray(annual, dtype=float)
    if matrix.shape != (hourly.size, annual.size):
        raise ValueError("Electricity balancing dimensions differ")
    for name, values in (("prior", matrix), ("hourly targets", hourly), ("annual targets", annual)):
        if not np.isfinite(values).all() or (values < 0).any():
            raise ValueError(f"Non-finite or negative electricity {name}")
    total = float(hourly.sum())
    if not np.isclose(total, annual.sum(), rtol=1e-12, atol=1e-8):
        raise ValueError("Incompatible hourly and annual electricity totals")
    rows, cols = hourly > 0, annual > 0
    matrix[~rows, :] = 0
    matrix[:, ~cols] = 0
    if total == 0:
        return matrix, dict(iterations=0, max_hourly_error_MW=0., max_annual_error_MWh=0.)
    if (matrix[rows].sum(axis=1) <= 0).any() or (matrix[:, cols].sum(axis=0) <= 0).any():
        raise ValueError("Electricity targets lack positive profile support")
    for iteration in range(1, max_iterations + 1):
        row_sum = matrix.sum(axis=1)
        matrix *= np.divide(hourly, row_sum, out=np.zeros_like(hourly), where=row_sum > 0)[:, None]
        col_sum = matrix.sum(axis=0)
        matrix *= np.divide(annual, col_sum, out=np.zeros_like(annual), where=col_sum > 0)[None, :]
        row_error = np.max(np.abs(matrix.sum(axis=1) - hourly))
        col_error = np.max(np.abs(matrix.sum(axis=0) - annual))
        if row_error <= rtol * hourly.max() and col_error <= rtol * annual.max():
            return matrix, dict(iterations=iteration, max_hourly_error_MW=float(row_error),
                                max_annual_error_MWh=float(col_error))
    raise ValueError(f"Electricity reconciliation did not converge after {max_iterations} iterations")


def decode_jsonstat(data):
    """Decode sparse or dense JSON-stat without treating absent cells as zero."""
    ids, sizes = data["id"], data["size"]
    categories = []
    for dimension in ids:
        index = data["dimension"][dimension]["category"]["index"]
        categories.append([k for k, _ in sorted(index.items(), key=lambda item: item[1])]
                          if isinstance(index, dict) else index)
    values = data.get("value", {})
    items = values.items() if isinstance(values, dict) else enumerate(values)
    records = []
    for flat, value in items:
        if value is None:
            continue
        coordinates = np.unravel_index(int(flat), tuple(sizes))
        record = {key: categories[i][coordinate] for i, (key, coordinate) in enumerate(zip(ids, coordinates))}
        record["value"] = float(value)
        records.append(record)
    return pd.DataFrame(records, columns=ids + ["value"])


class SourceCache:
    def __init__(self, directory, refresh=False):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.refresh = refresh
        self.sources, self.warnings = [], []

    def get(self, name, url):
        path = self.directory / (name + "_" + hashlib.sha256(url.encode()).hexdigest()[:12] + ".json")
        if self.refresh or not path.exists():
            print(f"Electricity composition: downloading {name}", flush=True)
            attempt, rate_limits = 0, 0
            while True:
                try:
                    request = urllib.request.Request(url, headers={"User-Agent": "H2RES-data-preparation/sector-profiles-1"})
                    with urllib.request.urlopen(request, timeout=90) as response:
                        payload = response.read()
                    data = json.loads(payload)
                    if isinstance(data, dict) and data.get("error"):
                        raise ValueError(f"{name}: {data['error']}")
                    temporary = path.with_suffix(".json.part")
                    temporary.write_bytes(payload)
                    temporary.replace(path)
                    break
                except (urllib.error.URLError, TimeoutError) as exc:
                    if isinstance(exc, urllib.error.HTTPError) and exc.code == 429:
                        rate_limits += 1
                        retry = exc.headers.get("Retry-After", "") if exc.headers else ""
                        try:
                            wait = float(retry)
                        except ValueError:
                            try:
                                wait = (parsedate_to_datetime(retry) - datetime.now(timezone.utc)).total_seconds()
                            except (TypeError, ValueError, OverflowError):
                                wait = min(900., 60. * 2 ** min(rate_limits - 1, 4))
                        if not np.isfinite(wait) or wait <= 0:
                            wait = 60.
                        print(f"Electricity composition: {name} rate limited; retrying after {wait:.0f}s. Completed sources stay cached; Stop cancels the run.", flush=True)
                        while wait > 0:
                            pause = min(wait, 60.)
                            time.sleep(pause)
                            wait -= pause
                        continue
                    attempt += 1
                    if attempt >= 3:
                        raise RuntimeError(f"Cannot acquire {name}; cached successful sources are retained: {exc}") from exc
                    time.sleep(2 ** (attempt - 1))
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise ValueError(f"Invalid electricity source cache {path}; use Refresh downloaded source data") from exc
        self.sources.append(dict(name=name, url=url, file=path.name,
                                 sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                 updated=data.get("updated") if isinstance(data, dict) else None))
        return data

    def table(self, dataset, year, **filters):
        url = API + dataset + "?" + urllib.parse.urlencode(dict(lang="EN", time=str(year), **filters))
        return decode_jsonstat(self.get(f"{dataset}_{year}", url))

    def optional_table(self, dataset, year, **filters):
        try:
            return self.table(dataset, year, **filters)
        except (RuntimeError, ValueError, KeyError) as exc:
            self.warnings.append(f"{dataset} {year}: {exc}")
            return pd.DataFrame()


def _geo(country):
    return {"GR": "EL", "GB": "UK"}.get(country, country)


def _lookup(frame, **filters):
    if frame.empty:
        return None
    for key, value in filters.items():
        if key not in frame:
            return None
        frame = frame.loc[frame[key].eq(value)]
    if len(frame) != 1:
        return None
    value = float(frame.iloc[0]["value"])
    return value if np.isfinite(value) and value >= 0 else None


def _regional(frame, region, country, weights, fallbacks, label, **filters):
    """Recorded parent fallback apportioned by JRC shares, never equal zeros."""
    region = _geo(country) + region[2:]
    shares = pd.Series(weights.to_numpy(), index=[_geo(country) + z[2:] for z in weights.index])
    for geo in (region, region[:4], region[:3], _geo(country)):
        value = _lookup(frame, geo=geo, **filters)
        if value is not None:
            if geo != region:
                siblings = shares.loc[shares.index.str.startswith(geo)]
                value *= shares[region] / siblings.sum()
                fallbacks.append(dict(region=region, feature=label, basis=f"parent {geo} apportioned by JRC shares"))
            return value
    fallbacks.append(dict(region=region, feature=label, basis="unavailable"))
    return np.nan


def _spatial_proxy(employment, gva, sector_codes, regions, country, weights, fallbacks):
    candidates = []
    for label, table in (("employment", employment), ("GVA", gva)):
        values = []
        for region in regions:
            parts = [_regional(table, region, country, weights, fallbacks, f"{label}:{code}", nace_r2=code)
                     for code in sector_codes]
            values.append(sum(parts) if np.isfinite(parts).all() else np.nan)
        values = np.asarray(values)
        available = np.isfinite(values)
        if available.any() and values[available].sum() > 0:
            # Missing regions retain positive prior support at JRC-weighted
            # average intensity. A measured zero remains a measured zero.
            scale = values[available].sum() / weights.to_numpy()[available].sum()
            values[~available] = weights.to_numpy()[~available] * scale
            fallbacks.extend(dict(region=region, feature=f"{label}:{','.join(sector_codes)}",
                                  basis="JRC-share average intensity from covered regions")
                             for region, covered in zip(regions, available) if not covered)
            candidates.append(values / values.sum())
    if not candidates:
        raise ValueError(f"No regional or parent economic coverage for {country}, sectors {sector_codes}")
    return np.mean(candidates, axis=0)


def composition(country, year, weights, cache, tourism_share):
    """Regional sector budgets; final energy shares are proxies for grid mix."""
    if not 0 <= tourism_share < 1:
        raise ValueError("Tourism share must be at least 0 and less than 1")
    regions = list(weights.index)
    fallbacks = []
    employment = cache.optional_table("nama_10r_3empers", year, unit="THS", wstatus="EMP")
    gva = cache.optional_table("nama_10r_3gva", year, unit="CP_MEUR")
    if employment.empty and gva.empty:
        raise ValueError("Sector-weighted electricity needs Eurostat regional employment or GVA; select national-scaled to use the existing method")
    population = cache.optional_table("demo_r_pjanaggr3", year, unit="NR", sex="T", age="TOTAL")
    energy = cache.table("nrg_bal_c", year, unit="GWH", siec="E7000", geo=_geo(country))
    balances = {}
    for key in ("FC_E", "FC_IND_E", "FC_OTH_CP_E", "FC_OTH_HH_E", "FC_OTH_AF_E"):
        value = _lookup(energy, nrg_bal=key)
        if value is None:
            raise ValueError(f"Eurostat electricity balance {key} missing for {country}/{year}; choose another demand year or national-scaled")
        balances[key] = value
    agriculture = balances["FC_OTH_AF_E"] + (_lookup(energy, nrg_bal="FC_OTH_FISH_E") or 0.)
    known = balances["FC_IND_E"] + balances["FC_OTH_CP_E"] + balances["FC_OTH_HH_E"] + agriculture
    if balances["FC_E"] <= 0 or known > balances["FC_E"] * (1 + 1e-4):
        raise ValueError(f"Inconsistent Eurostat national electricity sector balance for {country}/{year}")
    national = np.array([balances["FC_OTH_HH_E"], balances["FC_IND_E"],
                         balances["FC_OTH_CP_E"] * (1 - tourism_share), agriculture,
                         balances["FC_OTH_CP_E"] * tourism_share, max(0., balances["FC_E"] - known)])
    national /= national.sum()
    pop = np.array([_regional(population, r, country, weights, fallbacks, "population") for r in regions])
    if not np.isfinite(pop).all() or pop.sum() <= 0:
        valid = np.isfinite(pop)
        scale = pop[valid].sum() / weights.to_numpy()[valid].sum() if valid.any() and pop[valid].sum() > 0 else 1.
        pop[~valid] = weights.to_numpy()[~valid] * scale
        fallbacks.extend(dict(region=region, feature="population",
                              basis="household JRC-share proxy at covered-region average intensity; not an observed population")
                         for region, covered in zip(regions, valid) if not covered)
        if pop.sum() <= 0:
            raise ValueError(f"No positive household proxy for {country}")
    household = pop / pop.sum()
    industry = _spatial_proxy(employment, gva, ("B-E", "F"), regions, country, weights, fallbacks)
    service_parts = np.column_stack([_spatial_proxy(employment, gva, (code,), regions, country, weights, fallbacks)
                                    for code in SERVICES])
    # Weight broad service groups using their national employment/GVA levels,
    # then normalize. Neither GVA nor employment is treated as electricity.
    service_group_mix = []
    for table in (employment, gva):
        values = np.array([_lookup(table, geo=_geo(country), nace_r2=c) or 0. for c in SERVICES])
        if values.sum() > 0:
            service_group_mix.append(values / values.sum())
    group_mix = np.mean(service_group_mix, axis=0) if service_group_mix else np.full(len(SERVICES), 1 / len(SERVICES))
    service_joint = service_parts * group_mix
    services = service_joint.sum(axis=1)
    service_shapes_mix = np.divide(service_joint, services[:, None],
                                  out=np.tile(group_mix, (len(regions), 1)), where=services[:, None] > 0)
    farm = (_spatial_proxy(employment, gva, ("A",), regions, country, weights, fallbacks)
            if national[3] > 0 else household)
    nights = cache.optional_table("tour_occ_nin3", year, unit="NR", c_resid="TOTAL", nace_r2="I551-I553") if tourism_share else pd.DataFrame()
    tourism = np.array([_regional(nights, r, country, weights, fallbacks, "visitor nights") for r in regions]) if tourism_share else services.copy()
    if tourism_share:
        valid = np.isfinite(tourism)
        scale = tourism[valid].sum() / services[valid].sum() if valid.any() and tourism[valid].sum() > 0 and services[valid].sum() > 0 else 1.
        tourism[~valid] = services[~valid] * scale
        fallbacks.extend(dict(region=region, feature="visitor nights",
                              basis="service-activity share at covered-region average visitor intensity")
                         for region, covered in zip(regions, valid) if not covered)
        if tourism.sum() <= 0:
            tourism = services.copy()
            fallbacks.append(dict(region=country, feature="tourism", basis="no positive visitor nights: services spatial proxy"))
    tourism /= tourism.sum()
    proxy = np.column_stack([household, industry, services, farm, tourism, weights.to_numpy()])
    # Strictly positive regularization is an explicit weak prior, not energy
    # added to the final demand. It makes compatible margins feasible even
    # when parent geographies or rounded zero employment give sparse support.
    proxy = .999999 * proxy + .000001 * weights.to_numpy()[:, None]
    budget, diagnostics = balance(proxy * national, weights.to_numpy(), national, rtol=1e-14)
    return budget, service_shapes_mix, dict(
        feature_year=year, fallbacks=fallbacks, national_electricity_GWh=balances,
        national_sector_fractions=dict(zip(SECTORS, national.tolist())),
        tourism_fraction_of_services= tourism_share, composition_balancing=diagnostics,
        composition_method="Equal blend of normalized employment and GVA spatial proxies, scaled to national sector electricity; household population; tourism visitor nights. Region/sector budgets reconciled to JRC regional shares and national final-sector fractions.",
        assumptions=["National final-electricity sector fractions are rescaled to the ENTSO-E grid-load boundary; they are not additional demand.",
                     "Industry B-E plus F is a broad proxy; it does not distinguish individual energy-intensive plants.",
                     "The tourism fraction of service electricity is a user-adjustable assumption, not an observed energy statistic.",
                     "Within each service A10 group, one representative/equal mix of available German branch profiles is transferred.",
                     "A 1e-6 JRC-weighted positive prior regularizes sector allocation; actual zero-demand target zones remain zero."])


def library(directory=LIBRARY):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    for filename, checksum in manifest["files"].items():
        path = directory / filename
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
            raise ValueError(f"Missing or damaged electricity profile library: {path}")
    return pd.read_csv(directory / "bdew_2025_hourly.csv"), pd.read_csv(directory / "demandregio_2018_hourly.csv"), manifest


def country_calendar(country, stamps, cache):
    zone = TIMEZONES.get(country)
    if zone is None:
        raise ValueError(f"No local calendar timezone for sector profiles: {country}")
    tz = ("Asia/" if country == "CY" else "Europe/") + zone
    local = stamps.tz_convert(ZoneInfo(tz))
    holidays = set()
    code = {"EL": "GR", "UK": "GB"}.get(country, country)
    # UTC boundary hours can fall into the adjacent local calendar year.
    for year in sorted(set(local.year)):
        try:
            data = cache.get(f"holidays_{code}_{year}", f"https://date.nager.at/api/v3/PublicHolidays/{year}/{code}")
            if not isinstance(data, list):
                raise ValueError("Holiday API did not return a list")
            holidays.update(item["date"] for item in data if item.get("global") and "Public" in item.get("types", []))
        except (RuntimeError, ValueError, KeyError) as exc:
            cache.warnings.append(f"{code}/{year}: no public-holiday calendar; weekends only ({exc})")
    holiday = np.array([stamp.strftime("%Y-%m-%d") in holidays for stamp in local])
    weekday = np.array(local.dayofweek)
    weekday[holiday] = 6
    daytype = np.where(weekday == 6, "sunday", np.where(weekday == 5, "saturday", "weekday"))
    # BDEW treats Christmas Eve and New Year's Eve as Saturdays unless Sunday.
    special = (local.month == 12) & np.isin(local.day, [24, 31]) & (weekday != 6)
    daytype[special] = "saturday"
    return local, weekday, daytype, dict(timezone=tz, public_holiday_dates=sorted(holidays),
                                       holiday_scope="national public holidays; regional holidays excluded")


def _normalize(values):
    values = np.asarray(values, dtype=float)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError("Sector shape must contain finite positive values")
    return values / values.sum()


def construct_shapes(country, load, regions, service_mix, cache, tourism_share, directory=LIBRARY):
    bdew, research, manifest = library(directory)
    local, weekday, daytype, calendar_report = country_calendar(country, load.index, cache)
    keys = pd.MultiIndex.from_arrays([local.month, weekday, local.hour])
    bdew_keys = pd.MultiIndex.from_arrays([local.month, daytype, local.hour])

    def branch(code):
        source = research.loc[research.profile.eq(code)].set_index(["month", "weekday", "hour"])["value"]
        return _normalize(source.reindex(keys).to_numpy())

    def standard(code):
        source = bdew.loc[bdew.profile.eq(code)].set_index(["month", "daytype", "hour"])["value"]
        values = source.reindex(bdew_keys).to_numpy(copy=True)
        if code == "H25":
            day = local.dayofyear.to_numpy()
            factor = -3.92e-10 * day**4 + 3.20e-7 * day**3 - 7.02e-5 * day**2 + 2.10e-3 * day + 1.24
            values *= factor
        return _normalize(values)

    household, agriculture = standard("H25"), standard("L25")
    industry = np.mean([branch(code) for code in INDUSTRIAL_PROFILES], axis=0)
    service_shapes = np.column_stack([np.mean([branch(code) for code in SERVICE_PROFILES[group]], axis=0)
                                     for group in SERVICES])
    hotel = branch("WZ55")
    # Remove German between-month accommodation seasonality before assigning
    # local observed nights. Preserve the within-month daily/hourly pattern.
    month = local.month.to_numpy()
    for m in range(1, 13):
        hotel[month == m] /= hotel[month == m].sum()
    monthly = cache.optional_table("tour_occ_nin2m", int(load.index[0].year), unit="NR", c_resid="TOTAL", nace_r2="I551-I553") if tourism_share else pd.DataFrame()
    shapes = np.empty((len(load), len(regions), len(SECTORS)))
    tourism_bases = []
    for number, region in enumerate(regions):
        season = None
        for geo in (_geo(country) + region[2:], _geo(country) + region[2:4], _geo(country)):
            values = [_lookup(monthly, geo=geo, month=f"M{m:02d}") for m in range(1, 13)]
            if all(value is not None for value in values) and sum(values) > 0:
                season = np.array(values) / sum(values)
                basis = geo
                break
        if season is None:
            # No invented summer multiplier: equal daily occupancy across the
            # available calendar, with the source hotel day/hour shape.
            season = np.bincount(month, minlength=13)[1:].astype(float)
            season /= season.sum()
            basis = "constant daily occupancy: no complete monthly tourism series"
        tourism = hotel * season[month - 1]
        # Report zero observed nights, but retain tiny positive shape support
        # for compatible country-hour/annual constraints after balancing.
        tourism = .999999 * tourism + .000001 / len(load)
        shapes[:, number, :] = np.column_stack([household, industry,
            _normalize(service_shapes @ service_mix[number]), agriculture,
            _normalize(tourism), _normalize(load.to_numpy() + 1e-12)])
        tourism_bases.append(dict(region=region, monthly_nights_basis=basis, monthly_fractions=season.tolist()))
    return shapes, dict(profile_library=manifest, calendar=calendar_report, tourism_seasonality=tourism_bases,
                        profile_transfer="German representative sector profiles; no regional metered-load accuracy claim. Country weather/calendar effects also enter through the observed ENTSO-E curve. No local temperature model is fitted.")


def reconcile_profiles(load, weights, fractions, shapes):
    """Preserve source-year AND model-year annual shares, including leap years."""
    weights = weights.reindex(fractions.index)
    budget = fractions.to_numpy()
    if not np.allclose(budget.sum(axis=1), weights.to_numpy(), rtol=0, atol=1e-9):
        raise ValueError("Sector budgets do not preserve JRC regional shares")
    if shapes.shape != (len(load), len(weights), budget.shape[1]):
        raise ValueError("Sector profile dimensions differ from annual budget dimensions")
    result = np.zeros((len(load), len(weights)))
    diagnostics = {}
    # Balance Feb 29 as its own block, using the same regional/sector shares.
    # Then both the full source year and model calendar preserve annual ratios.
    leap = (load.index.month == 2) & (load.index.day == 29)
    for name, mask in (("model_8760", ~leap), ("february_29", leap)):
        if not mask.any():
            continue
        target = budget.ravel() * float(load.to_numpy()[mask].sum())
        prior = shapes[mask].reshape(mask.sum(), -1) * budget.ravel()
        annual_prior = prior.sum(axis=0)
        prior *= np.divide(target, annual_prior, out=np.zeros_like(target), where=annual_prior > 0)[None, :]
        final, report = balance(prior, load.to_numpy()[mask], target)
        report["relative_L1_adjustment_to_prior"] = float(np.abs(final - prior).sum() / max(1., final.sum()))
        report["regional_max_annual_error_MWh"] = float(np.max(np.abs(
            final.reshape(mask.sum(), len(weights), -1).sum(axis=(0, 2)) - weights.to_numpy() * load.to_numpy()[mask].sum())))
        result[mask] = final.reshape(mask.sum(), len(weights), -1).sum(axis=2)
        diagnostics[name] = report
    return result, diagnostics


def generate_sector_profiles(country, year, load, weights, cache_dir, *, refresh=False, tourism_share=.1):
    cache = SourceCache(Path(cache_dir) / "electricity_composition", refresh)
    budget, service_mix, features = composition(country, year, weights, cache, tourism_share)
    shapes, source_report = construct_shapes(country, load, list(weights.index), service_mix, cache, tourism_share)
    fractions = pd.DataFrame(budget, index=weights.index, columns=SECTORS)
    matrix, diagnostics = reconcile_profiles(load, weights, fractions, shapes)
    model = ~((load.index.month == 2) & (load.index.day == 29))
    ledger = fractions.mul(float(load.loc[model].sum())).rename_axis("region").reset_index()
    for column in SECTORS:
        ledger = ledger.rename(columns={column: column + "_MWh"})
    return matrix, dict(method="sector-weighted", **features, **source_report,
                        reconciliation=diagnostics, sources=cache.sources, warnings=cache.warnings), ledger
