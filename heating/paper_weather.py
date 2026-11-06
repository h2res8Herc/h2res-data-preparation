"""Reproducible population-weighted eight-point regional weather sampling."""
import hashlib
from pathlib import Path
import time

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import mapping


def sample_region(geometry, geometry_crs, population, zone, count=8, seed=0):
    import rasterio
    from rasterio.mask import mask

    with rasterio.open(population) as raster:
        shape = gpd.GeoSeries([geometry], crs=geometry_crs).to_crs(raster.crs).iloc[0]
        pixels, transform = mask(raster, [mapping(shape)], crop=True, filled=False, all_touched=False)
        values = pixels[0].astype(float).filled(np.nan)
        eligible = np.flatnonzero(np.isfinite(values) & (values > 0))
        if not len(eligible):
            raise ValueError(f"No inhabited population-grid cells in {zone}; regional weather requires an explicit assumption")
        stable_seed = int.from_bytes(hashlib.sha256(f"{seed}:{zone}".encode()).digest()[:8], "big")
        generator = np.random.default_rng(stable_seed)
        chosen = generator.choice(eligible, size=count, replace=len(eligible) < count)
        rows, columns = np.unravel_index(chosen, values.shape)
        east, north = rasterio.transform.xy(transform, rows, columns)
        points = gpd.GeoDataFrame(dict(nuts3_id=zone, sample=np.arange(count) + 1,
                                      population=values[rows, columns]),
                                 geometry=gpd.points_from_xy(east, north), crs=raster.crs).to_crs("EPSG:4326")
    points["longitude"], points["latitude"] = points.geometry.x, points.geometry.y
    points["weight"] = points.population / points.population.sum()
    return pd.DataFrame(points.drop(columns="geometry"))


def request_series(reader, era5_path, longitude, latitude, year, verbose=False):
    # A provider failure must not silently change the sampling method or move
    # demand to a centroid. Successful point series remain cached by the reader.
    for attempt in range(5):
        try:
            return reader(era5_path, lon=longitude, lat=latitude, year=year, verbose=verbose)
        except Exception as error:
            cause = error
            while cause is not None and getattr(cause, "code", None) != 429:
                cause = cause.__cause__
            if cause is None or attempt == 4:
                raise
            delay = min(max(float(cause.headers.get("Retry-After", 60)), 1.), 120.)
            print(f"Weather provider rate limit; keeping cached series and retrying in {delay:g}s", flush=True)
            time.sleep(delay)


def regional_hdd(population_totals, nuts, population_raster, era5_path, year, base_temperature,
                 alpha, beta, reader, *, count=8, seed=0, output=None):
    samples, hdd, totals = [], {}, []
    geometry = nuts.set_index("NUTS_ID").geometry
    for row in population_totals.itertuples(index=False):
        zone = row.nuts3_id
        points = sample_region(geometry.loc[zone], nuts.crs, population_raster, zone, count, seed)
        arrays = [np.asarray(request_series(reader, era5_path, point.longitude, point.latitude, year), dtype=float)
                  for point in points.itertuples(index=False)]
        if any(len(array) != 8760 or not np.isfinite(array).all() for array in arrays):
            raise ValueError(f"Incomplete eight-point hourly temperature for {zone}")
        representative = np.average(np.stack(arrays), axis=0, weights=points.weight)
        hdd[zone] = np.maximum(0., base_temperature - representative)
        totals.append(float(hdd[zone].sum()))
        samples.append(points)
        print(f"{zone}: {count} population-weighted weather samples; annual degree-hours {totals[-1]:.1f}", flush=True)
    stats = population_totals.copy()
    stats["hdd_annual"] = totals
    values = np.maximum(stats.pop_sum.to_numpy(), 0.) ** beta * np.maximum(np.asarray(totals), 0.) ** alpha
    if not np.isfinite(values).all() or values.sum() <= 0:
        raise ValueError("Population/degree-hour allocation has no positive finite national weight")
    stats["w_base"] = values / values.sum()
    if output is not None:
        pd.concat(samples, ignore_index=True).to_csv(Path(output) / "paper_weather_samples.csv", index=False)
    return stats[["nuts3_id", "pop_sum", "hdd_annual", "w_base"]], hdd
