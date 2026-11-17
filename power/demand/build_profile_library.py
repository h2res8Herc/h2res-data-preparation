"""Rebuild the compact, attributed profile library from original source files.

Developer utility: sources are downloaded separately, never fabricated here.
The application uses the resulting small CSVs, not the 153 MB research archive.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
from zipfile import ZipFile

import numpy as np
import openpyxl
import pandas as pd

DESTINATION = Path(__file__).resolve().parent / "profile_library"


def build(source: Path, destination: Path = DESTINATION):
    destination.mkdir(parents=True, exist_ok=True)
    workbook = source / "bdew_2025.xlsx"
    book = openpyxl.load_workbook(workbook, read_only=True, data_only=True)
    records = []
    for profile in ("H25", "G25", "L25"):
        rows = list(book[profile].values)
        for month in range(1, 13):
            for offset, daytype in enumerate(("saturday", "sunday", "weekday")):
                column = 2 + (month - 1) * 3 + offset
                values = np.array([float(row[column]) for row in rows[4:100]])
                if len(values) != 96 or not np.isfinite(values).all() or (values < 0).any():
                    raise ValueError(f"Invalid BDEW values: {profile}/{month}/{daytype}")
                # Sum four quarter-hour energy values to obtain hourly energy.
                for hour, value in enumerate(values.reshape(24, 4).sum(axis=1)):
                    records.append((profile, month, daytype, hour, value))
    pd.DataFrame(records, columns=["profile", "month", "daytype", "hour", "value"]).to_csv(
        destination / "bdew_2025_hourly.csv", index=False, float_format="%.10g")
    records = []
    archive = source / "demandregio.zip"
    expected = "68d48af3de0eb0f2159959a965237633"
    if hashlib.md5(archive.read_bytes()).hexdigest() != expected:
        raise ValueError("DemandRegio archive does not match the published Zenodo checksum")
    with ZipFile(archive) as package:
        for name in sorted(package.namelist()):
            if not name.endswith("2018.csv"):
                continue
            code = re.search(r"/(WZ[\d-]+)_", name).group(1)
            frame = pd.read_csv(io.BytesIO(package.read(name)), sep=";", decimal=",", skiprows=[1], index_col=0)
            stamps = pd.to_datetime(frame.index)
            values = pd.to_numeric(frame["Mean_Value"], errors="raise")
            if not np.isfinite(values).all() or (values < 0).any():
                raise ValueError(f"Invalid DemandRegio values: {name}")
            # Published timestamps identify quarter-hour samples. Average them
            # into month/weekday/hour typical values; no raw meter data copied.
            typical = pd.DataFrame(dict(month=stamps.month, weekday=stamps.dayofweek,
                                        hour=stamps.hour, value=values.to_numpy()))
            typical["value"] /= typical["value"].mean()
            grouped = typical.groupby(["month", "weekday", "hour"])["value"].mean()
            if len(grouped) != 12 * 7 * 24:
                raise ValueError(f"Incomplete DemandRegio template: {code}")
            records.extend((code, *key, value) for key, value in grouped.items())
    pd.DataFrame(records, columns=["profile", "month", "weekday", "hour", "value"]).to_csv(
        destination / "demandregio_2018_hourly.csv", index=False, float_format="%.10g")
    manifest = dict(version="sector-library-1", sources=[
        dict(title="BDEW Standardlastprofile Strom 2025", profiles=["H25", "G25", "L25"],
             url="https://www.bdew.de/energie/standardlastprofile-strom/",
             download_url="https://www.bdew.de/media/documents/Kopie_von_Repr%C3%A4sentative_Profile_BDEW_H25_G25_L25_P25_S25_Ver%C3%B6ffentlichung.xlsx",
             source_sha256=hashlib.sha256(workbook.read_bytes()).hexdigest(),
             attribution="BDEW Bundesverband der Energie- und Wasserwirtschaft e.V., 2025. Publicly provided representative profiles; no open-data licence asserted.",
             transformation="Four quarter-hour energy values summed per hour. Household dynamization applied at runtime according to BDEW 17 March 2025 guidance, page 4. P25/S25 are excluded."),
        dict(title="Regression-based electricity load profiles of 32 industrial and commercial sub-sectors in Germany",
             authors="Stephan Seim, Daniel Ruedt, Qi Wu, Maike Held, Paul Verwiebe, Joachim Mueller-Kirchenbauer",
             url="https://doi.org/10.5281/zenodo.4576494", licence="CC BY 4.0",
             licence_url="https://creativecommons.org/licenses/by/4.0/", source_md5=expected,
             transformation="2018 weighted German mean profiles: normalize each branch by its annual mean, then average by month, weekday and clock hour. German holiday/weather effects remain in those averages. No disaggregator code reused.")],
        files={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.glob("*.csv")})
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Built compact sector profile library: {destination}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_directory", type=Path)
    build(parser.parse_args().source_directory)
