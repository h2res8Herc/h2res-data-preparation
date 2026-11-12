# Preparation command-line reference

Generated from the actual `add_argument` call sites. Expressions such as `SCRIPT_DIR / ...` show the source default; they are not literal shell arguments. The authoritative fully resolved help is the script's `--help` output. These commands prepare data rather than execute H2RES.

## generate_all_sector_inputs.py

| Option | Default | Choices / action | Help |
|---|---|---|---|
| `--countries` | `['HR']` | `store` |  |
| `--sectors` | `list(SECTORS)` | `store` | 'Comma-separated subset of power,industry,transport,heating.' |
| `--spatial-level` | `'nuts3'` | `['nuts3', 'nuts2', 'nuts1', 'country', 'custom']` |  |
| `--zone-map` | `argparse default` | `store` | 'Required with --spatial-level custom; full-country country,nuts3,zone mapping. Examples: docs/CUSTOM_ZONES.html.' |
| `--out-root` | `SCRIPT_DIR / 'outputs_all'` | `store` |  |
| `--data-root` | `SCRIPT_DIR / 'data_all'` | `store` |  |
| `--nuts3` | `argparse default` | `store` |  |
| `--refresh-sources` | `argparse default` | `'store_true'` |  |
| `--efuels` | `False` | `argparse.BooleanOptionalAction` |  |
| `--industry-mode` | `'categories'` | `('regular', 'categories', 'complex')` | 'Categories and complex industry are mutually exclusive model modes.' |
| `--industry-electricity-case` | `'conservative'` | `('conservative', 'technical_2050')` |  |
| `--industry-source-root` | `argparse default` | `store` | 'Directory containing country JRC-IDEES-2023 Industry and both balance workbooks; otherwise use cache/public downloads' |
| `--industry-download` | `True` | `argparse.BooleanOptionalAction` |  |
| `--industry-base-year` | `2020` | `store` |  |
| `--industry-waste-allocation` | `'sector-blend'` | `('strict', 'sector-blend')` | 'Use exact single-class waste evidence, or an explicitly recorded sector-blend assumption where needed' |
| `--industry-zone-weights` | `argparse default` | `store` | "Complex industry regional allocation: country,zone,Industry,weight; '*' means every sector" |
| `--industry-regional-allocation` | `'require-weights'` | `('require-weights', 'equal')` | 'National JRC data need explicit weights at regional resolution; equal is an explicit proxy' |
| `--complex-industry-sectors` | `'all'` | `store` | 'Complex sector selection: all or comma-separated native Industry labels' |
| `--model-root` | `argparse default` | `store` | 'Snapshot the live data from this model directory into the portable reference.' |
| `--model-reference` | `DEFAULT_REFERENCE` | `store` |  |
| `--model-export` | `True` | `argparse.BooleanOptionalAction` | 'Export canonical data files and the selected current model workbook.' |
| `--refactored-export` | `argparse default` | `'store_true'` | 'Also export data_refactored and H2RES_refactored_inputs.zip using the bus-based CSV contract.' |
| `--refactored-model-root` | `argparse default` | `store` | 'Optional refactored installation for actual-reader checks; separate from legacy --model-root.' |
| `--model-ready-package` | `None` | `argparse.BooleanOptionalAction` | 'Also write h2res_inputs and H2RES_model_inputs.zip with the selected flex_tech workbook and distributions.' |
| `--all-model-variants` | `True` | `argparse.BooleanOptionalAction` | 'Populate every native flex_tech/industry companion variant for the selected countries and write the ready-to-use data folder.' |
| `--export-only` | `argparse default` | `'store_true'` | 'Package existing sector outputs without downloading or regenerating sources.' |
| `--import-model-inputs` | `argparse default` | `'store_true'` | "Copy the supplied model's complete baseline inputs, preserving its original geography." |
| `--require-model-ready` | `argparse default` | `'store_true'` | 'Return an error if generated curves or model zone coverage are incomplete.' |
| `--scenario-preset` | `argparse default` | `('reference', 'res100')` | 'Keep reference assumptions or target 100%% renewable energy.' |
| `--scenario-scope` | `argparse default` | `('all-energy', 'electricity')` |  |
| `--scenario-config` | `argparse default` | `store` | 'JSON scenario assumptions and investment overrides.' |
| `--planning-years` | `argparse default` | `store` | 'Comma-separated equally spaced decision years.' |
| `--start-year` | `argparse default` | `store` |  |
| `--end-year` | `argparse default` | `store` |  |
| `--year-step` | `argparse default` | `store` |  |
| `--renewable-target-year` | `argparse default` | `store` |  |
| `--renewable-start-share` | `argparse default` | `store` | 'Starting electricity renewable-share assumption, from 0 to 1.' |
| `--investment-multiplier` | `argparse default` | `store` | 'Scale reference annual build limits; installed-capacity ceilings stay unchanged.' |
| `--era5` | `argparse default` | `store` |  |
| `--temperature-source` | `'open-meteo'` | `['open-meteo', 'cds-netcdf']` |  |
| `--population-tif` | `argparse default` | `store` |  |
| `--accept-population-terms` | `argparse default` | `'store_true'` |  |
| `--skip-heating-raw` | `argparse default` | `'store_true'` |  |
| `--heating-input-root` | `SCRIPT_DIR / 'heating'` | `store` |  |
| `--hydro-year` | `2020` | `store` |  |
| `--hydro-profiles` | `packaged_hydro / 'runoff_shapes_2020.npz' if (packaged_hydro / 'runoff_shapes_2020.npz').exists() else bulk_hydro / 'outputs/profiles/runoff_shapes_2020.npz'` | `store` |  |
| `--hydro-units` | `packaged_hydro / 'hydro_units.csv' if (packaged_hydro / 'hydro_units.csv').exists() else bulk_hydro / 'outputs/dispaset/hydro_units.csv'` | `store` |  |
| `--hydro-plants` | `packaged_hydro / 'jrc-hydro-power-plant-database.csv' if (packaged_hydro / 'jrc-hydro-power-plant-database.csv').exists() else bulk_hydro / 'data/plants/jrc-hydro-power-plant-database.csv'` | `store` |  |
| `--skip-hydro-profiles` | `argparse default` | `'store_true'` |  |
| `--hydro-output-level` | `'match-power'` | `('match-power', 'aggregated', 'individual', 'both')` | 'Hydro curve level; default follows --power-output-level.' |
| `--power-output-level` | `'aggregated'` | `('aggregated', 'individual', 'both')` | 'Write zonally aggregated plants, individual plants, or both.' |
| `--skip-vre-profiles` | `argparse default` | `'store_true'` | 'Skip wind/solar profiles for source-only or diagnostic exports. Complete H2RES exports always generate them, reusing cached weather.' |
| `--vre-year` | `2020` | `store` |  |
| `--vre-irena-year` | `argparse default` | `store` |  |
| `--vre-weather-source` | `'openmeteo'` | `('openmeteo', 'renewables-ninja')` | 'Weather backend; Renewables.ninja reads RENEWABLES_NINJA_TOKEN.' |
| `--renewables-ninja-dataset` | `'merra2'` | `store` |  |
| `--openmeteo-max-wait` | `DEFAULT_MAX_WAIT` | `store` | 'Maximum seconds per local-estimate pause (0: no cap); quota recovery never aborts the run' |
| `--vre-calibrate` | `True` | `argparse.BooleanOptionalAction` |  |
| `--irena-xlsx` | `SCRIPT_DIR / 'power' / 'VRES_distributions' / 'IRENA_Statistics_Extract_2025H2.xlsx'` | `store` |  |
| `--electricity-demand-year` | `2020` | `store` |  |
| `--skip-electricity-demand` | `argparse default` | `'store_true'` | 'Skip ENTSO-E national load download and EIGL NUTS3/model-zone allocation.' |

## h2res_input_gui.py

| Option | Default | Choices / action | Help |
|---|---|---|---|
| `--check` | `argparse default` | `'store_true'` | 'Check Python and preparation dependencies without opening a window' |
| `--smoke-test` | `argparse default` | `'store_true'` | 'Create and close the interface while keeping its window hidden' |

## preparation_dependencies.py

| Option | Default | Choices / action | Help |
|---|---|---|---|
| `--sectors` | `'power,industry,transport,heating'` | `store` |  |
| `--industry-mode` | `'categories'` | `('regular', 'categories', 'complex')` |  |

## run_model_scenario.py

| Option | Default | Choices / action | Help |
|---|---|---|---|
| `--model-root` | `argparse default` | `store` |  |
| `--bundle` | `Path(__file__).resolve().parent` | `store` |  |
| `--solve` | `argparse default` | `'store_true'` | 'Build and solve; default only checks the actual input reader' |
| `--scenario-name` | `argparse default` | `store` |  |
| `--industry-mode` | `argparse default` | `('regular', 'categories', 'complex')` |  |
| `--efuels` | `None` | `argparse.BooleanOptionalAction` |  |
| `--industry-electricity-case` | `argparse default` | `('conservative', 'technical_2050')` |  |

## industry/generate_industry_inputs_standalone.py

| Option | Default | Choices / action | Help |
|---|---|---|---|
| `--countries` | `parse_countries('HR')` | `store` | 'Comma-separated ISO2 list, e.g. HR,SI,IT, or ALL/EU to run every country found in JRC-IDEES with SECURES profiles' |
| `--year` | `2019` | `store` |  |
| `--secures-year` | `2010` | `store` |  |
| `--nuts-level` | `3` | `[0, 1, 2, 3]` |  |
| `--reserve` | `0.15` | `store` |  |
| `--out-root` | `RUN_DIR` | `store` |  |
| `--data-dir` | `DATA_DIR` | `store` |  |
| `--empty-facility-dir` | `DATA_DIR / 'empty_facility_proxy'` | `store` |  |
| `--clean` | `True` | `argparse.BooleanOptionalAction` |  |
| `--debug` | `argparse default` | `'store_true'` |  |
| `--adjust-hourly` | `True` | `argparse.BooleanOptionalAction` | "Apply the paper's hourly feedstock correction when moving demand between temperature categories" |
| `--keep-heat-categories` | `argparse default` | `'store_true'` | 'Keep temperature bands in Industry_data; default aggregates to the sector-level shape used by the legacy workbook.' |
| `--efuels` | `False` | `argparse.BooleanOptionalAction` | 'Use the e-fuel-compatible table as canonical Industry_data. All regular/e-fuel and heat-category variants are always written.' |
| `--refresh-helpers` | `argparse default` | `'store_true'` | 'Rewrite embedded helper scripts before running.' |
| `--download-sources` | `True` | `argparse.BooleanOptionalAction` |  |
| `--refresh-sources` | `argparse default` | `'store_true'` |  |
| `--nuts3-url` | `NUTS_URL` | `store` |  |
| `--jrc-idees-url` | `JRC_IDEES_URL` | `store` |  |
| `--secures-url` | `SECURES_URL` | `store` |  |
| `--iep-zip-url` | `None` | `store` |  |
| `--eutl-zip-url` | `None` | `store` |  |
| `--eigl-zip-url` | `None` | `store` |  |
| `--nuts3` | `None` | `store` |  |
| `--jrc-root` | `None` | `store` |  |
| `--secures-root` | `None` | `store` |  |
| `--iep-dir` | `None` | `store` |  |
| `--eutl-dir` | `None` | `store` |  |
| `--eigl-dir` | `None` | `store` |  |
| `--eigl-year` | `None` | `store` |  |
| `--skip-eigl` | `False` | `argparse.BooleanOptionalAction` |  |
| `--regional-allocation` | `'require-weights'` | `('require-weights', 'equal')` | 'Use EIGL/facility geography; equal is an explicit regional proxy assumption' |
| `--tech-template` | `None` | `store` |  |

## industry/generate_complex_industry_inputs.py

| Option | Default | Choices / action | Help |
|---|---|---|---|
| `--countries` | `'HR'` | `store` |  |
| `--zone-map` | `argparse default` | `store` | 'Shared country,nuts3,zone[,system_new] CSV; omitted means national zones' |
| `--reference` | `DEFAULT_REFERENCE` | `store` |  |
| `--output` | `ROOT / 'outputs_all/industry/combined'` | `store` |  |
| `--cache` | `ROOT / 'data_all/industry/jrc_idees_2023'` | `store` |  |
| `--source-root` | `argparse default` | `store` |  |
| `--download` | `True` | `argparse.BooleanOptionalAction` |  |
| `--refresh` | `argparse default` | `'store_true'` |  |
| `--efuels` | `False` | `argparse.BooleanOptionalAction` |  |
| `--electricity-case` | `'conservative'` | `('conservative', 'technical_2050')` |  |
| `--base-year` | `2020` | `store` |  |
| `--zone-weights` | `argparse default` | `store` |  |
| `--regional-allocation` | `'require-weights'` | `('require-weights', 'equal')` |  |
| `--selected-sectors` | `'all'` | `store` |  |
| `--waste-allocation` | `'sector-blend'` | `('strict', 'sector-blend')` |  |

## transport/script/generate_transport_inputs_standalone.py

| Option | Default | Choices / action | Help |
|---|---|---|---|
| `--countries` | `parse_countries('HR')` | `store` |  |
| `--nuts3` | `argparse default` | `store` |  |
| `--national-dir` | `argparse default` | `store` |  |
| `--pbf-dir` | `argparse default` | `store` |  |
| `--oil-raster` | `argparse default` | `store` |  |
| `--el-raster` | `argparse default` | `store` |  |
| `--zone-map` | `argparse default` | `store` |  |
| `--out-root` | `SCRIPT_DIR / 'outputs_transport'` | `store` |  |
| `--data-dir` | `DEFAULT_DATA_DIR` | `store` |  |
| `--curves-dir` | `argparse default` | `store` |  |
| `--refresh-sources` | `argparse default` | `'store_true'` |  |
| `--efuels` | `False` | `argparse.BooleanOptionalAction` | 'Also generate transport_ICE_prim. Without this flag only transport_all is written.' |
| `--metric-crs` | `'EPSG:3035'` | `store` |  |
| `--skip-allocation` | `argparse default` | `'store_true'` | 'Aggregate existing *_NUTS3.csv files without repeating geospatial allocation.' |

## heating/generate_heating_inputs_standalone.py

| Option | Default | Choices / action | Help |
|---|---|---|---|
| `--countries` | `parse_countries('HR')` | `store` |  |
| `--source-year` | `2021` | `store` |  |
| `--efuels` | `False` | `argparse.BooleanOptionalAction` |  |
| `--model-year` | `YEAR` | `store` |  |
| `--zone-map` | `argparse default` | `store` |  |
| `--out-root` | `SCRIPT_DIR / 'outputs_heating'` | `store` |  |
| `--data-dir` | `SCRIPT_DIR / 'heating_data'` | `store` |  |
| `--raw-output-root` | `SCRIPT_DIR / 'generated_nuts3_heating'` | `store` |  |
| `--skip-raw-generation` | `argparse default` | `'store_true'` | 'Only aggregate existing raw outputs supplied with --input-root.' |
| `--input-root` | `SCRIPT_DIR` | `store` |  |
| `--refresh-sources` | `argparse default` | `'store_true'` |  |
| `--rebuild-raw` | `argparse default` | `'store_true'` |  |
| `--accept-population-terms` | `argparse default` | `'store_true'` | 'Confirm acceptance of the Eurostat/GISCO population-grid terms.' |
| `--nuts3-geojson` | `argparse default` | `store` |  |
| `--population-tif` | `argparse default` | `store` |  |
| `--era5` | `argparse default` | `store` | 'Existing ERA5/ERA5-Land NetCDF.' |
| `--temperature-source` | `'open-meteo'` | `['open-meteo', 'cds-netcdf']` | 'Temperature source when --era5 is not supplied: cached Open-Meteo ERA5-Land sampled-point series (default) or a CDS NetCDF download.' |
| `--eigl-dir` | `argparse default` | `store` |  |
| `--hotmaps-dh-tif` | `argparse default` | `store` |  |
| `--idees-root` | `argparse default` | `store` |  |
| `--powerplants-csv` | `argparse default` | `store` |  |
| `--weather-points` | `8` | `[8]` | 'Population-weighted random grid samples per NUTS3 region (paper method: 8)' |
| `--weather-seed` | `0` | `store` | 'Reproducible random sampling seed' |
| `--dh-chp-lambda` | `0.9` | `store` | 'DH spatial-weight blend: 0=Hotmaps only, 1=CHP only (default: 0.9).' |

## power/generators/generate_genco_power_sector.py

| Option | Default | Choices / action | Help |
|---|---|---|---|
| `--mode` | `'raw'` | `['raw', 'built']` |  |
| `--built-dir` | `None` | `store` |  |
| `--out` | `DEFAULT_OUT` | `store` |  |
| `--countries` | `None` | `store` | 'Comma-separated ISO2 list, e.g. "HR,SI,IT".' |
| `--include-country-name-files` | `argparse default` | `'store_true'` |  |
| `--keep-source-file` | `argparse default` | `'store_true'` |  |
| `--summary` | `argparse default` | `'store_true'` |  |
| `--output-format` | `'sdewes18'` | `['sdewes18', 'detailed']` |  |
| `--rebuild-built` | `argparse default` | `'store_true'` | 'Deprecated alias for --mode raw.' |
| `--powerplants` | `DEFAULT_POWERPLANTS` | `store` |  |
| `--jrc-hydro` | `DEFAULT_HYDRO` | `store` |  |
| `--template-genco` | `None` | `store` |  |
| `--hr-defaults-xlsx` | `None` | `store` |  |
| `--nuts3-geojson` | `DEFAULT_NUTS3` | `store` |  |
| `--zone-mode` | `'country1'` | `['country1', 'country']` |  |
| `--download-sources` | `True` | `argparse.BooleanOptionalAction` |  |
| `--refresh-sources` | `argparse default` | `'store_true'` |  |
| `--clean-built-dir` | `True` | `argparse.BooleanOptionalAction` |  |
| `--powerplants-url` | `POWERPLANTS_URL` | `store` |  |
| `--jrc-hydro-url` | `JRC_HYDRO_URL` | `store` |  |
| `--nuts3-url` | `NUTS3_URL` | `store` |  |

## power/generators/build_genco_union_plus_template_defaults_all.py

| Option | Default | Choices / action | Help |
|---|---|---|---|
| `--powerplants` | `argparse default` | `store` |  |
| `--jrc-hydro` | `argparse default` | `store` |  |
| `--template-genco` | `argparse default` | `store` |  |
| `--hr-defaults-xlsx` | `argparse default` | `store` |  |
| `--out-dir` | `argparse default` | `store` |  |
| `--powerplants-country-col` | `'Country'` | `store` |  |
| `--powerplants-fuel-col` | `'Fueltype'` | `store` |  |
| `--powerplants-tech-col` | `'Technology'` | `store` |  |
| `--powerplants-name-col` | `'Name'` | `store` |  |
| `--powerplants-cap-col` | `'Capacity'` | `store` |  |
| `--hydro-country-col` | `'country_code'` | `store` |  |
| `--hydro-name-col` | `'name'` | `store` |  |
| `--hydro-cap-col` | `'capacity_mw'` | `store` |  |
| `--hydro-type-col` | `'type'` | `store` |  |
| `--zone-mode` | `'country1'` | `['country1', 'country']` |  |
| `--countries` | `'auto'` | `store` |  |
| `--decom-start-existing-cap` | `20.0` | `store` |  |
| `--life-time` | `25.0` | `store` |  |
| `--decom-start-new` | `25.0` | `store` |  |
| `--nuts3-geojson` | `argparse default` | `store` |  |
| `--nuts3-id-col` | `'NUTS_ID'` | `store` |  |
| `--nuts3-level-col` | `'LEVL_CODE'` | `store` |  |
| `--nuts3-level` | `3` | `store` |  |
| `--nuts3-out-col` | `'NUTS3'` | `store` |  |

## power/hydro/generate_hydro_inputs_standalone.py

| Option | Default | Choices / action | Help |
|---|---|---|---|
| `--year` | `2020` | `store` |  |
| `--countries` | `argparse default` | `store` |  |
| `--detailed-genco` | `argparse default` | `store` |  |
| `--aggregated-genco` | `argparse default` | `store` |  |
| `--aggregation-schema` | `argparse default` | `store` |  |
| `--profiles` | `DEFAULT_BULK / 'outputs/profiles/runoff_shapes_2020.npz'` | `store` |  |
| `--hydro-units` | `DEFAULT_BULK / 'outputs/dispaset/hydro_units.csv'` | `store` |  |
| `--plants` | `DEFAULT_BULK / 'data/plants/jrc-hydro-power-plant-database.csv'` | `store` |  |
| `--outdir` | `argparse default` | `store` |  |
| `--max-match-distance-km` | `20.0` | `store` |  |
| `--output-level` | `'aggregated'` | `('aggregated', 'individual', 'both')` | 'Write zone-aggregated curves, individual-plant curves, or both.' |

## power/demand/generate_electricity_demand_standalone.py

| Option | Default | Choices / action | Help |
|---|---|---|---|
| `--countries` | `argparse default` | `store` |  |
| `--year` | `argparse default` | `store` |  |
| `--out-dir` | `argparse default` | `store` |  |
| `--cache-dir` | `argparse default` | `store` |  |
| `--weights-dir` | `DEFAULT_WEIGHTS` | `store` |  |
| `--zone-map` | `argparse default` | `store` |  |
| `--token` | `argparse default` | `store` | 'ENTSO-E API token; preferably set ENTSOE_API_TOKEN instead.' |
| `--refresh` | `argparse default` | `'store_true'` |  |

## power/VRES_distributions/build_vre_capacity_weighted_cf_from_schema_openmeteo_weighted.py

| Option | Default | Choices / action | Help |
|---|---|---|---|
| `--schema` | `argparse default` | `store` | 'Schema CSV (genco_*_schema.csv)' |
| `--out-dir` | `argparse default` | `store` |  |
| `--country` | `'HR'` | `store` | 'ISO2 (matches schema System). Default HR' |
| `--date-from` | `argparse default` | `store` | 'YYYY-MM-DD' |
| `--date-to` | `argparse default` | `store` | 'YYYY-MM-DD' |
| `--timezone` | `'UTC'` | `store` | 'Open-Meteo timezone (default UTC)' |
| `--unit-column` | `None` | `store` | 'Schema unit column (new_unit_name or old_unit_name)' |
| `--output-suffix` | `''` | `store` | 'Suffix added before .csv, e.g. _individual' |
| `--cache-dir` | `None` | `store` | 'Persistent weather-response cache' |
| `--weather-source` | `'openmeteo'` | `('openmeteo', 'renewables-ninja')` |  |
| `--ninja-token` | `os.environ.get('RENEWABLES_NINJA_TOKEN')` | `store` |  |
| `--ninja-dataset` | `'merra2'` | `store` |  |
| `--irena-xlsx` | `None` | `store` | 'IRENA_Statistics_Extract_2025H2.xlsx' |
| `--irena-year` | `None` | `store` | 'Year to use (default from --date-from)' |
| `--calibrate` | `argparse default` | `'store_true'` | 'Calibrate national annual CF to IRENA' |
| `--pv-ghi-ref` | `1000.0` | `store` | 'W/m2 giving CF=1 for PV proxy' |
| `--wind-cut-in` | `3.0` | `store` |  |
| `--wind-rated` | `12.0` | `store` |  |
| `--wind-cut-out` | `25.0` | `store` |  |
| `--sleep-s` | `0.0` | `store` | 'Optional delay after a new download; default uses counted request budgets only' |
| `--max-retries` | `8` | `store` |  |
| `--openmeteo-max-wait` | `DEFAULT_MAX_WAIT` | `store` | 'Maximum local-estimate pause in seconds (0: no cap); HTTP 429 retries continue until success or Stop' |
| `--verbose` | `argparse default` | `'store_true'` |  |
