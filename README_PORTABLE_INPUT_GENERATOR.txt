ENERGY DATA SOURCING AND PREPARATION
==============================

Contents
--------

Standalone internet data sourcing, caching and CSV/Excel preparation for
H2RES_1.11.2026. This interface prepares files only; running the energy model
is a separate workflow. The current inputs are prepared under
outputs_all/model_inputs/data. See model_inputs/validation.json and USER_GUIDE.md.
The portable model_reference folder includes current costs, policies, annual
investment limits and process sources. The original model directory is read only.

New CLI options: --industry-mode regular|categories|complex,
--industry-electricity-case conservative|technical_2050,
--import-model-inputs, --export-only, --model-root, --model-reference,
--require-model-ready, --no-model-export. These settings are also in the GUI.

Complex industry now compiles JRC-IDEES-2023 country observations using the
supplied industry handoff. Choose complex mode and country spatial resolution,
or supply explicit regional weights. Missing public country archives can be
downloaded automatically. See USER_GUIDE.md for the Industry sources tab,
sector selection, strict/sector-blend waste assumptions and source audits.

h2res_input_schema.py
scenario_config.py
scenario_runtime.py
run_model_scenario.py
scenario_defaults_res100_2050.json
model_input_bundle.py
validate_model_inputs.py
model_reference/manifest.json
generate_all_sector_inputs.py
h2res_input_gui.py
data_preparation_gui.py
START_DATA_PREPARATION.bat
launch_data_preparation.ps1
START_H2RES_GUI.bat
USER_GUIDE.md
TECHNICAL_DOCUMENTATION.md
industry/generate_industry_inputs_standalone.py
industry/generate_complex_industry_inputs.py
industry/complex_sources.py
industry/methods/METHOD_PROVENANCE.json
transport/script/generate_transport_inputs_standalone.py
heating/generate_heating_inputs_standalone.py
power/generators/...
power/hydro/generate_hydro_inputs_standalone.py
power/hydro/precomputed/...                 (Europe-wide 2020 runoff profiles)
ESTAT_OBS-VALUE-T_2021_V2.tiff        (packaged population grid)

Graphical interface
-------------------
Double-click START_DATA_PREPARATION.bat, or run:
python data_preparation_gui.py

START_H2RES_GUI.bat is a compatible shortcut to this same preparation app.
The Output format tab controls the prepared file representation, and Input
assumptions controls future-year tables and policy defaults. There are no
model execution controls.

The launcher automatically detects Python on PATH and in common Anaconda,
Miniconda and standard per-user installation folders. If detection fails, open
Anaconda Prompt in this package folder and run the command above.

If the window does not appear, read DATA_PREPARATION_STARTUP.log, or run
START_DATA_PREPARATION.bat -Check for a check without opening a window.
START_H2RES_GUI_DEBUG.bat also remains available for startup diagnostics.

The GUI exposes sector selection, spatial aggregation, individual/aggregated
power and hydro, wind/solar sources and IRENA calibration, heating inputs,
cache/output folders, command preview and a live run log.

The unified script uses Open-Meteo ERA5-Land centroid series for heating by
default. Hydro uses packaged Europe-wide 2020 ERA5-Land surface plus sub-surface
runoff profiles, so normal model-input generation makes no hydro/CDS API calls.
Other public resources are cached under data_all.

Power runs also generate electricity demand for a user-selected year. Enter an
ENTSO-E Transparency Platform API token in the GUI (the token is not saved), or
set ENTSOE_API_TOKEN for command-line use. Monthly Actual Total Load downloads
are cached. Packaged normalized NUTS3 weights allocate national load to the
selected NUTS/custom model zones. The weights were derived from the official JRC
EIGL electricity_tot_demand_2019 layer; they set spatial shares only.

Run all sectors at NUTS3
------------------------
python generate_all_sector_inputs.py --countries HR

Run all 27 supported countries
------------------------------
python generate_all_sector_inputs.py --countries ALL

Run all sectors at NUTS2
------------------------
python generate_all_sector_inputs.py --countries HR --spatial-level nuts2

Run custom model zones
----------------------
python generate_all_sector_inputs.py --countries HR --spatial-level custom --zone-map custom_zones.csv

Generate only selected sectors
------------------------------
python generate_all_sector_inputs.py --countries HR --sectors power,industry,transport,heating

Generate both aggregated and individual-plant hydro profiles
-------------------------------------------------------------
python generate_all_sector_inputs.py --countries HR --sectors power --hydro-output-level both

Use --hydro-output-level individual to write only individual-plant profile
files. The default is aggregated, preserving the original model workflow.

Power-plant and wind/solar profile resolution
---------------------------------------------
python generate_all_sector_inputs.py --countries HR --sectors power --power-output-level aggregated
python generate_all_sector_inputs.py --countries HR --sectors power --power-output-level individual
python generate_all_sector_inputs.py --countries HR --sectors power --power-output-level both

The selected spatial level (NUTS3 by default, or NUTS2/NUTS1/country/custom)
defines the aggregated power zones. Wind, solar and hydro profiles follow the
same plant/zone selection. Wind and solar curves use cached Open-Meteo weather
and are calibrated by default to national IRENA generation/capacity factors.

Renewables.ninja can be selected as an alternative site-profile backend:
set RENEWABLES_NINJA_TOKEN=your_token
python generate_all_sector_inputs.py --countries HR --sectors power --vre-weather-source renewables-ninja

Use --skip-vre-profiles to generate GENCO and hydro without wind/solar curves,
or --no-vre-calibrate to retain the raw weather-model capacity factors.

Add the e-fuel transport table
------------------------------
python generate_all_sector_inputs.py --countries HR --efuels

The same option selects the e-fuel-compatible canonical industry table. Every
industry run also writes explicit regular and e-fuel variants, with and without
process-heat categories, in Industry_data_*.csv and industry_inputs.xlsx.

Custom zone-map columns
-----------------------
country,nuts3,zone
HR,HR021,Continental
HR,HR022,Continental
HR,HR050,Zagreb

Required Python packages
------------------------
numpy
pandas
openpyxl
geopandas
shapely
rasterio
xarray
netCDF4
pyogrio
requests

Install them, if needed, with:
python -m pip install numpy pandas openpyxl geopandas shapely rasterio xarray netCDF4 pyogrio requests

Notes
-----
ERA5-Land temperature is requested from Open-Meteo for each population-weighted
NUTS3 centroid and cached. The free endpoint is for non-commercial use and is
limited by Open-Meteo's current terms. For offline or commercial workflows,
pass an existing official NetCDF using --era5 PATH.
Downloaded public datasets are cached and are not downloaded again unless
--refresh-sources is supplied.

Power outputs include GENCO.csv plus:
power/hydro/ScaledInflows_2020.csv
power/hydro/AvailabilityFactors_HROR_2020.csv

With --hydro-output-level individual or both:
power/hydro/ScaledInflows_2020_individual.csv
power/hydro/AvailabilityFactors_HROR_2020_individual.csv
power/hydro/hydro_quality_report_individual.csv

Hydro rules:
- plants with missing/non-positive capacity are excluded;
- unclassified HPHS is treated as closed-loop with zero natural inflow;
- ROR profiles are capacity factors constrained to 0..1;
- HDAM inflows are normalized relative to aggregated turbine capacity.

Output is written under outputs_all.
