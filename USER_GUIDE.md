# Energy Data Sourcing and Preparation — User Guide

The complete, version-specific documentation library is in [docs/README.md](docs/README.md),
including separate preparation/model manuals, equations, input schemas, assumptions,
source references, BibTeX and a printable HTML edition.

## Starting the application

For the bus-based H2RES-refactored model (the version with `data_chile`), enable **Also export H2RES-refactored CSV case** on **Output format**. It creates `data_refactored` and a separate ZIP. See [the refactored export guide](docs/REFACTORED_EXPORT.html) for its native industry/transport representations and validation.

This is a standalone tool for internet data sourcing and input preparation.
It downloads and caches source observations, prepares sector tables and profiles,
and exports CSV/Excel inputs. Running H2RES is a separate workflow.

On Windows, extract the portable archive and double-click `START_DATA_PREPARATION.bat`.
You can also start it from Anaconda Prompt or PowerShell:

```text
python data_preparation_gui.py
```

The GUI shows the exact command it will execute. Output from the generator is
streamed into the Run log.

The current output format matches `H2RES_2.11.2026_novi/data`, including its
43-file layout and `sources`/`variants` subfolders. See the
[current model-data guide](docs/MODEL_DATA_2_11_2026.md).
The usable model inputs are directly in **`<Output directory>/data`**.
By default, all native `flex_tech` variants and complex-industry companions
are populated for the prepared country and geography. An additional delivery
under `model_inputs/h2res_inputs` contains these files, validation and a ZIP. See the
[combined model-input output guide](docs/MODEL_READY_OUTPUTS.md) for its layout,
settings and offline export commands.

The combined H2RES input package is published only after input validation
passes. Missing or inconsistent required data stop the export and preserve the
previous valid package; the run log and `model_export_failure.json` explain
what must be completed.

Use **Output format** to select the native input representation and portable
technology templates. Use **Input assumptions** for future years, build limits
and renewable targets to write into the prepared files. Click **Source and
prepare data** to start. The former `START_H2RES_GUI.bat` remains a compatible
shortcut to this same preparation tool.

If startup fails, read `DATA_PREPARATION_STARTUP.log`. The launcher checks Python
and its base preparation dependencies before opening the interface. To check
startup from PowerShell without opening a window:

```text
.\START_DATA_PREPARATION.bat -Check
```

The source pipelines need the packages in `requirements.txt`, including spatial
allocation (`geopandas`, `shapely`, `pyproj`, `pyogrio`), raster allocation and
weather-file support. Install them using the **same Python** shown in the startup
log. For the installed Python 3.12 on this machine, run in PowerShell:

```powershell
& "C:\Users\lukah\AppData\Local\Programs\Python\Python312\python.exe" -m pip install -r requirements.txt
```

The tool checks dependencies for the selected sectors before downloading or
changing prepared outputs. `-Check` verifies the default four-sector stack.
The optional CDS download backend additionally needs `requirements-cds.txt`;
the default Open-Meteo backend does not need `cdsapi`.

## Scenario defaults and a 100% renewable target

The **Input assumptions** tab offers `reference` (retain existing assumptions) and
`res100` (100% renewable energy by a selected target year). The default target
scope is the **whole energy system**, including power, heating, industry and
transport. Choosing that preset enables the e-fuel option for renewable fuel
pathways. Complex-industry source calibration remains separate.

Choose planning years, for example `2025,2030,2035,2040,2045,2050`. Years must be
increasing, equally spaced, covered by the input cost data, and include the
renewable target year. The statistical/weather data years remain independent.
Blank planning years retain the reference horizon. The supplied reference
currently supports 2020–2050; later years require additional data, rather than
automatic extrapolation.

The annual investment multiplier defaults to **1**, retaining existing build
limits. A value of 2 doubles finite annual limits; 0 sets finite limits to zero.
Blank/unrestricted limits stay blank, and existing installed capacities and
total-capacity ceilings are preserved. Runtime investment multipliers already
in the supplied model policy still apply. Individual limits can be overridden
through the optional scenario JSON using the workbook's native units.

An editable starting preset is `scenario_defaults_res100_2050.json`. To prepare
it offline from the supplied baseline:

```text
python generate_all_sector_inputs.py --import-model-inputs --efuels --scenario-config scenario_defaults_res100_2050.json --out-root outputs_res100 --require-model-ready
```

The same options work with normal generation and `--export-only`. CLI values
override JSON. You can also specify `--start-year 2025 --end-year 2050 --year-step 5`
instead of `--planning-years`.

```json
{
  "preset": "res100",
  "scope": "all-energy",
  "years": [2025, 2030, 2035, 2040, 2045, 2050],
  "target_year": 2050,
  "investment_multiplier": 1,
  "investment_overrides": [
    {"sheet": "cap_inv_lim", "column": "HR_Wind", "value": 1000,
     "where": {"zone": "HR1"}, "years": [2030, 2035, 2040, 2045, 2050]},
    {"sheet": "Industry_data", "column": "max_inv_period", "value": 1500,
     "where": {"zone": "HR1", "Industry": "Chemical_petrochemical"},
     "years": [2030, 2035, 2040, 2045, 2050]}
  ]
}
```

These are illustrative scenario assumptions, not country-specific forecasts.
The initial electricity renewable share comes from the reference RPS curve,
unless `--renewable-start-share` supplies a fraction from 0 to 1. New systems
without a reference RPS row require that explicit assumption.

The preparation tool records targets and assumptions in the exported files;
it does not execute a model or determine whether a target is feasible. The
optional integration files (`scenario.json`, `run_model_scenario.py` and
`scenario_runtime.py`) describe how the separate H2RES environment can consume
the assumptions. Copying data files alone does not add whole-energy policy
constraints to an independently configured model.

The full-system preset excludes fossil and nuclear energy at and after the
target year, including fossil use with carbon capture. Unverified outside
energy imports are disabled at that point; trade between active modeled zones
remains available. Generic stored energy has no origin tracer, so affected
stores must be empty at the target-year boundary, after which renewable stocks
can carry forward. Material inputs such as CO2 and nitrogen are separate from
energy. Mixed fossil-waste industrial equipment is excluded at the endpoint.
These are explicit, conservative origin assumptions. Electricity follows a
linear RPS trajectory; earlier non-electric transitions are optimized.

A renewable-energy target is distinct from a net-zero emissions target. Existing
carbon budgets and process-emission assumptions are retained. The preset does
not guarantee feasibility: investment ceilings, technology limits, resource
availability, storage boundary conditions and other policies can bind.

## General settings

This package prepares files for **H2RES_1.11.2026**. The **Output format** tab selects
regular industry, temperature categories, or complex processes, and the
conservative/technical-2050 industry electricity case. Categories and complex
industry are alternative modes.

The supplied model inputs are available in `outputs_all/model_inputs/data`.
`model_reference` contains a portable copy of the current live workbooks, CSVs
and archived JRC process sources, with SHA-256 provenance. This portable
template directory lets preparation run without an installed energy model.

Source and prepare inputs using the bundled format templates:

```text
python generate_all_sector_inputs.py --countries HR --spatial-level country --efuels --industry-mode categories
```

Generation needs its usual public data sources and, for ENTSO-E demand, an
API token. The GUI's **Data task** selector offers `generate` and
`export existing outputs`; the latter only repackages previously prepared data.

Each generated run writes the native `data` folder with current model filenames
and all technology alternatives. Prepared sectors use generated observations;
other inputs retain documented model defaults. Missing geography in default
tables is recorded with its donor and assumptions. Missing generated demand or
weather remains an error. Inspect `H2RES_DATA_manifest.json` and
`model_inputs/validation.json` before using the inputs.

```text
python generate_all_sector_inputs.py --export-only --countries HR --sectors industry --efuels --industry-mode categories --require-model-ready
python validate_model_inputs.py --efuels --industry-mode categories
```

Validation checks input file keys and data coverage. `--no-model-export` keeps
the standalone sector outputs without assembling a complete data directory.
Tests using an installed model's reader are separate developer checks.

Complex mode now compiles country process/activity inputs using the supplied
industry handoff and **JRC-IDEES-2023** observations. It covers all 11 industry
sectors by default. The **Industry sources** tab controls source folders,
reference year, sector selection and regional/waste allocation assumptions.
Missing country workbooks are downloaded from the public JRC country archives;
no JRC API token is required. Croatia's archived observations work offline.
Regular/category modes continue to use their separate JRC/SECURES pipeline.

For example, regenerate Croatian complex industry and the whole-energy RES preset:

```text
python generate_all_sector_inputs.py --countries HR --sectors industry --spatial-level country --industry-mode complex --efuels --scenario-config scenario_defaults_res100_2050.json --out-root outputs_complex_HR --require-model-ready
```

Use `--countries HU` for Hungary's actual observations. Generating industry
alone does not provide missing heating, transport or power data for that
country; the complete-bundle validator reports those gaps. Croatia and Hungary
have been checked against the actual model's complex-industry adapter.

JRC process observations are national. Country resolution needs no allocation
file. Regional resolution requires `--industry-zone-weights weights.csv`, with
`country,zone,Industry,weight` columns; weights must cover all selected zones and
sum to one for each country/sector. `Industry=*` supplies a common allocation.
Alternatively, explicitly choose `--industry-regional-allocation equal` for an
equal-weight proxy. Neither method identifies actual plant locations.

The default `--industry-waste-allocation sector-blend` uses exact single-class
fossil-waste evidence where available (including the HR calibration). When
several fossil-waste classes occur, it assumes the observed sector waste blend
applies to each process and records that assumption. `strict` rejects such
ambiguous process splits. Country-specific ammonia emissions are retained;
Croatia's documented reforming exception is never copied to another country.

Review `industry/combined/complex_generation.json`, `source_reconciliation.csv`,
`normalized/` source records and the generated workbook. The observations
preserve source cells and units. Equipment costs/lifetimes/build limits,
substitution ceilings, heat-pump eligibility, hourly shapes and activity held
constant after 2023 remain editable assumptions. For an exact HR1 run,
`reference_calibration_diff.csv` records differences from the handoff.

The exported metadata records the generated sector selection, which can differ
from an independently configured model's NMM-only selection. Select fewer sectors with
`--complex-industry-sectors Non_metallic_minerals`, for example.

- **Countries:** select `ALL` for all 27 supported countries, select one country,
  or enter multiple codes such as `HR,SI`. When using a custom map, this field
  may be left blank to select every country listed in the map. Individual power
  datasets cover some additional European countries, but those are not complete
  all-sector cases.
- **Sectors:** power, industry, transport and/or heating.
- **Spatial level:** NUTS3, NUTS2, NUTS1, country or a custom zone map.
- **Custom zone map:** CSV with `country,nuts3,zone` columns. Add the optional
  `system_new` column to merge countries into a new model system. For example,
  `EE,EE001,Baltics1,Baltics` produces `System=Baltics, Zone=Baltics1`.
  [Custom-zone examples and current limits](docs/CUSTOM_ZONES.html) explain
  the required full-country coverage, mixed aggregation and the proposed
  northern-Italy/offshore configuration. Omitting a region does not currently
  provide supported partial-country exclusion. Offshore zones without a source
  NUTS3 region need a separate generator extension.
- **Output directory:** generated model inputs.
- **Download/cache directory:** reusable downloaded public data.
- **Refresh sources:** downloads fresh source copies instead of using the cache.
- **E-fuels:** selects the e-fuel-compatible transport and industry representations.
  Regular/category industry writes separate regular/e-fuel tables, both with and
  without process-heat categories; this option selects canonical `Industry_data`.
  Complex industry writes the selected native workbook variant.

## Power, hydro, wind and solar

For wind/solar HTTP 429 failures, see the [weather quota and resume instructions](docs/PORTABLE_USER_GUIDE.html).
Retain the same weather cache, leave Refresh sources off, and use Generate after
the provider allowance resets. The downloader honors reset delays and preserves
completed site weather; a provider's daily quota cannot be removed by client code.

### Electricity demand

Power-sector runs generate national and regional hourly electricity demand for
the selected **Electricity-demand year**. Enter an ENTSO-E Transparency Platform
API token in the GUI; it is passed only to the running process and is not stored
in the settings file or command preview. Command-line users can set:

```text
set ENTSOE_API_TOKEN=your_token
python generate_all_sector_inputs.py --countries SI --sectors power --electricity-demand-year 2021
```

Monthly ENTSO-E Actual Total Load responses are cached under
`data_all/entsoe_load`. Packaged 2019 NUTS3 distributions are used only as
normalized spatial weights, so the selected ENTSO-E year determines the hourly
and annual demand magnitude. Use **Skip electricity-demand profiles** or
`--skip-electricity-demand` when this input is not required.

The generated `power/demand` folder contains national load, NUTS3 long-format
demand, selected model-zone long-format demand, and a model-zone wide table.

The year is not restricted to 2020. To download and generate all 27 supported
European country profiles for a chosen year independently of the other sectors:

```text
set ENTSOE_API_TOKEN=your_token
python power\demand\generate_electricity_demand_standalone.py --countries ALL --year 2022 --cache-dir data_all\entsoe_load --out-dir outputs_all\power\demand
```

**GENCO resolution** controls the power-plant table:

- `aggregated`: one capacity-weighted unit per zone/technology grouping.
- `individual`: one row per physical plant.
- `both`: aggregated `GENCO.csv` plus `GENCO_individual.csv`.

**Hydro profile resolution** normally remains `match-power`. It can be
overridden to aggregated, individual or both. HDAM/HPHS curves are written to
`ScaledInflows_<year>*.csv`; HROR curves are written to
`AvailabilityFactors_HROR_<year>*.csv`.

Wind and solar profiles are written below `power/vre/aggregated` and/or
`power/vre/individual`. Open-Meteo is key-free and is the default. To use
Renewables.ninja, set `RENEWABLES_NINJA_TOKEN` before opening the GUI:

```bat
set RENEWABLES_NINJA_TOKEN=your_token
START_H2RES_GUI.bat
```

IRENA calibration adjusts national annual means by technology while preserving
the plant-level hourly and spatial pattern. Weather responses are cached.

## Common configurations

### Individual Croatian plants and individual hydro

- Countries: `HR`
- Sectors: Power only
- GENCO resolution: `individual`
- Hydro profile resolution: `match-power`
- For source-only GENCO/hydro outputs, disable H2RES packaging before skipping wind and solar

### Croatia at NUTS1 with both representations

- Countries: `HR`
- Spatial level: `nuts1`
- GENCO resolution: `both`
- Hydro profile resolution: `match-power`

### Fully offline-safe power run

For source-only outputs, disable H2RES packaging, select Power, enable
**Skip wind and solar profiles**, and use the packaged hydro data. Other
sectors may require their cached/downloadable public sources. Complete H2RES
exports always generate wind/solar profiles, reusing cached site weather when
available. They cannot omit the availability columns required by GENCO.

## Ready-to-use H2RES data folder

The final inputs are directly in **`<Output directory>/data`**, for example
`sve_za_HR/data`. This directory mirrors the current H2RES model's exact native
filenames and subfolders. All native technology variants are populated by
default, including matching industry, transport and e-fuel tables. Supplied
model assumptions fill inputs not sourced online; provenance is recorded outside
`data` in `H2RES_DATA_manifest.json` and the validation package.

See [the native model-data guide](docs/MODEL_DATA_2_11_2026.md) for workbook
selection, defaults, the complete structure and re-exporting cached sources.

## Intermediate output structure

```text
outputs_all/
  power/
    GENCO.csv
    GENCO_individual.csv             (both mode)
    power_inputs.xlsx
    hydro/
    vre/
  industry/
  transport/
  heating/
```

Intermediate mapping schemas beginning with `_` are retained for traceability.

## Troubleshooting

The [2 November bugcheck and recovery note](docs/BUGCHECK_2026_11_02.md)
documents pandas numeric-type fixes, early template checks, protected exports,
country-cache handling and the offline regression/integration results.

- A backtick is a PowerShell continuation character and does not work in
  Anaconda Prompt. The GUI avoids shell-continuation problems entirely.
- If Renewables.ninja reports a missing token, set the environment variable and
  restart the GUI.
- API failures can generally be resumed: completed weather requests remain in
  the cache directory.
- Use **Open output folder** to inspect results and quality reports.
- An older shipping-identifier error mentioning `ICE_MARINE_DOM` or
  `ICE_MARINE_INT` occurs during model-data export. The current preparer maps
  these to the model's `ICE_MARINE_SHORT` and `ICE_MARINE_LONG` names, including
  cached profile columns. Use `--export-only` with the original run settings to
  reuse completed sector results; fresh downloads are not required.
- The **Stop** button terminates the active top-level generator. Already written
  cache and output files are retained.
