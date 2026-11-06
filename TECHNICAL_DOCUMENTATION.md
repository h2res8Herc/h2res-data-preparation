# H2RES Standalone Input Preparation — Technical Documentation

For the expanded preparation and model documentation, use [docs/README.md](docs/README.md).
It includes the current source-derived equation/configuration index, complete schema
inventories and the reference register; this file remains the shorter legacy technical guide.

## 1. Architecture

### Optional H2RES-refactored CSV contract

`refactored_input_export.py` converts a completed native bundle to a separate `data_refactored` case and archive. `refactored_reference/contract.json` captures the supplied refactored model's example headers and reader fingerprints without its illustrative Chile values. Unit, bus, annual cost and full-calendar checks run before atomic publication. `refactored_case_loader.py` can additionally exercise the actual separate model reader and all sector data-preparation APIs on every year and all assets. It performs no solve. See [REFACTORED_EXPORT](docs/REFACTORED_EXPORT.html) for accounting, scenario adaptations and unrepresented legacy constraints.

### H2RES 1 November 2026 contract

`h2res_input_schema.py` defines the common 8760-hour calendar, current industry
identifiers, regular-mode fuel mapping, capture defaults, and annual equipment
limits for 2025–2050. Existing annual values are preserved. Zero blocks new
capacity; blank limits remain unrestricted, subject to the model's scalar
fallback. Negative, infinite, or non-numeric limits are rejected.

`model_input_bundle.py` snapshots the supplied model's canonical live files
into `model_reference/data`, records source/reader hashes, and assembles
`outputs_all/model_inputs/data`. It selects the six regular/category/complex
technology families and the current category/complex electricity variants by the
same naming rules as `main.py`. No combined category/complex mode is offered.

Generated sector files use these native interfaces:

| Input | Contract |
|---|---|
| `generators.csv` | Existing GENCO columns, including `System`, `Zone`, `STOCapacityGWh` |
| `electricity_demand.csv` | `period,Power,System,Zone`; Power in MW |
| `renewable_availability.csv` | `period` plus matching VRE/ROR generator names; fractions |
| `hydro_inflows.csv` | `period` plus matching HDAM/HPHS generator names; existing capacity-normalized inflow convention |
| `industry_heat.csv` | `period,System,zone` plus sector useful-energy demands, including NON_HEAT |
| `industry_category_profiles.csv` | Separate `Industry[category]` columns using exact reader identifiers |
| `Industry_data` | Separate `Industry` and `category`, capture/fossil fields, annual investment columns |
| `industry_electricity.csv` | `period` plus globally unique model zones; baseline electricity in MWh/hour |
| `transport_demand.csv` | `period,zone,System` plus sector activity shares normalized over 8760 hours |
| `transport_profiles.csv` | `period,zone,System` plus per-technology plug-in availability fractions |
| `heating_individual.csv`, `heating_district.csv` | `period` plus model zone names, including multi-country runs |
| `heating_electricity.csv` | Baseline electric-heater and heat-pump final electricity from the raw IDEES tables |

Timestamped leap years lose February 29, rather than the final 24 hours of
December. All bundled hourly data use periods 1–8760. The electricity generator
also retains its dated diagnostic CSVs. Legacy process-heat-only industry
exports remain separate from the model's full useful-energy demand.

The selected technology workbook comes from the supplied model reference.
Replacement writes only worksheet XML for the changed sheets, preserving
all other workbook members byte for byte, including Excel formula caches.
Current industry equipment assumptions, detailed/remainder selection,
heat-pump candidates, capture settings, and fuel ceilings come from the
reference. The simple-industry remainder is recalculated numerically from
excluded regenerated services, weighted by their annual demand, to avoid
retaining stale cached pooling formulas.

Worksheet patching identifies `sheetData` by its spreadsheet namespace and local
name. It accepts default namespaces, prefixes such as `ns0:sheetData`, and empty
self-closing data elements. Replacement cells carry their namespace context;
worksheet dimensions and structured-table ranges are updated together. This
prevents valid prefixed sheets such as `tech_cost_years` from failing regional
default expansion. Unrelated workbook parts and cached formulas remain intact.

After applying the 5 November 2026 Excel export fix, an interrupted export can be
retried with **Data task: export existing outputs**, using the same country,
output directory and model options. This XML compatibility fix does not require
downloading sources or recalculating already prepared sector data. See the
[current native-format guide](docs/MODEL_DATA_2_11_2026.md) for the 2 November model.

Other policy, cost, network, process-emission and investment-curve sheets
retain their reference values. The complex workflow parses country-specific
JRC-IDEES-2023 process trees using the supplied industry handoff's pure methods;
it does not infer process activities from temperature categories. The reference
and extracted handoff remain intact. All 11 sectors are generated. The exported
launcher reads the explicit generated sector selection from
`complex_generation.json` rather than assuming the source model's NMM default.
Bundle copies remove exact duplicate transport-demand records, including
the supplied repeated HR1 year, and record that repair in their manifest.
Conflicting hourly records fail validation. Small historical availability
factors above one in retained reference data are reported as warnings;
newly generated factors above one are errors.

Transport bundling retains the current workbook's paid conversion/alternative
engine rows and `compat_*` metadata, with zero initial stock for derived rows.
Primary-fuel mappings, including e-petrol and marine pilot-fuel requirements,
come from the current reference. Their CAPEX remains in the unchanged cost
sheets. This lets the model load its persisted compatibility constraints and
inherit each derived technology's parent availability profile.

`validation.json` checks active-zone and hourly-key coverage, matching power
profiles, transport columns, industry categories, process-workbook structure,
and annual investment values. This is an input coverage check; full scenario
feasibility still depends on costs, policies and network assumptions for the
chosen geography. `validate_model_inputs.py --read-with-model MODEL_DIRECTORY`
adds the actual model reader, using its current flags and local bundle data,
without building or solving an optimization problem.

Regression checks: `python -m unittest discover -s tests -v`.
Offline interface smoke test: `python tests/smoke_reference_export.py`.
The smoke test writes to `validation/generated_smoke` and does not replace
the delivered baseline bundle or represent a fresh statistical calibration.

`generate_all_sector_inputs.py` is the orchestration entry point. It creates a
shared NUTS3-to-model-zone mapping and calls the sector generators:

```text
GUI / command line
        |
generate_all_sector_inputs.py
        |
        +-- power generators and aggregation
        |     +-- hydro profile mapping/aggregation
        |     +-- wind/solar profile preparation
        +-- industry standalone generator
        +-- transport standalone generator
        +-- heating standalone generator
```

`h2res_input_gui.py` is a thin Tkinter client. It does not reproduce model
logic: it validates selections, constructs runner arguments, launches the same
CLI in a worker thread and streams combined stdout/stderr to the log window.

## 2. Spatial processing

### Scenario configuration and model adapter

`scenario_config.resolve_scenario` merges optional JSON with CLI settings.
The default reference path makes no scenario edits. Explicit planning years
replace `policy.xlsx/setup` and `policy_efuel.xlsx/setup`, retaining their
first-row temporal controls. The RES preset edits active systems' RPS curves
to reach 1 at the modeled target year, using reference starting shares or an
explicit user assumption. Available cost years bound the planning horizon.

The investment multiplier affects annual limits in `cap_inv_lim`, equipment
`max_inv_period*`/capture fields, `max_cap_period`, and transport year columns.
It does not scale CAPEX, existing capacity, total maximum capacity or demand.
Blank limits remain unrestricted. JSON overrides select a sheet, column, row
filters and optional years; unmatched filters and unknown columns are errors.
Only the selected technology workbook is edited. Complex equipment/capture
limits are scaled when selected, without regenerating its process calibration.

`run_model_scenario.py` evaluates the supplied model with its industry/e-fuel
flags set to the exported selection and its data paths redirected to the
bundle. Its in-memory AST adaptation wraps `exec_script`. After the supported
builder returns, `scenario_runtime.add_renewable_constraints` adds endpoint
origin restrictions before the CAPEX/objective/solve script runs. A guard
refuses to solve if the adapter was not attached to the current model.
The source model files are never patched. Existing named result directories
are rejected rather than overwritten. The default launcher action loads data
only; `--solve` explicitly enables the normal optimization workflow.

Whole-energy mode requires the heating, industry/transport and e-fuel branches.
Its endpoint rows restrict non-renewable power/CHP output, fossil boilers,
industrial fuel/equipment use, transport fuels, fossil reforming/refining,
unverified external energy supply and external routes disguised as internal
trade. Nuclear is non-renewable even with zero direct combustion CO2. Material
carriers are exempt. Stored energy without a provenance tracer is cleared at
the target-year boundary; later internally renewable stocks may carry. Native
process emissions and carbon budgets remain separate policies. Unsupported
fuel labels fail classification rather than being silently treated as green.

The native RPS alone is insufficient: its domestic generation accounting does
not establish the origin of heating, industrial fuels, mobility or imports.
The conservative endpoint restrictions establish origin explicitly, at the
cost of potentially limiting otherwise certifiable imported/stored energy.
No claim of national scenario feasibility is made from input validation.

`tests/test_scenario.py` covers scenario parsing, policy curves, horizon controls,
investment semantics and launcher injection. `tests/verify_scenario_constraints.py`
uses small licensed Gurobi LPs to test feasible renewable supply, rejection of
fossil-only terminal supply, pre-target operation, trade and boundary stocks.
Its optional `--model-root MODEL --bundle BUNDLE` integration creates native
variables on a two-period sample and checks the adapter against their actual
indices, without solving the national model.

All sector calculations start at NUTS3. Built-in mappings truncate/aggregate
NUTS codes to NUTS2 or NUTS1, map to country, or apply a user CSV. Power GENCO
aggregation groups compatible units within the resulting zone and technology.
Capacities and storage powers are summed; efficiencies, costs and operational
parameters use capacity-weighted aggregation where appropriate. A schema maps
every original `old_unit_name` to its `new_unit_name`.

In individual mode, zone assignment still changes to the requested model zone,
but unit rows are retained one-to-one. Both mode writes both schemas and tables.

## 3. Hydro

### Electricity-demand construction

The demand module requests ENTSO-E Actual Total Load (`documentType=A65`,
`processType=A16`) month by month for the user-selected year and national/control
area. Fifteen- and thirty-minute observations are converted to hourly mean MW,
while simultaneous component series are summed. Short gaps are interpolated and
cached XML responses reused.

Regional allocation uses normalized NUTS3 weights calculated from the official
JRC EIGL `electricity_tot_demand_2019.tif` layer. The EIGL year determines only
the spatial shares, not the load magnitude. Every hour is reconciled exactly to
ENTSO-E national load and then aggregated through the common model-zone map.
The token is read from `ENTSOE_API_TOKEN` and is never written to outputs or GUI
settings. This portable method does not use the older experimental neural
network or per-NUTS3 weather requests.

Runtime hydro processing consumes packaged, precomputed plant runoff shapes.
The expensive ERA5-Land/HydroBASINS derivation is therefore outside normal
model preparation.

- Missing or non-positive plant capacity: plant is excluded.
- HROR: runoff shape is scaled to annual generation, capped by capacity and
  exported as an availability factor in `[0,1]`.
- HDAM: runoff is scaled using annual generation and discharge efficiency and
  expressed relative to turbine capacity.
- HPHS without natural inflow: treated as closed-loop with zero natural inflow.
- Multiple GENCO components matched to one JRC hydro complex: annual generation
  is divided by component MW share, preserving the complex total without
  duplicating inflow.
- Zonal curves: plant curves are weighted by plant MW capacity.

The generator verifies that aggregated hydro curve names equal the hydro GENCO
unit names. Mapping and quality CSVs expose plant IDs, distances, capacities,
annual equivalent hours and aggregation membership.

## 4. Wind and solar

The VRE preparer reads the GENCO aggregation schema, retaining plant latitude,
longitude, capacity, country, technology and destination unit.

Supported technology codes are PHOT, WTON and WTOF. Two weather backends exist:

- Open-Meteo archive: shortwave radiation and wind speed; proxy PV and turbine
  power curves convert weather into hourly capacity factors.
- Renewables.ninja: site PV/wind simulation using the token supplied through
  `RENEWABLES_NINJA_TOKEN`.

Each weather response is hashed by request parameters and stored in the cache.
Both output mode therefore reuses identical site downloads.

IRENA calibration derives target annual CF as:

```text
CF = annual generation [GWh] * 1000 / (installed capacity [MW] * hours)
```

A technology-specific scalar is solved against the capacity-weighted national
mean with clipping to `[0,1]`. Scaling occurs before zonal aggregation, so the
hourly and regional pattern is retained. Final zonal series are capacity-
weighted plant profiles.

## 5. Industry, transport and heating

Industry produces sector technology tables and normalized distributions using
the standalone resource pipeline. Transport produces `transport_all` and,
where e-fuels are enabled, the compatible `transport_ICE_prim` representation.
Regular/category industry generation writes regular and e-fuel-compatible variants at both sector
and process-heat-category resolution. The global e-fuel option determines which
variant is written as canonical `Industry_data`.
Complex generation instead writes the selected regular/e-fuel and electricity
case directly as the native `industry_complex*.xlsx`, plus an adapted technology
workbook, profiles and aggregate baselines. `industry/methods/METHOD_PROVENANCE.json`
records source-script hashes and the narrowly scoped local parser extension.
No archived installer or migration is run. Source ZIP extraction writes only
the three explicitly named country workbooks, and uncached numeric source
formulas are rejected.

Source reconciliation covers useful/final energy, combustion CO2 and historical
process CO2 by sector. Observed useful/final ratios above one remain intact.
HP efficiencies and unobserved substitutions are separate assumptions. Regional
allocation conserves energy, emissions and physical output; output indices are
kept as indices and their intensities apportioned instead. Finite national
build budgets are apportioned, retaining zeros and blanks. A shared cross-country
zone uses country-prefixed branch/component keys to avoid merging unlike
activity indices. New component costs copy generic technology columns while
preserving existing formulas, caches and other workbook members.

Exact biomass/waste splits require the source method's single fossil-waste
class proof. The default sector-blend extension uses observed sector fossil
waste energy/CO2 to derive a weighted factor and explicitly assumes that mix
across processes; strict mode rejects ambiguous splits. It does not alter
observed total energy or CO2. The exact HR ammonia exception is guarded by
country, branch, year and amount. Other-country process CO2 is preserved until
country-specific evidence supports reclassification under the H2-fed convention.
Hourly shapes come from the matching country reference where available, then
are normalized to source energy; a flat fallback is recorded otherwise. They
are not new measured process-level hourly profiles. Future activity is held at
the last observation, not forecast automatically.

`tests/test_complex_industry.py` independently checks raw JRC roots, HR calibration,
regional units, assumptions and Excel formula-cache preservation.
`tests/verify_complex_industry_integration.py` calls the actual target model's
process adapter on a small hour sample and verifies annual energy closure.
These checks do not solve the optimization or establish complete non-industry
input coverage for a newly selected country.
Heating produces individual and district-heating technology tables for
electric, fuel-boiler and solar technologies, plus normalized individual/DH
heat-demand curves. Public source files are cached in `data_all`.

Heating temperature can come from Open-Meteo or an existing CDS/ERA5 NetCDF.
The packaged population raster supports population-weighted spatial allocation.

## 6. Primary CLI options

| Option | Values | Purpose |
|---|---|---|
| `--countries` | ISO2 CSV | Countries to process |
| `--sectors` | sector CSV | Selected sector generators |
| `--spatial-level` | nuts3/nuts2/nuts1/country/custom | Shared model geography |
| `--power-output-level` | aggregated/individual/both | GENCO resolution |
| `--hydro-output-level` | match-power/aggregated/individual/both | Hydro resolution |
| `--vre-weather-source` | openmeteo/renewables-ninja | VRE backend |
| `--vre-calibrate` | Boolean optional | IRENA calibration |
| `--skip-vre-profiles` | flag | Avoid weather requests |
| `--skip-hydro-profiles` | flag | Avoid hydro export |
| `--electricity-demand-year` | year | ENTSO-E Actual Total Load year |
| `--skip-electricity-demand` | flag | Do not request or generate load profiles |

Use `python generate_all_sector_inputs.py --help` for the complete interface.

For custom geography, see [the mapping guide and editable examples](docs/CUSTOM_ZONES.html).
The runner validates the map against the selected NUTS boundary vintage before
starting sector generation. It rejects blank offshore membership, unknown
region IDs, repeated assignments, ambiguous zone names and incomplete national
coverage. Different numbers of zones per country are supported. A partial
country or a synthetic zero-demand offshore bus is not yet a supported custom
map; the design files are labeled accordingly.

## 7. Portability and dependencies

The package uses paths relative to its extracted directory. Required static
power, hydro, NUTS, population and IRENA data are bundled. Full raw European
weather is not bundled; wind/solar and heating weather is downloaded and cached
unless supplied locally.

Python packages: numpy, pandas, openpyxl, geopandas, shapely, rasterio, xarray,
netCDF4, pyogrio and requests. The GUI itself only requires standard Tkinter,
which is included in standard Windows Python and Anaconda installations.

## 8. Validation

The native 2 November 2026 export additionally checks industry aggregation against
its source table, exact generator names across costs and regional investment
limits, complete annual financial keys, and active regional network coverage.
`simple_industry` pools only fully excluded industry services and can correctly
be empty when all services are detailed. Pooling conserves baseline capacity,
useful heat, fuel input and combustion emissions. National technology investment
budgets are split over the matching generated plants by existing capacity and
are not repeated in every region. Cost, investment and maintenance defaults are
traced in `generator_input_links.json` outside the native `data` directory.

Missing regional network connections use explicit virtual national-exchange
defaults and are recorded in `network_input_assumptions.json`. These are not
observations of physical lines. External transfer envelopes retain their
national totals. See [native data documentation](docs/MODEL_DATA_2_11_2026.md)
for the assumptions and generated launcher, which selects the recorded
variants in a separate H2RES installation.

The portable build is validated by clean extraction and a Croatian power run in
both mode with network-dependent VRE disabled. The test checks 116 individual
GENCO rows, 46 aggregated NUTS3 units, a complete 116-row identity schema and
8,784-hour aggregated/individual hydro exports. VRE retrieval and IRENA
calibration are smoke-tested on a Croatian site, including persistent caching.
