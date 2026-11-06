"""Provenance and method checks for prepared heating/transport observations."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sources(paths):
    return [dict(file=str(Path(path).resolve()), sha256=file_hash(path)) for path in paths]


def verify_records(records):
    for item in records:
        if file_hash(item["file"]) != item["sha256"]:
            raise ValueError(f"Prepared method source changed: {item['file']}; regenerate the sector")


def transport_allocation(args):
    """Written only after a successful actual infrastructure allocation."""
    root = Path(args.out_root)
    for country in args.countries:
        directory = root / country
        pbf = Path(args.pbf_dir) / f"{country}.osm.pbf"
        osm = json.loads((pbf.parent / (pbf.name + ".h2res_infrastructure/source.json")).read_text(encoding="utf-8"))
        if osm["parser"] != "pyosmium" or osm["sha256"] != file_hash(pbf):
            raise ValueError("Transport infrastructure was not read from the current OSM source")
        outputs = [directory / name for name in ("debug_weights_NUTS3.csv", "transp1_shape_passenger_NUTS3.csv", "transp1_shape_freight_NUTS3.csv")]
        inputs = [pbf, Path(args.nuts3), Path(__file__).parent / "transport/script/osm_infrastructure.py",
                  Path(__file__).parent / "transport/script/activity_units.py",
                  Path(__file__).parent / "transport/script/navigation_allocation.py",
                  Path(__file__).parent / "transport/script/generate_transport_inputs_standalone.py"]
        inputs.append(Path(args.paper_allocator))
        inputs += sorted((Path(args.national_dir) / country).glob("*.csv"))
        inputs += [Path(path) for path in (args.oil_raster, args.el_raster) if path is not None]
        details = dict(method_id="paper_transport_v1", sources=sources(inputs), outputs=sources(outputs),
                       infrastructure=osm, national_table_basis="bundled JRC-derived national table snapshot; legacy CSVs do not declare a selectable source year",
                       road_weights="separate EIGL oil/electricity rasters",
                       infrastructure_measurement="clipped regional line lengths/areas and station/port/aerodrome counts",
                       national_activity_units="million passenger-km or tonne-km; diagnostic MWh = total_load * 1000 / primary_efficiency",
                       maritime_constraint="Sea navigation restricted to GISCO COAST_TYPE 1/2; landlocked domestic navigation uses inland OSM ports/quays",
                       navigation_method=getattr(args, "paper_navigation_method", None),
                       navigation_allocations=getattr(args, "paper_navigation", {}).get(country, []))
        (directory / "paper_spatial_calculation.json").write_text(json.dumps(details,indent=2),encoding="utf-8")


def _checked_transport_countries(args):
    root = Path(args.out_root)
    countries, input_records = {}, []
    for country in args.countries:
        path = root / country / "paper_spatial_calculation.json"
        if not path.is_file():
            raise ValueError("Transport has no verified OSM allocation; regenerate instead of reusing old fallback outputs")
        details = json.loads(path.read_text(encoding="utf-8"))
        verify_records(details["sources"] + details["outputs"])
        import geopandas as gpd
        nuts = gpd.read_file(args.nuts3)
        from transport.script.navigation_allocation import METHOD, navigation_kind, QUANTITIES
        coast_type = pd.to_numeric(nuts.COAST_TYPE, errors="raise")
        coastal = set(nuts.loc[coast_type.isin([1,2]),"NUTS_ID"])
        raw = root / country
        passenger = pd.read_csv(raw / "transp1_shape_passenger_NUTS3.csv")
        freight = pd.read_csv(raw / "transp1_shape_freight_NUTS3.csv")
        all_modes = pd.concat([passenger,freight],ignore_index=True)
        has_coast = bool(set(all_modes.nuts3) & coastal)
        if details.get("navigation_method") != METHOD:
            raise ValueError("Transport navigation provenance predates the inland-waterway fix; regenerate Transport using cached downloads")
        kinds = all_modes.apply(lambda row: navigation_kind(row.sector, row.unit_name, has_coast), axis=1)
        marine = kinds.isin(["maritime", "domestic_navigation"])
        inland = ~all_modes.nuts3.isin(coastal)
        if not all_modes.loc[marine & inland,["total_load","number","energy_MWh"]].fillna(0).eq(0).all().all():
            raise ValueError("Maritime transport was allocated to an inland NUTS3 region")
        air_freight = freight.sector.str.contains("avia|avio|air",case=False,na=False)
        if freight.loc[air_freight,["total_load","number","energy_MWh"]].fillna(0).ne(0).any().any():
            raise ValueError("The paper excludes aviation from freight allocation")
        from transport.script.activity_units import ensure_energy_column
        national_checks = {}
        navigation_checks = []
        debug = pd.read_csv(raw / "debug_weights_NUTS3.csv").set_index("NUTS_ID")
        for mode, allocated in (("passenger", passenger), ("freight", freight)):
            for (sector, unit, technology), block in allocated.groupby(["sector", "unit_name", "type"], sort=False, dropna=False):
                kind = navigation_kind(sector, unit, has_coast)
                if kind is None:
                    continue
                matching = [note for note in details["navigation_allocations"]
                            if (note['table_kind'], note['sector'], note['unit_name'], note['type'])
                            == (mode, sector, unit, technology)]
                if len(matching) != 1 or matching[0]['navigation_kind'] != kind:
                    raise ValueError(f"Missing or inconsistent navigation evidence for {country}/{mode}/{sector}")
                note = matching[0]
                column = ('ship_inland_' if kind == 'inland_navigation' else 'ship_') + ('freight' if mode == 'freight' else 'passenger')
                eligible = set(debug.index[debug[column].gt(0)])
                if note['weights_basis'] == 'assumed_equal_coastal_regions_no_OSM_port_proxy':
                    eligible = set(debug.index) & coastal
                if set(note['eligible_regions']) != eligible:
                    raise ValueError(f"Navigation eligibility differs from the OSM indicators for {country}/{sector}")
                if (not block.get('navigation_kind', pd.Series('',index=block.index)).eq(kind).all()
                        or block.loc[~block.nuts3.isin(eligible), list(QUANTITIES)].fillna(0).ne(0).any().any()):
                    raise ValueError(f"Navigation was allocated outside eligible port/coastal regions for {country}/{sector}")
                navigation_checks.append(note)
            national_path = next(Path(item["file"]) for item in details["sources"]
                                 if Path(item["file"]).name == f"transp1_shape_{mode}.csv")
            national = ensure_energy_column(pd.read_csv(national_path),country + '/' + mode)
            if mode == "freight":
                national = national.loc[~national.sector.str.contains("avia|avio|air",case=False,na=False)]
            keys = ["sector","unit_name","type"]
            expected = national.groupby(keys,dropna=False)[["total_load","number","energy_MWh"]].sum()
            actual = allocated.groupby(keys,dropna=False)[["total_load","number","energy_MWh"]].sum()
            if not np.allclose(actual.reindex(expected.index,fill_value=0.),expected,rtol=1e-8,atol=1e-4):
                raise ValueError(f"{country}/{mode}: regional transport does not conserve national activity, fleet and energy")
            national_checks[mode] = dict(national_totals=expected.sum().to_dict(),conserved=True)
        countries[country] = dict(infrastructure=details["infrastructure"],
                                  maritime_inland_zero=True, freight_aviation_zero=True,
                                  navigation_method=METHOD, navigation_allocations=navigation_checks,
                                  inland_navigation_present=bool((kinds.eq('inland_navigation') & all_modes[list(QUANTITIES)].abs().sum(axis=1).gt(0)).any()),
                                  inland_navigation_non_port_zero=True,
                                  national_table_basis=details["national_table_basis"],
                                  national_activity_units=details["national_activity_units"],national_conservation=national_checks)
        input_records += sources([path])
    return countries, input_records


def validate_transport_allocation(args):
    """Reject invalid spatial results before constructing hourly/model workbooks."""
    _checked_transport_countries(args)


def write_transport(args):
    root = Path(args.out_root)
    countries, input_records = _checked_transport_countries(args)
    names = ["transport_all.csv","transport_profiles.csv","transport_demand.csv"]
    details = dict(method_id="paper_transport_v1",countries=countries,sources=input_records,
                   files={name:file_hash(root / "combined" / name) for name in names})
    (root / "combined/paper_generation.json").write_text(json.dumps(details,indent=2),encoding="utf-8")


def write_heating(args, input_root):
    from heating.generate_heating_inputs_standalone import locate_country_dir
    root = Path(args.out_root)
    countries, inputs = {}, []
    for country in args.countries:
        directory = locate_country_dir(Path(input_root), country, args.source_year)
        path = directory / "paper_generation.json"
        if not path.is_file():
            raise ValueError("Heating has no verified paper-method sources; regenerate the raw calculations")
        details = json.loads(path.read_text(encoding="utf-8"))
        if details["method_id"] != "paper_heating_v1" or not details["complete"]:
            raise ValueError("Heating calculation is not complete under the paper method")
        verify_records(list(details["inputs"].values()))
        verify_records([dict(file=str(directory/name),sha256=digest) for name,digest in details["outputs"].items()])
        sampling = pd.read_csv(directory / "paper_weather_samples.csv")
        if (not sampling.groupby("nuts3_id").size().eq(8).all()
                or not np.allclose(sampling.groupby("nuts3_id").weight.sum(),1)):
            raise ValueError("Heating must use eight population-weighted samples per NUTS3 region")
        hourly = pd.read_csv(directory / f"hourly_nuts3_{country}_{args.source_year}.csv",usecols=["nuts3_id","fuel","mwh"])
        annual = pd.read_csv(directory / f"annual_nuts3_{country}_{args.source_year}.csv")
        actual = hourly.groupby(["nuts3_id","fuel"]).mwh.sum()
        expected = annual.groupby(["nuts3_id","fuel"]).annual_mwh.sum()
        if not np.allclose(actual.reindex(expected.index,fill_value=0.),expected,rtol=1e-8,atol=1e-4):
            raise ValueError("Hourly heating demand does not conserve its annual region/fuel totals")
        countries[country] = dict(**details["method_details"],year=args.source_year,
                                  degree_hour_annual_conservation=True,sample_count=len(sampling))
        inputs += sources([path])
    names = ["heating_individual.csv","heating_district.csv","heating_electricity.csv",
             "flex_tech_heat.csv","flex_tech_DH.csv","thermal_tech.csv","thermal_tech_DH.csv","solar_indv.csv","solar_DH.csv"]
    details = dict(method_id="paper_heating_v1",countries=countries,sources=inputs,
                   files={name:file_hash(root/name) for name in names})
    (root / "paper_generation.json").write_text(json.dumps(details,indent=2),encoding="utf-8")
