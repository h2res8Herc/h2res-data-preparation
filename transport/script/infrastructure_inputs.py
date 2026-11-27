"""Fleet-linked charging and refuelling inputs for the native November 21 model."""
from pathlib import Path

import pandas as pd

PROFILES = "transport_infrastructure.csv"
EXISTING = "transport_infrastructure_existing.csv"
DEFAULTS = Path(__file__).resolve().parent


def generate(fleet, output, reference=None):
    def read(name):
        path = reference / name if reference is not None else DEFAULTS / name
        return pd.read_csv(path if path.is_file() else DEFAULTS / name)

    profiles, existing = read(PROFILES), read(EXISTING)
    domestic = profiles.loc[profiles.sector.eq("Domestic_shipping")]
    sectors = set(fleet.sector)
    for sector, prefix in [("Domestic_coastal_shipping","ship_short_"), ("Inland_waterways","ship_mid_")]:
        if sector in sectors and sector not in set(profiles.sector):
            extra = domestic.assign(sector=sector, unit=domestic.unit.str.replace("ship_short_",prefix,regex=False))
            if sector == "Domestic_coastal_shipping" and "Domestic_shipping" in sectors:
                extra["unit"] = extra.unit.str.replace("ship_short_", "ship_coastal_", regex=False)
            profiles = pd.concat([profiles,extra],ignore_index=True)
    profiles = profiles.loc[profiles.sector.isin(sectors)].copy()
    if profiles.unit.duplicated().any():
        raise ValueError("Duplicate charging infrastructure profile identifiers")
    types = profiles.assign(type=profiles.vehicle_types.str.split("|",regex=False)).explode("type")
    vehicles = fleet.loc[fleet.type.isin(["BAT","EL","PHEV","FCEV"]),["sector","type","zone","System"]].drop_duplicates()
    pairs = vehicles.merge(types[["unit","sector","type","life_years"]],how="left",on=["sector","type"])
    if pairs.unit.isna().any():
        raise ValueError(f"Missing charging profiles for {pairs.loc[pairs.unit.isna(), ['sector','type']].drop_duplicates().to_dict('records')}")
    keys = ["unit","zone","System"]
    stock = pairs[keys+["life_years"]].drop_duplicates().merge(existing,on=keys,how="left",validate="one_to_one")
    stock["number"] = stock.number.fillna(0.)
    stock["existing_remaining_life_years"] = stock.existing_remaining_life_years.fillna(stock.life_years)
    profiles.to_csv(output/PROFILES,index=False)
    stock[existing.columns].to_csv(output/EXISTING,index=False)
    return [PROFILES, EXISTING]
