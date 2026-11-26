"""Plot NUTS3 transport inputs from a completed HR, SI or IT loader run."""
import argparse
import hashlib
import json
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import pandas as pd

from navigation_allocation import METHOD
from navigation_sources import BALANCES, COMPONENTS


def transport_data(directory, country, regions):
    proof = json.loads((directory / "paper_spatial_calculation.json").read_text(encoding="utf-8"))
    if proof.get("navigation_method") != METHOD:
        raise ValueError(f"{country}: regenerate transport with the updated loader before plotting")
    hashes = {Path(item["file"]).name: item["sha256"] for item in proof["outputs"]}
    source = pd.read_csv(BALANCES).query("country == @country")
    blocks = []
    for kind in ("passenger", "freight"):
        path = directory / f"transp1_shape_{kind}_NUTS3.csv"
        if hashes.get(path.name) != hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError(f"{path} differs from its recorded allocation output")
        raw = pd.read_csv(path)
        if set(raw.country) != {country} or not np.isfinite(raw[["energy_MWh", "total_load"]]).all().all():
            raise ValueError(f"Invalid country or missing transport values in {path}")
        grouped = raw.groupby(["sector", "nuts3"])[["energy_MWh", "total_load"]].sum()
        modes = dict(list(grouped.groupby(level="sector")))
        for ref in source.loc[source.kind.eq(kind)].itertuples():
            if kind == "freight" and "aviation" in ref.sector.lower():
                continue
            if ref.sector not in modes and ref.sector in COMPONENTS and ref.activity_million == ref.energy_ktoe == 0:
                index = pd.MultiIndex.from_product([[ref.sector], regions.index], names=grouped.index.names)
                modes[ref.sector] = pd.DataFrame(0., index=index, columns=grouped.columns)
            values = modes[ref.sector].sum()
            np.testing.assert_allclose(values, [ref.energy_ktoe * 11630, ref.activity_million], rtol=1e-8, atol=1e-6)
        for name, mode in modes.items():
            if set(mode.index.get_level_values("nuts3")) != set(regions.index):
                raise ValueError(f"Incomplete {country} NUTS3 grid for {name}")
        table = pd.concat(modes.values()).reset_index()
        blocks.append(table.assign(kind=kind))
    return pd.concat(blocks, ignore_index=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", choices=["HR", "SI", "IT"], required=True)
    parser.add_argument("--transport-dir", type=Path, required=True, help="Country folder containing allocated NUTS3 CSVs")
    parser.add_argument("--nuts3", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    regions = gpd.read_file(args.nuts3)
    regions = regions.loc[regions.NUTS_ID.str.startswith(args.country) & regions.NUTS_ID.str.len().eq(5)]
    regions = regions.set_index("NUTS_ID").to_crs(3035)
    if regions.empty or not regions.index.is_unique:
        raise ValueError("Expected a unique NUTS3 boundary layer")
    frame = transport_data(args.transport_dir, args.country, regions)
    frame["country"] = args.country
    frame["region_name"] = frame.nuts3.map(regions.NUTS_NAME)
    frame["activity_unit"] = frame.kind.map({"passenger": "million passenger-km", "freight": "million tonne-km"})
    frame["energy_GWh"] = frame.energy_MWh / 1000
    args.out.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.out / f"{args.country}_transport_regions.csv", index=False)
    with PdfPages(args.out / f"{args.country}_transport_atlas.pdf") as pdf:
        for kind, part in frame.groupby("kind", sort=False):
            for metric in ["total_load", "energy_GWh"]:
                sectors = part.sector.unique()
                for offset in range(0, len(sectors), 4):
                    fig, axes = plt.subplots(2, 2, figsize=(10, 9), layout="constrained")
                    for ax in axes.flat:
                        ax.set_axis_off()
                    for ax, sector in zip(axes.flat, sectors[offset:offset+4]):
                        subset = part.loc[part.sector.eq(sector)].set_index("nuts3")
                        values = subset[metric].reindex(regions.index)
                        total = values.sum()
                        unit = "GWh" if metric == "energy_GWh" else subset.activity_unit.iloc[0]
                        regions.plot(ax=ax, color="#eeeeee", edgecolor="#777777", linewidth=.25)
                        if total > 0:
                            share = 100 * values / total
                            active = share.gt(0)
                            regions.loc[active].plot(column=share.loc[active], ax=ax, cmap="viridis", vmin=0,
                                vmax=share.max(), legend=True, legend_kwds={"shrink": .65, "label": "% of national mode total"},
                                edgecolor="#555555", linewidth=.25)
                        ax.set_title(f"{sector}\nNational total {total:,.2f} {unit}", fontsize=10)
                    fig.suptitle(f"{args.country} · {kind.title()} transport · " +
                                 ("Energy demand" if metric == "energy_GWh" else "Transport activity"))
                    pdf.savefig(fig)
                    fig.savefig(args.out / f"{args.country}_{kind}_{metric}_{offset//4+1}.png", dpi=160)
                    plt.close(fig)


if __name__ == "__main__":
    main()
