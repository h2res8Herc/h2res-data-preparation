"""JRC-IDEES-2021 navigation and aviation balances and inland port throughput."""
from io import StringIO
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

BALANCES = Path(__file__).with_name("idees_navigation_aviation_2020.csv")
PORTS = Path(__file__).with_name("inland_port_freight_2020.csv")
INLAND_BASIS = "Eurostat_iww_go_aport_2020"
COMPONENTS = ("Domestic coastal shipping", "Inland waterways")


def corrected_table(content, rows):
    table = pd.read_csv(StringIO(content))
    result = []
    for row in table.to_dict("records"):
        domestic = row["sector"] == "Domestic shipping"
        matches = rows.loc[rows.sector.isin(COMPONENTS) if domestic else rows.sector.eq(row["sector"])]
        if matches.empty:
            result.append(row)
            continue
        if domestic and row["number"] != 0:
            raise ValueError("Domestic vessel stock requires a coastal and inland split")
        for match in matches.itertuples():
            energy_gwh = match.energy_ktoe * 11.63
            if (match.activity_million > 0) != (energy_gwh > 0):
                raise ValueError(f"Inconsistent activity and energy for {match.country}/{match.sector}")
            unit = {"Domestic coastal shipping": "ICE_MARINE_SHORT", "Inland waterways": "ICE_MARINE_MID"}.get(match.sector, row["unit_name"])
            result.append(dict(row, sector=match.sector, unit_name=unit, total_load=match.activity_million,
                               efficiency_primary=match.activity_million / energy_gwh if energy_gwh else 0.))
    return pd.DataFrame(result).to_csv(index=False)


def inland_weights(country, nuts):
    """Use located Eurostat throughput, retaining coverage and unresolved tonnage."""
    ports = pd.read_csv(PORTS)
    ports = ports.loc[ports.country.eq(country)]
    zones = nuts.set_index("NUTS_ID").to_crs(3035)
    totals = pd.Series(0., index=zones.index)
    records = []
    for port in ports.itertuples():
        zone = None
        if pd.notna(port.lon) and pd.notna(port.lat):
            point = gpd.points_from_xy([port.lon], [port.lat], crs=4326).to_crs(3035)[0]
            distances = zones.distance(point)
            nearest = distances.idxmin()
            if distances[nearest] <= 5000:
                zone = nearest
                totals[zone] += port.tonnes
        records.append(dict(port=port.port, nuts3=zone, tonnes=port.tonnes))
    return totals, dict(dataset="iww_go_aport", year=2020, unit="tonnes loaded + unloaded",
                        reported_tonnes=int(ports.tonnes.sum()), located_tonnes=int(totals.sum()), ports=records)
