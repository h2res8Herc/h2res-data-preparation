# Native data output for H2RES_2.11.2026_novi

The current export follows `D:\POSAO\H2RES_2.11.2026_novi\data`. It writes a directly usable **`<output directory>/data` folder**, reproducing the reference's **43 files and three subdirectory paths**. It includes all native technology workbooks, source workbooks and the technical-2050 alternative. The model installation is read as the format reference; generated files are written to the preparation output directory.

## Regional inputs and shared assumptions

The non-eFuel `Industry_data` and `simple_industry` tables in `flex_tech.xlsx`, `flex_tech_categories.xlsx` and `flex_tech_complex_industry.xlsx` exclude `heat` and `waste`, matching the native reference. Their useful-service weights are reassigned proportionally to existing Gas, Coal, Oil, Biomass, Electricity and Hydrogen use **within the same zone, industry and heat category**. Feedstocks and zero-share future equipment receive none of this reassignment. If a category has no supported incumbent, its industry's supported mix in the same zone is used; if that is also empty, gas is the explicit default. Reassignment takes place before category aggregation, so regular and category tables conserve the same fuel quantities.

For the ordinary generators, added capacity equals reassigned useful service divided by recipient efficiency, capacity factor and 8760. Process-derived aggregate capacities already measure useful MW and scale with their useful-service shares. Baseline shares and substitution ceilings are updated together. Hourly total service and regional allocation stay conserved. Historical `industry_electricity.csv` remains the observed electricity subtraction from total grid demand: any electricity introduced by the simplified representation becomes additional modeled industrial electricity use. Reassigning heat or waste is a **model representation assumption**, not a newly observed fuel mix or a promise to conserve historical final-energy consumption or emissions across fuels with different efficiencies and carbon factors.

The separate `industry_complex*.xlsx` process tables retain purchased heat where the complex model explicitly accounts for external steam, including its supply emissions. Their observed process energy and carbon reconciliation is retained. eFuel technology variants retain their native heat/waste representation. Every non-eFuel ordinary table is checked for unsupported heat/waste rows before delivery, including zero-capacity rows. Old prepared industry files must be regenerated using cached downloads before exporting.

Reassignment records are saved beside the prepared industry tables as `Industry_data_regular_fuel_redistribution.csv`, `Industry_data_regular_heat_categories_fuel_redistribution.csv` and `industry_fuel_representation.json`. Complex compilations record their aggregate adaptation in `fuel_redistribution.json` and `complex_generation.json`. These audit files stay outside the native 43-file `data` layout.

File-format validation and regional data quality are separate checks. A workbook that the model can read is not evidence that its county-level quantities were sourced correctly.

For NUTS3 industry, the loader downloads and caches the public **EU ETS/EUTL installation tables, EEA Industrial Emissions Portal site records and JRC EIGL industrial installation inventory**. Installation coordinates, sector codes and industrial activities determine the branch geography. Each selected-year JRC-IDEES national sector, temperature category and fuel total is distributed with that branch's regional shares. Industry is not allocated by population, and regional industrial fuel rasters are not imposed as hard geographic margins. Every national sector/category/fuel total is conserved. The regular/category pipeline receives the selected industry base year too.

These are **modelled regional allocations, not observed factory capacities**. Within each branch the source priority is selected-year ETS verified emissions as an industrial activity proxy, otherwise IED sector facility density, otherwise EIGL sector facility density. Inventories are alternatives rather than quantities added together. Missing branch coverage uses an explicitly flagged all-industrial-site-density assumption. NACE 20/21 covers chemical/petrochemical final consumption; NACE 19 refineries and energy transformation are excluded. Feedstock corrections also update the hourly NON_HEAT/heat categories while preserving total energy. Derived equipment capacity follows `E / (efficiency * capacity_factor * 8760)`.

Regular, category and generated complex industry variants share the same branch weights. `regional_allocation.json` in each country's `01_allocated` folder records sources, hashes, coverage assumptions and conservation; `facility_observations.csv` identifies the installations. `industry/combined/regional_generation.json` binds those allocations to the prepared files, and `regional_branch_weights.csv` carries them into complex variants. Export rejects old regional allocations with unverifiable methods or changed source files. Select `equal` only for an intentional equal-allocation scenario.

Heating uses **eight reproducible inhabited population-grid samples per NUTS3 region**, population-weighted hourly Open-Meteo temperatures, degree hours, Hotmaps heat-density data, JRC residential/tertiary totals, PowerPlantMatching CHP locations and five EIGL residential/tertiary fuel maps, including electricity. Transport reads actual rail, station, port/quay and airport/runway features from country OSM extracts through the Python `osmium` package. Lines and areas are clipped at regional boundaries. Maritime allocation is restricted to GISCO coastal regions; inland maritime demand is zero. The national passenger/freight tables and EIGL oil/electricity road weights remain separate. See [the paper-method audit](PAPER_METHOD_AUDIT.md) for sources, choices not specified numerically in the paper, and source years.

Existing national quantities retained as defaults—such as battery capacity, fuel stocks, ammonia annual demand and finite capacity limits—are distributed over the requested regions using prepared demand shares. Their active regional sums conserve the supplied national default. Industry/heating defaults use the corresponding demand shares where available; other defaults use electricity demand. This is an allocation assumption, not a new observation of those assets. Generated sector quantities retain their sourced allocation. Intrinsic technology values such as efficiency, cost and lifetime remain shared; normalized transport, CO2 and NH3 timing curves may also be identical because annual totals supply their scale. Reference solar thermal availability remains a shared weather assumption. Future investment limits supplied by sector generators remain scenario assumptions.

The validation delivery includes `regional_input_quality.json` alongside its file-format checks. Heating and transport also have `paper_generation.json` records binding their prepared tables to their raw sources and method. Previously generated industry proxies, centroid heating calculations and transport outputs produced without a working OSM parser must be regenerated; **Export existing** cannot repair them. Reuse cached downloads when regenerating. Missing sources download automatically, and valid raw calculations are reused only when their method, source hashes and outputs match.

Sources: [EU ETS installation compilation](https://zenodo.org/records/21414185), [EEA industrial emissions dataset](https://industry.eea.europa.eu/industrial-emissions/dataset), [JRC EIGL industrial sites](https://arcgis.jrc.ec.europa.eu/server/rest/services/eigl/EIGL_SERVICES_Industrial_infrastructure_PUB/MapServer), [GISCO NUTS boundaries](https://gisco-services.ec.europa.eu/distribution/v2/nuts/), [JRC-IDEES-2021 archive](https://zenodo.org/records/15895830). The [full audit](PAPER_METHOD_AUDIT.md) lists the heating and transport references.

## Generated example

The 5 November Excel export correction accepts worksheet data expressed with XML namespace prefixes, including `ns0:sheetData`, as well as default namespaces and empty self-closing data elements. It updates worksheet dimensions and table ranges while preserving unrelated package parts and formula caches. If export stops with `Cannot locate native sheet data in tech_cost_years`, apply the update and retry **export existing outputs** with the same prepared output folder and model settings. Source downloads and sector calculations do not need to be repeated for this XML formatting issue.

For landlocked countries such as Hungary, domestic shipping rows can represent inland waterways. They use inland OSM port/quay evidence and retain their national activity and energy; international sea shipping remains zero when its national source is zero. The generator prevents the legacy all-county fallback when shipping weights are zero. Missing inland port evidence produces an explicit error before model files are constructed. See the [navigation correction in the method audit](PAPER_METHOD_AUDIT.md#transport). Keep **Refresh downloaded source data** off when rerunning after an update to reuse cached PBFs, rasters and parsed OSM features. Regenerate the affected transport outputs before exporting.

The prepared Croatia NUTS3 data folder is **`sve_za_HR_NUTS3/data`**. Use it as the separate H2RES installation's `data` directory. `sve_za_HR_NUTS3/H2RES_DATA_manifest.json` records the configuration, provenance, defaults and validation results. Reports remain outside `data`, keeping its native file structure intact. An output directory chosen in the GUI replaces this example name.

An additional archive and validation delivery is retained in:

```text
sve_za_HR_NUTS3/model_inputs/h2res_inputs/
  data/                         same native file and folder layout as the model
    generators.csv              GENCO in the model's actual filename
    flex_tech.xlsx
    flex_tech_categories.xlsx
    flex_tech_complex_industry.xlsx
    flex_tech_efuel.xlsx
    flex_tech_efuel_categories.xlsx
    flex_tech_efuel_complex_industry.xlsx
    policy.xlsx
    policy_efuel.xlsx
    policy_fuels.xlsx
    industry_complex*.xlsx
    h2_terminals.xlsx
    electricity_demand.csv
    renewable_availability.csv
    hydro_inflows.csv
    industry_heat.csv
    industry_category_profiles.csv
    industry_electricity.csv
    heating_individual.csv
    heating_district.csv
    heating_electricity.csv
    transport_demand.csv
    transport_profiles.csv
    ...                         other native demand, price and supply CSVs
    README.md
    sources/
      JRC-IDEES-2023_Industry_HR.xlsx
      JRC-IDEES-2023_EnergyBalance_HR.xlsx
      JRC-IDEES-2023_EmissionBalance_HR.xlsx
    variants/technical_2050/
      flex_tech_efuel_categories.xlsx
  model_input_selection.json
  package_manifest.json
  FILES.csv
  validation.json
  scenario_reader_validation.json
  H2RES_model_inputs.zip
```

The ZIP contains the same delivery, excluding the ZIP itself. `FILES.csv` lists every data file with its size and SHA-256 hash. The delivery metadata and reports remain outside `data`, keeping the model's data layout intact.

## Selected configuration

| Industry mode | Without e-fuels | With e-fuels |
|---|---|---|
| Regular | `flex_tech.xlsx` | `flex_tech_efuel.xlsx` |
| Categories, conservative | `flex_tech_categories.xlsx` | `flex_tech_efuel_categories.xlsx` |
| Categories, technical 2050 | `flex_tech_categories.xlsx` | `variants/technical_2050/flex_tech_efuel_categories.xlsx` |
| Complex | `flex_tech_complex_industry.xlsx` | `flex_tech_efuel_complex_industry.xlsx` |

Complex mode also selects its matching `industry_complex*.xlsx`. Its technical-2050 companions keep their filenames at the data root, as in the supplied model.

With **Generate all native flex_tech and industry variants** enabled (the default), all seven technology paths receive the prepared geography and applicable sector tables. Regular and category representations use their respective generated equipment tables. The process method compiles four matching complex-industry companions, covering both e-fuel choices and both electricity cases. Each companion uses the selected country's JRC observations.

Transport retains the model's existing vehicle, service, engine and fuel structure. Each technology workbook receives transport rows matched to that variant's template, including its paid engine conversions and primary-fuel mappings. No transport workbook filenames are invented: the native H2RES flags select the six root workbooks or the existing technical-2050 path.

The model's industry/e-fuel flags select which workbook it reads. `variant_inventory.json` lists the generated alternatives and their settings; `model_input_selection.json` identifies the selected configuration. Disable all-variant generation only for an advanced selected-configuration export; inactive alternatives then retain reference data.

Select all four sectors for newly sourced power, industry, transport and heating data. The current `sve_za_HR/data` example contains all four prepared HR sectors. Unselected sectors retain supplied defaults, identified in `sector_sources` and `input_provenance.json`.

## Defaults and observations

Public sources supply historical observations and weather. Supplied model data provide technology costs, lifetimes, conversion parameters, investment limits, policy assumptions and inputs not prepared by a source pipeline. These defaults remain editable; they are not reported as new internet observations. Missing geography in default tables is inherited explicitly, with donor country/zone and affected rows or columns recorded in `default_geography_assumptions`.

Generated demand and availability files must cover the requested zones, generators and complete 8,760-hour model calendar. Missing generated series remain errors. Complex process energy/activity totals remain in the process companions; common industry CSVs supply native shared aggregate/profile inputs.

An active demand zone need not contain a generator in the source inventory. This can occur at NUTS3 resolution. Such zones remain active, retain their sector demand and defaults, and appear in `zones_without_sourced_generators` as a warning. No artificial plant is added. Existing generator profiles, hourly demand and requested geography remain mandatory checks. The warning describes catalogue coverage, not proof that the region has no real-world generation.

Regional workbooks can have large worksheet XML parts. Integrity validation streams those parts with bounded buffers and reuses results only for identical SHA-256 file contents. Unchanged ZIP parts are copied as streams while patching. If an export nevertheless runs out of memory, the previous delivery remains intact and `model_export_failure.json` identifies the preserved, unvalidated recovery bundle. A recovery bundle must pass validation before use.

### Windows path errors after validation

On Windows configurations enforcing the legacy 260-character limit, the older nested archive staging path could fail with `[WinError 3]` after all variants had passed. A 126-character output directory produced a 260-character temporary technical-2050 workbook path. Package staging now uses a short sibling directory on the same volume, preserving transactional publication without requiring a Windows registry change. Native filenames and the final folder layout are unchanged.

If `model_export_failure.json` records `recovery_input_coverage_passed: true`, keep its `_unpublished_model_inputs_...` folder. After applying the updated exporter, run the recovery command from the existing preparation application folder using its `.venv`:

```powershell
.\.venv\Scripts\python.exe native_data_delivery.py --out-root outputs_all_HR3 --recovery-bundle outputs_all_HR3\_unpublished_model_inputs_ugimad3g
```

These names match the reported HR3 example; otherwise use the paths recorded in your failure file. When the package was not created, recovery revalidates the saved native variants, rebuilds the folder/ZIP, verifies file hashes and publishes `data`. It does not download source data or regenerate sector observations. Existing published inputs remain available if recovery fails. New failure records include the failing phase, traceback and Windows filename/error fields where supplied by Python.

## Using the preparation interface

1. Open `START_DATA_PREPARATION.bat`. Reopen an older window to see the new controls.
2. Select the country, geography and output parent directory.
3. Select all four sectors for newly prepared country data.
4. Keep H2RES export and all native variants enabled on **Output format**.
5. Use **generate** for sourcing, or **export existing outputs** to rebuild from completed sector files and cached process observations without downloads.
6. Open **H2RES data folder**. Usable files are directly in `<output directory>/data`.

Leave **Refresh sources** off to reuse downloads. Wind/solar profiles are required for complete power exports. Reuse of a compiled process variant checks its source hashes, template assumptions, year, geography/weights and Excel integrity first.

## Version migration and preparation

The portable format reference is `model_reference_2_11_2026`. The old `model_reference` is retained; default references from older windows are redirected automatically. No original model data are overwritten. Worksheet replacement preserves native Excel tables, relationships and formatting; broken worksheet/table links block publication.

This model uses short live workbook names. The old `_electricity_review` and `_electricity_technical_2050` filename suffixes are not exported as live aliases. Relative variant paths are retained by the input-reader/scenario adapter. Cached complex-industry exports are applied to the current repaired technology workbook, retaining its current financial sheets and adding the required component-cost proxies.

Re-export the cached HR example without downloading:

```powershell
python generate_all_sector_inputs.py --countries HR --sectors power,industry,transport,heating --spatial-level country --out-root sve_za_HR --data-root data_HR_za_pripremu --industry-mode categories --efuels --power-output-level individual --hydro-output-level individual --export-only --all-model-variants --require-model-ready
```

For new observations, use **generate** and choose the country, spatial level, sectors and configuration in the preparation interface. The output format defaults to this model version. Combined H2RES input packages require complete coverage: incomplete inputs stop the export and preserve the previous valid package. The missing-data report is available in the run log and `model_export_failure.json`.

## Verification

### Industry aggregation and generator identities (5 November 2026)

`simple_industry` is calculated from the same workbook's `Industry_data` and the applicable hourly industry demand. A service is pooled only when all its equipment flags are excluded; an active heat pump also makes that service detailed. Installed capacities, capture stocks, capacity ceilings and investment envelopes are summed over the excluded services. Baseline fuel shares and share ceilings are weighted by their useful heat demand; efficiency is harmonically weighted to preserve fuel input, and combustion intensity is weighted by that fuel input. Empty investment limits retain the native unlimited/default semantics. A fully detailed representation correctly has an empty `simple_industry` table with its native columns. No zero-capacity placeholder sector is introduced.

Each physical `generators.csv` name is written verbatim into every generated workbook's `tech_cost_years` and `cap_inv_lim`. Costs and limits must cover every calendar year in the supplied planning range, not just planning milestones. A plant receives its investment allocation only in its home zone. The source national technology build budget is divided across the matching plants by existing capacity, so adding regions or plants does not multiply that budget. Zero-stock groups use equal shares explicitly. Heating limits continue to use heating demand shares.

`model_inputs/generator_input_links.json` records each plant's location, fuel, machinery/CHP match, reference cost column, investment donor columns, national annual budget and allocated share. Costs, investment limits and maintenance values are scenario defaults rather than measured plant finance. Compatible machinery/fuel/CHP proxies are identified. Geothermal power uses the separate reference power-cost assumption; without a supplied geothermal build envelope it receives zero new-build allowance. `literature_fixed_opex.csv` includes the generated plant names using the reference annual maintenance value where available, otherwise the model's explicit 1% of CAPEX per year default.

### Regional network assumptions

Supplied connections between active regions are retained. Where the supplied workbook has no connected regional electric network, the exporter connects disconnected components through the largest-demand region using bidirectional, zero-distance virtual exchange links. Their fixed capacities use reference carrier capacity ceilings, with zero loss/variable cost and no new-build allowance. Matching hydrogen defaults and the native e-fuel carrier blocks are completed where applicable. These are declared national-exchange modeling assumptions, **not observed transmission lines, surveyed capacities or a calibrated NUTS3 network**. A grid-constrained study must replace them with its own network.

External national transfer capacities and build envelopes are allocated once over the regions using electricity demand shares. Merged two-row transmission headers are retained, including completion of the truncated reference e-petrol block from petrol parameters. The exporter checks that the active national electric network is connected and external-transfer rows cover the active regions. `model_inputs/network_input_assumptions.json` records every added connection and carrier-default repair.

The outside-system supply mix and normalized hourly availability curves describe one external system. They retain one row per year/hour and are never duplicated for each modeled country or region. Their unique keys, value bounds and full hourly calendar are checked before publication.

National generation targets, hydro ceilings, biomass-feedstock budgets and outside-trade targets retain their national totals using the native `Zone='*'` system-aggregate scope. They are not apportioned by county electricity demand. Positive generation calibration targets without any corresponding active sourced generator are not applied; the supplied target and reason remain in `model_inputs/policy_input_assumptions.json` and a validation warning. For the checked HR inventory this applies to the reference 0.6095 TWh biomass-power target: the sourced inventory has no biomass generator. No biomass stock is fabricated to enforce it. Restore a supported calibration target after supplementing the plant inventory when required by the study.

### Running the selected data with minimal configuration

The exact native folder is `<output directory>/data`; its 43 paths match the supplied H2RES format reference. Copying that folder still requires selecting the corresponding industry/e-fuel flags in the model. Alternatively, the generated launcher applies the recorded selection and points the separate model at this folder without editing its files. From the output directory, using the Python environment containing H2RES and Gurobi:

```powershell
python model_inputs/run_model_scenario.py --model-root "D:\POSAO\H2RES_2.11.2026_novi" --bundle .
```

This command loads inputs only. Add `--solve` to start the configured model run. Use `--industry-mode regular`, `--industry-mode categories` or `--industry-mode complex`, `--efuels`/`--no-efuels`, and `--industry-electricity-case conservative`/`technical_2050` to choose another generated variant. The launcher also translates legacy generator-specific build-limit multipliers to the generated plant names; conflicting donor multipliers require an explicit plant-specific choice. The separate model installation supplies its own runtime policies and solver license.

The supplied H2RES reader has a legacy remainder-aggregation loop that concatenates results before all regions are read. This can drop other regions' source demand. The generated launcher moves that concatenation after its loop in memory, preserving the native input format and original model files. It prints an `[INPUT COMPATIBILITY]` message when this correction is needed; an already corrected reader passes through. Use this launcher for regional runs with the supplied reader. Copying `data` into an uncorrected model and launching its original `main.py` directly does not apply this correction. The input-reader checks independently compare the loaded regular/category industry service totals with the source profiles in every region.

For complex industry, zero facility-allocation weights imply zero local activity as well as zero energy and stocks. Nonphysical national production indices remain unscaled in positive-share regions because their process intensities carry the regional share; those indices are set to zero in zero-share regions. Physical product tonnes continue to be allocated by the facility shares. The export repairs this condition in older compiled companions before publishing and records the affected tables in `complex_zero_weight_activity_repairs`.

Verification records are in `validation/native_data_verification.json`, `validation/native_data_readers`, `validation/excel_sheet_diagnosis/results.json` and `validation/native_data_regression_tests.log`. They cover the exact directory layout, native alternatives, actual Excel opening, H2RES input-reader configurations, model-source immutability, defaults and atomic publication. Reader validation does not build or solve an optimization.

Passing the reader establishes compatibility with the tested input configuration. Scenario assumptions, reference data retained for unselected sectors, and optimization feasibility still need the corresponding study checks.
