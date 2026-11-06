# Internet data sourcing and input preparation manual

**Version documented:** source snapshot of 1 November 2026. See [version inventory](inventory/documented_version.json). References use identifiers in the [bibliography](REFERENCES.md).

**Updated regional preparation, 4 November 2026:** see the [paper-method audit](PAPER_METHOD_AUDIT.md) for the current source downloads and industry/heating/transport allocation, and [native data delivery](MODEL_DATA_2_11_2026.md) for the current model layout. The original inventories and compiled PDF/HTML retain their dated snapshot.

## 1. Purpose and boundaries

The tool obtains public energy and spatial data, caches downloads, transforms observations into sector input tables and hourly profiles, and packages those files in the interface required by the supplied H2RES model. It supports power, industry, transport and heating. It can prepare one country, several countries or a shared custom geography.

The graphical application is **Energy Data Sourcing and Preparation**. Its only preparation runner is `generate_all_sector_inputs.py`. It does not operate the H2RES solver. A separate adapter can accompany an output bundle so an independently run H2RES installation reads the right variants and policy settings; its existence does not mean preparation ran an optimization.

The model-compatible package combines newly prepared sector data with portable template inputs. Selecting one sector regenerates that sector; it does not automatically recalibrate every remaining workbook, network, cost, policy or demand series for a new country. The coverage report is essential when moving beyond the template geography.

## 2. Package layout

| Path | Role |
|---|---|
| `START_DATA_PREPARATION.bat` | Main Windows shortcut |
| `launch_data_preparation.ps1` | Python discovery, dependency probe, startup logging and safe path handling |
| `data_preparation_gui.py` | Public interface entry point |
| `h2res_input_gui.py` | Interface implementation; historical module name retained for compatibility |
| `START_H2RES_GUI.bat` | Compatibility shortcut to the same preparation interface |
| `data_preparation_config.json` | Saved settings, excluding the ENTSO-E token |
| `generate_all_sector_inputs.py` | Shared orchestration, geography and calls to sector generators |
| `preparation_dependencies.py` | Selected-sector dependency checks before downloads/output changes |
| `model_reference/data` | Portable format, technology and scenario templates |
| `model_input_bundle.py` | Native file export, worksheet replacement and coverage checks |
| `scenario_config.py` | Input-year, renewable-target and investment-limit assumptions |
| `industry`, `power`, `transport`, `heating` | Sector implementations and bundled support resources |
| `data_all*` | User-selected download/cache roots; they may contain multinational source data |
| `outputs_all*` | User-selected prepared output roots |
| `validation` | Developer test evidence; not a guarantee that a fresh national scenario is feasible |

## 3. Installation and environment

Use a consistent 64-bit Python environment. The launcher accepts Python 3.10 or later and checks the basic table packages; selected pipelines additionally need geospatial, raster and weather dependencies. Python 3.12 is the interpreter used in the recorded local verification. A solver package/license is not required to source and prepare data.

Install from the repository directory using the Python that will run the application:

```powershell
& "C:\Users\lukah\AppData\Local\Programs\Python\Python312\python.exe" -m pip install -r requirements.txt
```

The default requirements include NumPy, pandas, openpyxl, Requests, GeoPandas, Shapely, pyproj, pyogrio, rasterio, rasterstats, pyxlsb, pycountry, xarray and netCDF4. The optional CDS downloader adds `requirements-cds.txt`. Tkinter normally comes with the Windows Python installation. GeoPandas installation guidance is maintained by its developers [R26](REFERENCES.md#r26).

The launcher searches a local `.venv`, standard Python directories, Anaconda/Miniconda locations and a usable PATH interpreter. `DATA_PREPARATION_PYTHON` can identify another `python.exe`. It verifies the interpreter before starting the interface. Installing a package into a different Python does not fix the interpreter used by the application.

Check the complete default stack without opening a window:

```powershell
.\START_DATA_PREPARATION.bat -Check
python preparation_dependencies.py
```

The preparation command and interface start action also check dependencies for the selected sectors. Complex industry alone needs fewer packages than raster-based category industry. Missing or broken imports produce an install command containing the active Python path before the tool starts source downloads or deletes old raw build files.

## 4. First run and interface

Double-click `START_DATA_PREPARATION.bat`, or run `python data_preparation_gui.py`. The old shortcut remains compatible. Paths containing spaces and parentheses are handled by the PowerShell launcher. Startup information is written to `DATA_PREPARATION_STARTUP.log`.

### 4.1 General

Select a country code such as `IT` or `HR`, a comma-separated list such as `HR,SI`, or `ALL`. Choose the sectors, spatial resolution, output root and cache root. Enable e-fuel-compatible inputs when required by the intended model representation. Refresh forces source updates; leave it off when intentionally reusing cached observations.

### 4.2 Power and profiles

Choose aggregated units, individual units or both. Hydro profile resolution can follow power resolution or be selected separately. Choose weather/statistical years, Open-Meteo or Renewables.ninja, and IRENA calibration. Enter the ENTSO-E token if electricity demand is being downloaded. Skip controls deliberately omit the corresponding profile work; a successful plant-table run with skipped curves is not a complete power-data package.

### 4.3 Heating and advanced

Choose Open-Meteo temperatures or an existing/CDS NetCDF source, and optionally supply a population raster. Regional heating uses eight inhabited grid-point samples per NUTS3 region, population-weighted temperatures, CHP locations and five fuel-prevalence maps. Raw calculations are reused only when source/method fingerprints and output hashes match. See [the paper-method audit](PAPER_METHOD_AUDIT.md).

### 4.4 Output format

`generate` sources/prepares the selected data. `export existing outputs` repackages files already prepared. Select regular, category or complex industry and the conservative or technical-2050 electricity case. The portable templates directory supplies schemas and technology/policy assumptions. Packaging in H2RES format is optional; strict coverage can make an incomplete bundle return an error.

### 4.5 Industry sources

The calibration year, regional-allocation choice and missing-source download control also apply to regular/category industry. Their national totals use JRC-IDEES-2021. EU ETS/EUTL, EEA IED and JRC EIGL facility evidence downloads automatically into the industry cache; missing branch coverage is explicitly recorded as an industrial-site-density assumption. The JRC-IDEES-2023 source folder, explicit complex sector selection, user-supplied complex weights and waste-allocation policy configure the complex compiler. Automatically generated complex variants use the same facility branch geography as the prepared regular/category tables. The source-folder field is not forwarded as the regular/category JRC-IDEES-2021 directory.

### 4.6 Input assumptions

Set planning years, renewable target and annual investment multiplier, or supply scenario JSON. These choices affect prepared future-year input/policy tables. Historical/statistical source years remain separate. `reference` retains supplied assumptions unless other explicit settings request changes. `res100` records the chosen renewable policy and requires e-fuel-compatible inputs for the whole-energy option.

### 4.7 Run controls

The command preview is the exact argument list passed to the runner. **Source and prepare data** starts it in a worker process. The run log combines output and errors. **Stop** terminates the tracked orchestration process; do not assume it can roll back downloaded or partly written files or every spawned child. Review outputs and rerun with matching settings. **Save settings** preserves selections; the ENTSO-E token is omitted. Legacy configuration is read only if the new configuration file does not exist.

## 5. Country selection and multinational downloads

The requested countries are passed to each sector generator. The shared map is restricted to those countries. Normal processing loops operate on that list, and `ALL` expands only when explicitly selected.

Country selection does **not** mean every upstream download is country-specific. The category industry path downloads the complete JRC-IDEES-2021 archive and SECURES archive, then finds the requested country's workbooks/profiles. The inspected archives contained 27 JRC countries and 29 SECURES demand-country codes. GISCO boundaries, EIGL rasters, the powerplants database and JRC hydro database also cover broad regions [R06](REFERENCES.md#r06), [R08](REFERENCES.md#r08), [R09](REFERENCES.md#r09), [R10](REFERENCES.md#r10), [R11](REFERENCES.md#r11).

Transport unpacks national tables for many countries from bundled assets. Those folders are not separate internet downloads and do not imply that all countries were allocated. Its OSM downloader requests the chosen country extracts; the inspected Italy cache contained `IT.osm.pbf` only [R13](REFERENCES.md#r13).

Complex industry uses separate public JRC-IDEES-2023 country archives and selects the Industry, EnergyBalance and EmissionBalance workbooks [R07](REFERENCES.md#r07). Do not confuse this method with the category pipeline's older bulk archive.

Verify selection in the output, not by counting country names in a cache. Power rows use `System` and `Zone`; most other sector tables use `System` and `zone`. For national Italy these should be `IT` and `IT1`. Intermediate industry files can still use Italian NUTS3 codes before shared aggregation. The read-only checks performed during development found 1,073 Italian power rows and Italy-only industry/transport tables; this is evidence for those files, not certification of every future run.

## 6. Spatial and temporal conventions

The shared geography is based on 2021 NUTS3 boundaries. The default CLI spatial level remains `nuts3`. Country resolution maps the selected country's NUTS3 units to a zone such as `IT1`. NUTS2/NUTS1 use the corresponding code prefixes. Custom maps have `country,nuts3,zone`; optional `system_new` permits a shared model system.

```csv
country,nuts3,zone,system_new
HR,HR021,Adriatic1,Adriatic
SI,SI031,Adriatic1,Adriatic
```

This is a schema example, not a complete territorial allocation. Every required source region must have an unambiguous target. Zone names must be globally unique unless the countries genuinely share the same modeled system/zone. A custom aggregate does not automatically create cross-border transmission, resource potentials or consistent policy targets.

The model calendar has 8,760 hourly positions, numbered 1–8760. Timestamped leap years drop February 29, preserving the rest of the calendar. Do not relabel an unexplained 8,759-row or duplicated-hour series as complete. For one-hour intervals MW and MWh/hour have the same numeric value, but capacity and annual energy remain different quantities. Source weather, source statistics and future decision years must be stated separately.

Country aliases matter: EU datasets commonly use `EL` where other providers use `GR`. Individual modules handle supported aliases at source boundaries; the model's System labels must remain consistent. Do not silently mix country-code conventions across tables.

## 7. Power inventory and electricity demand

### 7.1 Inventory construction

The power builder combines non-hydro rows from powerplantmatching with hydro rows from the JRC hydro database, avoiding a direct second inclusion of hydro powerplantmatching rows. It normalizes fuel and technology labels, assigns locations to NUTS polygons, and fills technical fields from supplied reference/default tables [R09](REFERENCES.md#r09), [R10](REFERENCES.md#r10).

It can exclude unsupported battery rows from this generation inventory and rejects missing/non-positive hydro capacities. The raw builder assigns unresolved border/outside locations using nearest spatial matches. For more detailed geographies, inspect these corrections: nearest placement is a spatial proxy. Capacity, location, decommissioning and commissioning status need a study-specific inventory audit. Downloading a fresh CSV does not prove that every row is an operating plant in the intended base year.

Plant parameters such as efficiency, remaining life and costs can come from template medians rather than individual observed plants. A Croatian donor parameter is a technology default, not a Croatian capacity observation being asserted for Italy. Preserve the distinction when reporting results.

### 7.2 Aggregated and individual outputs

The orchestrator builds a detailed inventory and both aggregation schemas. Aggregated units pool compatible technology/fuel rows by target zone. Individual mode retains plant rows and requires profiles keyed to those individual names. `both` provides the canonical chosen aggregation plus supplementary individual files. Never combine an individual inventory with only aggregated availability columns.

Main outputs are `power/GENCO.csv`, `power_inputs.xlsx`, `_genco_aggregation_schema.csv` and `_genco_individual_schema.csv`. The exported bundle renames the canonical inventory to `generators.csv`.

### 7.3 Electricity demand

The demand module requests actual total load from the ENTSO-E Transparency Platform by month using `documentType=A65` and `processType=A16`. Requests use the applicable national/control-area code and selected year. The token is obtained from the GUI/environment; it is not a data parameter to publish. API requirements and code lists are maintained by ENTSO-E [R12](REFERENCES.md#r12).

Regional shares are derived from the JRC EIGL 2019 total-electricity raster. They allocate national hourly magnitude; the raster year is not the ENTSO-E load year. If A(t) is national load and w(r) are normalized spatial weights, then L(r,t)=w(r)A(t), and regional values reconcile to national load at every hour. Demand is subsequently aggregated through the shared map.

Do not subtract/add the same industrial or heating electricity twice. The prepared baseline and the model's endogenous sector electricity must obey the baseline convention documented in the model manual and the source-year assumptions of the scenario.

## 8. Hydro, wind and solar profiles

### 8.1 Hydro

Normal execution uses bundled plant runoff shapes, rather than deriving a new European hydrology model. The bundled `runoff_shapes_2020.npz` and supporting unit/quality tables therefore have their own provenance and year. The JRC database provides plant information [R10](REFERENCES.md#r10); it is not by itself the source of all hourly hydrology.

Run-of-river curves are normalized to annual generation and capped by capacity. Reservoir inflows are scaled with generation/discharge assumptions and expressed using the model's capacity-normalized convention. Pumped-storage plants without natural inflow are treated as closed-loop. Several generator components matched to one hydro complex share its annual generation by MW to avoid duplicating the whole complex's inflow. Aggregate curves are capacity-weighted.

Read matching/quality outputs for missing profiles, nearest mappings, equivalent full-load hours and excluded units. Plant runoff shapes and inflow-derived generation are approximations; inflows, dispatch and reservoir stock have distinct physical roles.

### 8.2 Wind and solar

The default module requests Open-Meteo historical weather at plant sites and transforms radiation/wind into proxy PV/turbine capacity factors. Requests are cached by their parameters. Renewables.ninja is an alternative simulation backend and requires `RENEWABLES_NINJA_TOKEN` [R15](REFERENCES.md#r15), [R18](REFERENCES.md#r18).

These are weather-derived profiles, not measured plant output. Reanalysis information and temporal coverage are documented by the weather providers [R16](REFERENCES.md#r16), [R17](REFERENCES.md#r17). Profile uncertainty includes turbine parameters, hub height, PV orientation, irradiance conversion, weather resolution and missing operational losses.

IRENA calibration uses a local statistics extract. The target is annual generation divided by capacity and hours:

```text
target_CF = generation_GWh × 1000 / (capacity_MW × hours)
```

A technology-level scaling factor is solved against the national capacity-weighted mean while clipping hourly factors to [0,1]. Scaling precedes aggregation. Record the exact statistics year and local workbook hash; do not cite the current IRENA website as proof of the values in a previously extracted workbook [R19](REFERENCES.md#r19).

## 9. Regular and temperature-category industry

This path uses JRC-IDEES-2021 annual information, national SECURES demand shapes and spatial allocation helpers. It has its own reference years and should not be described as the JRC-IDEES-2023 complex method. The helper scripts are compressed into the standalone file and unpacked for execution; their geospatial/raster imports are real dependencies.

The allocation stage combines national sector/fuel observations with NUTS3 spatial weights and temperature bins. A complete new country-specific process-by-temperature cross-tabulation has not been rebuilt by the handoff integration. Inherited allocation rules and optional facility/EIGL evidence must be documented as such.

Regular mode aggregates delivered industrial services by sector. Categories retain temperature/service classes, including `NON_HEAT`, so electrical mechanical and other non-heat services are not lost from the total. Legacy process-heat-only views remain available for a different purpose and must not substitute for the full native demand file.

Source-energy allocation, assumed operating hours/reserves and technology efficiencies are used to derive equipment baselines. These derived MW values are not an observed industrial plant census. Equipment parameters and available future alternatives can come from portable templates.

The generator writes regular/e-fuel and category/non-category variants. The chosen representation is canonical `Industry_data`; exact `Industry` and `category` columns must match profile labels. Baseline electricity is exported separately. The bundle recalculates the pooled `simple_industry` remainder from excluded source services and demand weights; retaining old cached pooling formulas would risk double counting.

National aggregation should conserve each allocated service's demand and baseline equipment totals. Inspect the country `01_allocated`, `02_units_hourly`, `03_non_energy` stages before relying on combined results.

## 10. Complex process industry

### 10.1 Observation extraction

The new compiler uses the supplied handoff's process-tree extraction and service-screening methods. The three country source workbooks are JRC-IDEES-2023 Industry, EnergyBalance and EmissionBalance [R07](REFERENCES.md#r07). It traverses useful-energy, final-energy and emissions trees by indentation and matching paths, rather than adding every subtotal as a separate service.

It produces eleven native sectors: Iron_steel; Non_ferrous_metals; Chemical_petrochemical; Non_metallic_minerals; Paper_pulp_printing; Food_beverages_tobacco; Transport_equipment; Machinery; Textile_leather; Wood_wood_products; Not_elsewhere_specified_(industry).

Every observation retains source workbook hashes and sheet/cell addresses. Requested calibration year defaults to 2020. A branch with no positive activity in that year can use its latest positive observation; fallbacks are recorded and must be considered when comparing the aggregate with a single-year national total. Numeric formulas without cached results are rejected.

For a process/fuel stream:

```text
useful_MWh = useful_ktoe × 11630
final_MWh  = final_ktoe × 11630
efficiency = useful_MWh / final_MWh
useful_share(f) = useful_MWh(f) / sum_f useful_MWh(f)
initial_capacity_MW(f) = useful_MWh(f) / 8760
combustion_factor(f) = observed_CO2_t(f) / final_MWh(f)
```

Observed aggregate useful/final ratios above one are retained; arbitrary unobserved combustion alternatives do not inherit a ratio above one. The capacity formula is explicitly an average-utilization assumption, not measured installed nameplate MW.

### 10.2 Product activity and process emissions

Physical output reported in kt is converted to tonnes. Output indices remain indices, using `_per_activity` intensities; the legacy `_per_t` fields are blank for index sectors. Useful energy is activity × intensity. Observed branch process emissions are assigned once to an emitter component, kept separate from fuel combustion. Capturable fractions remain assumptions.

Observed product activity is used through the final source year; afterward the last observation is held constant through 2050. This is an editable scenario extension, not a forecast produced from the internet.

The supplied material-feedstock convention maps legacy non-energy gas/oil services to H2-fed demand. Croatia's exact documented 2020 basic-chemicals ammonia-reforming term (535,320.11 tCO2) is retained in historical fields but excluded from additional process emissions under that convention. The exception is guarded by country, branch, source year and amount. Other-country process emissions remain unchanged pending their own evidence [R23](REFERENCES.md#r23), [R24](REFERENCES.md#r24).

### 10.3 Biomass and fossil waste

The source can group renewable biomass and fossil waste. Combustion CO2 remains the observed stream factor. Where matching balance evidence shows one fossil-waste class, its factor permits the exact energy split. Default `sector-blend` mode otherwise assumes that the observed sector fossil-waste blend applies to its processes and records that assumption. `strict` rejects ambiguous splits. Neither method silently labels observed fossil-waste emissions as renewable.

### 10.4 Alternatives and heat pumps

The inherited method screens substitutes by service and compatible incumbent fuel families. Material/feedstock services and identified reducing chemistry are protected. Biomass share growth is blocked; lignin is limited to a small local eligible solid-heat expansion. Equipment replacement options do not assert that the unmodified original burner or motor accepts every new fuel.

Conservative electrical screening preserves established electrical/mechanical/cooling/low-heat services and uses a partial additional envelope for unresolved furnaces; technical-2050 broadens eligible future equipment. The partial-coverage coefficient is a scenario rule, not a measured national adoption statistic. The supporting industrial-heat literature is listed in [R20](REFERENCES.md#r20)–[R22](REFERENCES.md#r22) and the inherited bibliography.

Heat pumps have 60, 80, 125 and 150 °C equipment classes. Their COP, lifetime, cost proxies, cumulative sink-temperature budgets and source-heat fractions are assumptions. Shared budgets prevent adding the individual maxima as if each were independent eligible demand.

### 10.5 Regional allocation and cost proxies

National source observations need regional assumptions. Country resolution needs no weighting file. A regional CSV has `country,zone,Industry,weight`, with `Industry=*` as a common fallback. Every selected country/sector must cover its zones and sum to one. `--industry-regional-allocation equal` is an explicit equal-weight proxy.

Energy, emissions, physical output and finite national annual build budgets are apportioned. Activity indices remain unchanged and their intensities are apportioned instead. Blank limits remain unrestricted, and zero remains blocked. Cross-country merged zones use country-prefixed process keys to preserve distinct intensities/activity indices.

New component cost columns copy explicit generic equipment donor curves, preserving existing component-specific costs and unrelated workbook XML/cached formulas. This fills an input interface; it does not create a new equipment-price survey.

### 10.6 Outputs and reconciliation

Read `complex_generation.json`, `source_reconciliation.csv`, `industry_allocation.csv`, `normalized/*` and the selected complex workbook. National HR1 runs also write `reference_calibration_diff.csv`. Reconciliation covers useful energy, final energy, combustion CO2 and historical process CO2 by sector. The compiler uses inherited country hourly shapes rescaled to source totals, or records a flat fallback; it does not claim measured process-level hourly production.

## 11. Transport

The transport preparer unpacks the national base tables and availability/activity curves supplied with the package, then allocates country service demand to NUTS3/target zones using spatial evidence such as energy-demand rasters and OSM transport indicators. Much of this national data is bundled; it is not freshly retrieved from a national statistics API on every run.

Road/rail/marine/aviation activity, vehicle counts, primary/secondary efficiencies, storage sizes and plug-in/V2G availability are different data types. `transport_demand.csv` contains activity shapes; `transport_profiles.csv` contains equipment/parent plug-in availability. The native model multiplies activity by annual demand/stock inputs. Do not treat a normalized activity profile as MW load.

GeoPBF downloads are country-specific. If the installed GDAL/OSM stack cannot provide rail, shipping or aviation indicators, documented allocation fallbacks may be used. An output can therefore be structurally valid while containing proxy spatial weights. Inspect warnings rather than interpreting absence of a traceback as complete infrastructure evidence.

The bundle preserves paid engine conversions and `compat_*` metadata from the technology templates, including primary-fuel recipes and parent availability profiles. Marine pilot fuel, blend ceilings, newbuild premiums and conversion lifetime/cost assumptions are scenario inputs. They are not a statement of current fuel certification or a calibrated Italian/Croatian fleet [R25](REFERENCES.md#r25).

Source shipping identifiers are normalized to the current model contract: `ICE_MARINE_DOM` becomes `ICE_MARINE_SHORT` in `Domestic_shipping`, and `ICE_MARINE_INT` becomes `ICE_MARINE_LONG` in `international_shipping`. This preserves the source loads, counts and efficiencies. Normalization precedes generation of the domestic electric-vessel option and lookup of the model's paid conversion families. Cached hourly profile columns receive the same renaming when exporting older results. Unknown combustion-engine identifiers still cause an explicit compatibility error.

## 12. Heating and cooling-related inputs

The heating preparer combines JRC residential/tertiary annual energy with population, weather/HDD and fuel-demand/density rasters. Hotmaps density informs district-heating allocation; EIGL layers inform fuel/spatial shares [R11](REFERENCES.md#r11), [R14](REFERENCES.md#r14). It then prepares hourly useful demand and equipment tables for individual and district heating, and baseline electric heating.

The default weather path uses Open-Meteo temperatures. The alternative is an existing or CDS-downloaded ERA5-Land NetCDF. CDS access requires the provider's current account/token setup and dataset terms; use the provider's instructions and placeholders rather than publishing credentials [R15](REFERENCES.md#r15), [R27](REFERENCES.md#r27).

Population weighting and degree-day allocation are spatial/temperature proxies. They do not identify every building, heat network or retrofit opportunity. Separate solar/DH/boiler/HP technology rows include template assumptions. The preparation application does not simulate the economic operation of those assets. Cooling input files retained in a bundle should not be presumed freshly recalibrated merely because heating was generated.

## 13. Planning years, policy targets and investment defaults

Choose an increasing, equally spaced planning grid within available cost/input years. Current supplied templates cover 2020–2050; adding 2055 requires supporting data rather than extrapolation by label alone. The target year must be a modeled decision year after the start for the renewable preset.

`investment_multiplier=1` retains finite build limits; 2 doubles them; 0 sets finite limits to zero. It does not scale installed stock, all costs or total installed-capacity ceilings. Blanks and scalar fallback semantics remain intact. The model's runtime technology multipliers can additionally apply, so examine both layers.

The whole-energy `res100` bundle prepares the electricity RPS path plus integration metadata/constraints for fossil/nuclear energy, unverified imports and uncertified boundary storage at/after the target year. It is not a new historical dataset and is not the same target as net-zero CO2. Process emissions remain separately modeled. Actual enforcement belongs to the separately executed model adapter; copying CSVs alone does not insert its additional equations.

An example JSON is `scenario_defaults_res100_2050.json`. CLI fields override JSON fields. Per-row investment overrides use the native workbook's units; do not confuse MW/year, MWh/year, tCO2/hour or vehicle counts. Complex-workbook per-row overrides are not exposed as an independent GUI editor; check supported sheet names in `scenario_config.py` and edit the intended native complex inputs explicitly when necessary.

## 14. Worked commands

Run from the preparation repository. These examples prepare data; they do not run H2RES.

### 14.1 Full Italy preparation

Set an ENTSO-E token in the current shell, or enter it in the GUI. Do not substitute an actual token into published scripts.

```powershell
$env:ENTSOE_API_TOKEN = "YOUR_TOKEN"
python generate_all_sector_inputs.py --countries IT --sectors power,industry,transport,heating --spatial-level country --efuels --industry-mode categories --out-root outputs_IT --data-root data_IT --require-model-ready
```

A new country still requires complete matching template/network/policy coverage. If strict validation fails, read the reported gaps; do not relabel the bundle as complete.

### 14.2 Plant-table-only check using cached sources

```powershell
python power/generators/generate_genco_power_sector.py --mode raw --countries IT --out outputs_IT/power/_genco_nuts3_detailed.csv --output-format detailed --nuts3-geojson power/data/NUTS_RG_20M_2021_4326_LEVL_3.geojson --no-download-sources --no-clean-built-dir
```

This deliberately does not create all weather, hydro and electricity-demand profiles. `--no-clean-built-dir` preserves other previously built country files; the combine step still selects IT.

### 14.3 Croatian process-industry inputs and renewable assumptions

```powershell
python generate_all_sector_inputs.py --countries HR --sectors industry --spatial-level country --industry-mode complex --efuels --scenario-config scenario_defaults_res100_2050.json --out-root outputs_complex_HR --data-root data_all --require-model-ready
```

Unselected sectors come from the portable reference. This demonstrates an industry replacement within that baseline, not a fresh all-sector statistical build.

### 14.4 Industry regional weights

```csv
country,zone,Industry,weight
HR,coast,*,0.4
HR,inland,*,0.6
```

Use a matching custom map and `--industry-zone-weights weights.csv`. The example fractions are illustrative assumptions.

### 14.5 Package already prepared files

```powershell
python generate_all_sector_inputs.py --export-only --countries HR --sectors industry --industry-mode complex --efuels --out-root outputs_complex_HR --require-model-ready
python validate_model_inputs.py --bundle outputs_complex_HR/model_inputs --industry-mode complex --efuels
```

The export variant must match the generated e-fuel/electricity case. Sector selection metadata comes from generation. Changing these assumptions should normally be followed by generation with matching flags.

## 15. Output packaging and quality gates

Sector outputs remain under their own subdirectories. When enabled, `model_inputs/data` contains the native names and the selected technology/policy workbooks. `bundle_manifest.json` records selected sectors, country/zone coverage, template/source information, repairs, scenario settings and missing files. `validation.json` records structural/coverage errors and warnings.

An export starts from the template set and replaces selected sector inputs. Unchanged files/sheets can still contain other countries or old scenario assumptions. The `active_zones` sheet and each generated sector's coverage determine the selected case. A template file containing a country label is not proof that all its parameters are calibrated for that country.

Coverage checks include 8,760 unique hours per active zone, matching unit/profile names, required columns, active-zone coverage, category/process keys and finite nonnegative investment limits. Exact repeated transport-demand rows in the supplied template are removed and recorded; conflicting duplicates must not be silently accepted.

`ready=true` means the implemented input checks passed. It does not establish optimality, future demand realism, complete scientific provenance, lifecycle sustainability, security of supply or feasibility of a renewable policy. Actual-reader and solver tests are separate evidence levels.

## 16. Caching, repeatability and disk use

Keep the same cache root to reuse downloads. A new root is a new cache, even for the same country. Refresh can redownload large complete archives, and extraction can consume substantially more disk space than the ZIP. Some power raw data/build caches are module-global under `power/data` and `power/generators`, rather than fully isolated by `--data-root`; avoid concurrent runs that clean/write those same locations.

Record source release, retrieval time, exact request parameters, workbook/file hashes, statistical/weather years, country list, map and template version. Master-branch CSV endpoints change over time. Store the actual source snapshot used in a published study. Cache reuse improves repeatability but does not prove the cached data are the latest release.

Excel cached values matter. XML-level replacement preserves unrelated members/caches. An uncached numeric formula cannot safely be read as zero. Recalculate a source workbook in a compatible spreadsheet application where necessary, preserving the original as provenance.

## 17. Troubleshooting

| Symptom | Likely cause and response |
|---|---|
| Window closes before Python starts | Use the repaired PowerShell-backed launcher; inspect startup log, especially paths with parentheses |
| `No module named geopandas` or another package | Install `requirements.txt` with the exact interpreter printed in the log; restart the interface to load new checks |
| Many country files appear in cache | Bulk archives or unpacked bundled tables; inspect generated System/zone fields |
| Same large archive downloads again | Refresh enabled or a different cache root |
| Local JRC-2021 folder seems ignored | Industry-source-folder GUI control applies to complex JRC-2023, not the current category runner |
| Complex regional run refuses to proceed | Supply valid country/sector weights or explicitly select equal allocation |
| No SECURES profile for a country | The source coverage differs by country; `ALL` is not proof that all four pipelines can run for every code |
| Missing ENTSO-E token/invalid API response | Verify provider access, code/year and token without printing credentials |
| OSM fallback warnings | Installed reader cannot extract the intended infrastructure; inspect allocation weights and install/validate a suitable reader if required |
| `No current primary-fuel compatibility mapping for ICE_MARINE_DOM` (or `ICE_MARINE_INT`) | Older shipping names reached the export step. The current preparer normalizes both fleet rows and profile columns. Re-export existing results with matching settings and `--export-only`; use the transport script's `--skip-allocation` first to recreate its full option set from cached NUTS3 tables. Heating success messages before this error indicate that heating finished; the export subsequently failed. |
| `ready=false` after sector generation | Native input coverage is incomplete; read errors, generate missing profiles/sectors and provide missing country policies/networks |
| Complex workbook/export mismatch | Regenerate with the selected e-fuel/electricity variant |
| Source formula has no cached value | Recalculate the source workbook; do not fill zero automatically |
| A renewable target later proves infeasible | Review resources, build rates, fixed processes, trade/origin assumptions and turnover limits in the separate model |

## 18. Validation and reproducible reporting

The dependency/preparation regression suite passed 45 tests after the shipping-identifier correction. The Italy recovery check is recorded in `validation/transport_shipping_recovery.json`: source shipping loads/counts/efficiencies, paid conversions, primary-fuel coverage and hourly keys were checked using the actual cached files. That export still reports a missing electricity-demand profile when its download was skipped. Process-industry verification additionally reconciled Croatian calibration and checked Croatian/Hungarian inputs through the actual model adapter; the full Croatian reader was exercised. Italy's plant-table pipeline generated 1,073 individual rows. These are bounded tests documented in local `validation/*.json`; they do not certify a complete national optimization.

Run relevant checks after a change rather than treating this count as permanent:

```powershell
python -m unittest discover -s tests -v
python preparation_dependencies.py
python validate_model_inputs.py --bundle outputs_IT/model_inputs --industry-mode categories --efuels
```

A publication should report the archived input bundle and hashes, command/settings, assumptions, source years, coverage/fallback warnings and a separate model-solution quality report. Cite the datasets used and the model formulation, not just the preparation interface.
