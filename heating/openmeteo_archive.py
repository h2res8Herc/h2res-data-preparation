"""Serve historical heating point requests from Open-Meteo's public annual grids."""
from calendar import isleap
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from io import BytesIO
import json
import time

import numpy as np


class ArchiveObject:
    """The size and range-read interface used by OmFileReader.from_fsspec."""

    def __init__(self, url):
        import requests

        self.url = url
        self.session = requests.Session()
        with self.session.head(url, timeout=20) as response:
            response.raise_for_status()
            self.length = int(response.headers["Content-Length"])
            self.etag = response.headers["ETag"]
        # Nearby sample points and repeated index reads share the same blocks.
        self.block_size = 512 * 1024
        self.block = lru_cache(maxsize=64)(self._read_block)

    def size(self, path):
        return self.length

    def _read_block(self, index):
        start = index * self.block_size
        end = min(start + self.block_size, self.length)
        headers = {"Range": f"bytes={start}-{end - 1}", "If-Match": self.etag}
        with self.session.get(self.url, headers=headers, timeout=30, stream=True) as response:
            response.raise_for_status()
            if response.status_code != 206 or response.headers.get("Content-Range") != f"bytes {start}-{end - 1}/{self.length}":
                raise OSError("Open-Meteo archive returned an unexpected byte range")
            data = response.content
            if len(data) != end - start:
                raise OSError("Incomplete Open-Meteo archive range")
            return data

    def cat_file(self, path, start, end):
        first, offset = divmod(start, self.block_size)
        last = (end + self.block_size - 1) // self.block_size
        data = b"".join(self.block(index) for index in range(first, last))
        return data[offset:offset + end - start]


@lru_cache(maxsize=2)
def annual_grid(model, year):
    from omfiles import OmFileReader

    url = f"https://openmeteo.s3.amazonaws.com/data/copernicus_{model}/temperature_2m/year_{year}.om"
    obj = ArchiveObject(url)
    reader = OmFileReader.from_fsspec(obj, url)
    scale = 10 if model == "era5_land" else 4
    if tuple(reader.shape) != (180 * scale + 1, 360 * scale, 24 * (365 + isleap(year))):
        raise ValueError(f"Unexpected annual grid dimensions for {url}: {reader.shape}")
    print(f"Reading hourly heating temperatures from {url}", flush=True)
    return reader, obj, scale


@lru_cache(maxsize=2)
def hourly_timestamps(year):
    first = datetime(year, 1, 1)
    return [(first + timedelta(hours=i)).isoformat(timespec="minutes") for i in range(24 * (365 + isleap(year)))]


_retry_after = {}


def archive_response(params):
    """Return the usual hourly payload, or let the caller use the point API."""
    model = params.get("models")
    if (model not in ("era5_land", "era5") or params.get("hourly") != "temperature_2m"
            or params.get("timezone") != "GMT" or params.get("elevation") != "nan"
            or params.get("cell_selection") not in ("nearest", "land")):
        return None
    start = date.fromisoformat(params["start_date"])
    year = start.year
    if (start != date(year, 1, 1) or params["end_date"] != f"{year}-12-31"
            or year >= datetime.now(timezone.utc).year):
        return None
    key = model, year
    if time.monotonic() < _retry_after.get(key, 0):
        return None
    try:
        reader, obj, scale = annual_grid(model, year)
        # Open-Meteo selects the nearest cell for both selectors when elevation
        # is NaN. Clamp the eastern boundary to the final longitude cell,
        # matching Open-Meteo's RegularGrid.findPointXy.
        lat = np.float32(params["latitude"])
        lon = np.float32(params["longitude"])
        spacing = np.float32(1 / scale)
        y = int(np.floor((lat + np.float32(90)) / spacing + np.float32(.5)))
        x = min(int(np.floor((lon + np.float32(180)) / spacing + np.float32(.5))), 360 * scale - 1)
        series = np.asarray(reader[y, x, :], dtype=np.float32).reshape(-1)
    except (ImportError, OSError, RuntimeError, ValueError, KeyError) as exc:
        print(f"Bulk weather unavailable for {model}/{year} ({exc}). Using the Open-Meteo point API.", flush=True)
        annual_grid.cache_clear()
        _retry_after[key] = time.monotonic() + 900
        return None
    # Match API decimal rounding (ties away from zero). Keep missing hours
    # for the existing gap checks and the coastal ERA5 fallback.
    tenths = np.copysign(np.floor(np.abs(series) * 10 + .5), series)
    values = [v / 10 if np.isfinite(v) else None for v in tenths.tolist()]
    payload = dict(latitude=y / scale - 90, longitude=x / scale - 180, timezone="GMT", utc_offset_seconds=0,
                   bulk_source=dict(url=obj.url, etag=obj.etag, grid_index=[y, x], selection="nearest",
                                    elevation_adjustment=False),
                   hourly_units=dict(time="iso8601", temperature_2m="°C"),
                   hourly=dict(time=hourly_timestamps(year), temperature_2m=values))
    return BytesIO(json.dumps(payload, allow_nan=False, separators=(",", ":")).encode("utf-8"))
