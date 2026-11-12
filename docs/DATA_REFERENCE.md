# Input, output and units reference

**Applies to:** the preparation repository and the documented H2RES local model, 12 November 2026. This chapter explains the core contracts; machine-readable inventories include every examined workbook sheet/header and native CSV header.

## 1. Complete schema inventories

| Inventory | Contents |
|---|---|
| [workbook_schema.csv](inventory/workbook_schema.csv) | All examined workbook/sheet names, stored dimensions and exact first-row headers; blank/duplicate headers preserved |
| [model_workbooks.json](inventory/model_workbooks.json) | Sheet-name lists for all live model workbooks |
| [csv_schema.json](inventory/csv_schema.json) | Exact headers for each native CSV |
| [model_data_files.csv](inventory/model_data_files.csv) | All examined data files, sizes and SHA-256 digests |
| [preparation_cli_options.csv](inventory/preparation_cli_options.csv) | Argument names, source defaults/choices/help and line positions for runner and sector CLIs |
| [model_configuration.csv](inventory/model_configuration.csv) | Entered source configuration assignments |
| [workbook_reference_urls.csv](inventory/workbook_reference_urls.csv) | Reference URL occurrences with workbook/sheet/cell context |

Some workbooks omit stored worksheet dimensions; their row count is marked unknown in the inventory rather than invented. Header inventories describe the files examined, not an assurance that all retained historical variants are active. Rows/columns can differ in another release.

## 2. Common keys and calendar

| Field | Meaning and rule |
|---|---|
| `System` | Model system label; often ISO2 country, but can be a custom aggregate |
| `Zone` / `zone` | Model zone; capitalization is file-specific and significant |
| `country` | Source-country label in spatial mappings/provenance; it can differ from a merged System |
| `nuts3` / `NUTS3` / `nuts3_id` | Source NUTS3 geography; sector maps use documented aliases |
| `period` | One-hour model position, normally integer 1–8760 |
| `year` / year-named column | Planning/observation year according to table; not interchangeable with a weather year |
| `unit_name` | Technology/asset identifier; must match profile, cost and compatibility mappings |
| `Industry` | Exact native industry identifier, not arbitrary display text |
| `category` | Service/temperature class, separate from Industry |
| `branch`, `component` | Complex-industry product branch and useful-service component |
| `include_in_the_model`, `active`, `CC_active` | Table-specific inclusion flags; inclusion does not itself create missing demand or source data |

Hourly records with long geography need unique `(System,zone,period)` keys. Wide power profiles need unique `period` and matching unit-name columns. Different files use different index orders internally; never infer an operational dictionary key order from a superficially similar variable. The native transport primary-fuel dictionary, for example, starts with physical fuel.

## 3. Units and conversion discipline

| Quantity | Normal basis | Frequent mistake |
|---|---|---|
| Electrical/thermal power | MW | Treating MW as annual MWh |
| One-hour flow | MWh per one-hour interval, often numeric MW | Multiplying by 8760 twice |
| Annual energy | MWh/year; sometimes source GWh/ktoe | Confusing 1000 MWh/GWh with 11630 MWh/ktoe |
| Storage power | MW | Using an energy-capacity cost |
| Storage energy | MWh, or native GWh converted explicitly | Confusing stock with throughput |
| Fuel input | Carrier MWh, usually lower-heating-value energy conventions | Applying useful-service efficiency a second time |
| CO2 flow/capture capacity | tCO2/hour | Treating as tonnes of stored inventory |
| CO2 stock | tCO2 | Applying MW-based CAPEX |
| Product activity | Tonnes or explicit index units | Labelling an index as tonnes |
| Fleet | Continuous vehicle-equivalent counts | Assuming discrete integer purchases |
| Capital cost | MEUR per native capacity unit | Applying MEUR/MWh to MW or €/vehicle without conversion |
| Variable cost | EUR/MWh or declared physical input basis | Counting purchased feedstock at multiple conversion stages |
| Fixed OPEX | MEUR per capacity-year or configured fraction | Treating a source annual rate as upfront CAPEX |
| Terminal capacity | TWh/year in standalone terminal workbook | Treating as tank energy capacity |

For JRC industry extraction, `1 ktoe = 11630 MWh` is the implemented conversion. `1 GWh = 1000 MWh`; `1 TWh = 1000000 MWh`; `1 MEUR = 1000000 EUR`. Currency labels do not by themselves identify a price year or inflation basis. Record those separately where source metadata provide them.

## 4. Native technology and policy workbook families

| Mode | No e-fuels | E-fuels |
|---|---|---|
| Regular industry | `flex_tech.xlsx` | `flex_tech_efuel.xlsx` |
| Category industry | `flex_tech_categories.xlsx` | Conservative: `flex_tech_efuel_categories.xlsx`; technical: `variants/technical_2050/flex_tech_efuel_categories.xlsx` |
| Complex industry | `flex_tech_complex_industry.xlsx` | `flex_tech_efuel_complex_industry.xlsx` |

Category/complex flags are mutually exclusive. Other retained filenames, including combined category/complex variants and copies, are archived alternatives rather than an instruction to activate them together. Regular and complex technology files can be paired with case-specific process workbooks as described below.

Policy uses `policy.xlsx` or `policy_efuel.xlsx`; e-fuel carrier prices use `policy_fuels.xlsx` where enabled. Read the active path printed/selected by the model, not the workbook whose filename happens to be open in Excel.

## 5. Electricity and hydro files

### 5.1 `generators.csv` / prepared `power/GENCO.csv`

Power assets use the source's native GENCO columns, including `unit_name,cap_mw,max_cap,fuel_type,decom_start_existing_cap,life_time,decom_start_new,final_life_cap,efficiency,cost_no_fuel,RampingCost,CO2Intensity,technology,RampUpRate,RampDownRate,CHPType,STOCapacityGWh,STOSelfDischarge,STOMaxChargingPower,STOChargingEfficiency,CHPPowerToHeat,CHPPowerLossFactor,CHPMaxHeat,System,Zone` in the examined native CSV.

`cap_mw` is installed power, `max_cap` a capacity ceiling where used, and storage energy is explicitly GWh in this native representation. A detailed intermediate can instead contain `STOCapacity` in MWh and extra coordinates/NUTS fields; use the exporter conversion rather than copying it directly into the native file. `CO2Intensity`/non-fuel costs must be interpreted on the reader's generation/CHP-equivalent basis, not assumed to be raw fuel factors.

### 5.2 Profiles

| File | Shape | Meaning |
|---|---|---|
| `electricity_demand.csv` | `period,Power,System,Zone` | Baseline electric load in MW |
| `renewable_availability.csv` | `period` plus exact generator names | Fractions for VRE and run-of-river |
| `hydro_inflows.csv` | `period` plus exact HDAM/HPHS names | Normalized inflow convention expected by reader |
| `electricity_prices.csv` | Hourly/zone price columns in examined input | Selected trade/electricity price assumptions |
| `import_prices.csv` | Native import-price long format | Price input according to selected cost path |
| `outside_system_normalized_curves.csv` | Outside-source/period curve fields | External source availability patterns |
| `outside_system_supply_shares.csv` | System/source/share fields | Mix for external availability calibration |

Profiles must match the canonical inventory's unit naming and aggregation. Plant/source mapping and curve-quality CSVs are part of the preparation evidence. Do not rename plant rows without updating their curves and cost/investment keys.

## 6. Shared technology workbook sheets

### 6.1 Geography and networks

`active_zones` identifies active `(zone,System)` combinations. `keys_links`, `keys_borders`, transmission and outside-link sheets establish which modeled and external endpoints exist. Input files may retain inactive countries and templates. Only valid active mappings should contribute to a run, but inherited network/policy assumptions still require review.

### 6.2 Generic flexible technologies

`flex_tech` contains assets with fields such as installed/maximum capacity, annual build limits, efficiency, electric auxiliary demand, lifetime/retirement, reserve contributions, input/output carriers, storage linkage, System/zone and activity flags. `Tech_type` and carrier fields determine how a row is interpreted; identical-looking numeric `cap_mw` fields in different asset classes should not be assumed to mean identical delivered services.

### 6.3 `tech_cost_years`

The first column identifies year; technology/component keys are columns. Values follow each asset's documented capital-capacity basis. Complex component costs use `component_unit_name` keys, with generic donors only when explicitly recorded. Interpolated/mapped data are not all direct quotes for that component.

For the active workbook, the optional `literature_fixed_opex.csv` links annual maintenance rates to workbook, technology, year, native capacity unit, conversion and source references. Its `source_cells`, `source_sheets` and `source_price_years` should accompany a cost audit. A match is specific to the chosen workbook/version; source references alone do not prove every row has been applied.

## 7. Ordinary/category industry inputs

### 7.1 Equipment tables

`Industry_data` includes System/zone, Industry, optional category, `unit_name`, physical `fuel_type`, group, efficiency, inclusion, capacity, initial service share, maximum service share, lifetime/decommissioning, CO2 information and scalar/annual build limits. Category profiles must use exactly the same native sector/category identifiers.

`simple_industry` represents a pooled remainder rather than an additional copy of selected detailed sectors. It must be recalculated when the detailed inclusion selection changes. `industry_CC` is the dedicated capture authority where used. `industry_heat_stor` exists only in variants supporting category industrial thermal storage.

### 7.2 Demand profiles

`industry_heat.csv` contains `period,System,zone` plus sector service demands. Despite the historical filename, full native service demand includes relevant non-heat components. `industry_category_profiles.csv` uses names such as `Iron_steel[100_400C]` and includes `NON_HEAT` where generated. `industry_electricity.csv` is wide by model zone and records the baseline electricity associated with the chosen source convention.

The legacy `heat_demand_industry.csv` can be process-heat-only; do not use it as the full native file merely because its name sounds appropriate.

## 8. Complex industry workbooks

Possible native names are `industry_complex.xlsx`, `industry_complex_efuel.xlsx` and their `_electricity_technical_2050.xlsx` variants.

| Sheet | Key fields | Interpretation |
|---|---|---|
| `complex_industry` | System, zone, Industry, branch, component, unit_name | Process-equipment alternatives and observed/assumed fuel parameters |
| `Process_data` | System, zone, Industry, branch, component | Useful-service/product intensity and independent process emissions |
| `Product_demand` | System, zone, Industry, branch, year columns | Annual product activity in declared unit |
| `CC` | System, zone, Industry, branch | Branch-level capture/reboiler/storage assumptions |
| `JRC_source_cells` | Sector/branch/component/fuel/year | Source observations and exact useful/final/emission addresses |
| `industry_heat_pumps` | Unit/class | COP, sink temperature, lifetime and cost assumptions |
| `Methodology` / screening/provenance tables | Descriptive keys | Source/version/assumption explanations; runtime tables remain authoritative |

### 8.1 Critical process fields

`activity_unit` and `product_unit` must agree within a branch. `energy_intensity_MWh_per_activity` and `process_CO2_t_per_activity` are authoritative generic intensities. Legacy `_per_t` fields are suitable only for physical product tonnes. `reference_activity` is the observation basis. `activity_factor` modifies activity-to-service conversion and must not be applied twice.

`historical_process_CO2_*` preserves observed history; `excluded_H2_reforming_CO2_*` records the guarded Croatian accounting exception; modeled `process_CO2_*` is the remaining additional process term. `combustion_CO2_t_per_MWh` is observed final-fuel combustion, distinct from the legacy pure-fuel `CO2Intensity` and from product process intensity.

`fossil_waste_final_energy_share` applies to the mixed biomass/waste final-energy stream. `source_waste_split` must distinguish exact single-class evidence from assumed sector blends. A positive observed fossil combustion factor cannot be erased because a row is named Biomass.

`hp_below60_share`, `hp_below80_share`, `hp_below125_share`, `hp_below150_share` and `hp_source_heat_share` are shared eligibility/source budgets. They are fractions of useful service, not individual independent technology potentials that can simply be added.

### 8.2 Industry identifiers

The source maps JRC ISI, NFM, CHI, NMM, PPA, FBT, TRE, MAE, TEL, WWP and OIS into the eleven exact model labels listed in the preparation manual. The spelling `Not_elsewhere_specified_(industry)` and legacy branch key `cemment` are intentional compatibility identifiers. Correcting display spelling inside keys without migrating dependent inputs breaks joins.

## 9. Transport tables and profiles

`transport_all` identifies sector, equipment, type, demand/load coefficients, primary efficiencies, stock counts, maximum stock/share, storage/charging, retirement/lifetime, grid efficiency and inclusion, plus year-based investment/share fields according to variant. The extended e-fuel workbook contains persisted `compat_*` and parent/conversion metadata.

Names such as `total_load`, `number`, `tot_num`, `efficiency_primary`, `max_share` and year columns must be read together with the selected native transport method. `total_load` is a service/demand coefficient, not a universal electrical-MW field. Annual activity normalization and stock-derived coefficients determine its physical interpretation. Source table and reader equations are the authority for road versus marine/rail proxy classes; a column name alone is insufficient for a cross-sector conversion.

`transport_ICE_prim` maps primary/secondary fuels and efficiencies/shares to the applicable engine/service rows. `compat_parent` permits inherited availability for converted equipment. Paid upgrades start with no independently observed additional stock; their conversion/cost recipes are template assumptions.

Shipping source aliases use the native route keys consistently across equipment, compatibility lookup and hourly profile headers: `ICE_MARINE_DOM` → `ICE_MARINE_SHORT` (`Domestic_shipping`) and `ICE_MARINE_INT` → `ICE_MARINE_LONG` (`international_shipping`). The source service quantities and initial stocks are retained. Both newly prepared files and cached legacy files passed through export use this normalization; simultaneous legacy/current profile columns are rejected as ambiguous.

| File | Values |
|---|---|
| `transport_demand.csv` | `period,zone,System` plus service activity shares, normally normalized to annual total 1 |
| `transport_profiles.csv` | `period,zone,System` plus equipment/parent plug-in availability fractions |

Fleet, service shares, fuel volume shares and fuel energy shares are different. Use the documented density/LHV/efficiency conversion in the pathway method rather than interpreting a volume percentage as an energy percentage.

## 10. Heating, DH, solar and cooling

Prepared technology tables are `flex_tech_heat`, `flex_tech_DH`, `thermal_tech`, `thermal_tech_DH`, `solar_indv` and `solar_DH`; storage sheets exist according to variant. Electricity/capacity and delivered-heat units must follow the class-specific reader. Heat-pump COP is not a boiler fuel efficiency.

`heating_individual.csv` and `heating_district.csv` are wide by model zone with `period`. `heating_electricity.csv` is the associated baseline electric demand. `solar_thermal_availability.csv` has zone/technology series according to the native reader. Cooling has separate individual/district files; their presence in the template does not imply they were freshly generated or enabled in a run.

## 11. Hydrogen, e-fuels, primary supply and capture

The selected flex workbook contains enabled e-fuel conversion, feedstock, primary-energy, trade, storage and network sheets. The exact sheet set is in the inventory because retained variants differ. Technology input/output recipes use carrier-specific energy or material units. Source notes and cost aliases are part of the contract.

Standalone terminals use `h2_terminals.xlsx`:

| Terminal asset field | Unit/meaning |
|---|---|
| `cap_TWh`, `max_cap_TWh` | Annual terminal throughput capacity, TWh/year |
| `max_new_TWh_per_year` | New annual-throughput capacity allowed per calendar year |
| `loss` | Fractional handling loss |
| `el_MWh_per_MWh` | Handling electricity per H2 throughput energy |
| `var_EUR_per_MWh` | Handling cost per throughput energy |
| `life_years`, `existing_remaining_life_years` | New/existing lifetime inputs |
| `fixed_opex_pct` | Asset-specific annual maintenance fraction where present |

Shipping-route fields include origin/destination, `delay_hours`, `cargo_MWh`, departure interval/offset and ships en route. A terminal row alone does not define an internal corridor. The workbook is an aggregate H2 representation and does not declare a separate ammonia vessel/cracker model.

Capture fields include `CC_cap`, capture electricity, capture rate, reboiler capacity/stripper heat and optional tank capacity. Their annual build limits have different units and cannot all be scaled as MW. Carbon-source tagging and allowed geological storage follow the chosen model switches, not merely the existence of a CC row.

## 12. Annual investment limits

| Asset / field prefix | New capacity allowed per calendar year |
|---|---|
| Industry `max_inv_period_YYYY` | MW useful-service equipment capacity |
| Industry heat-storage `max_inv_period_YYYY` | MWh storage energy |
| `CC_max_inv_period_YYYY` | tCO2/hour capture capacity |
| `Reboiler_max_inv_period_YYYY` | MW reboiler capacity |
| `Tank_stor_max_inv_period_YYYY` | tCO2 intermediate inventory capacity |
| Generic asset or generation tables | Their declared native capacity basis |
| Transport/year fields | Native vehicle/service investment convention; inspect sheet and active flag |

The year-specific cell takes precedence. Blank/missing annual cells fall back to the matching scalar. If that is also blank/missing, the limit is unrestricted. Zero is a binding prohibition on additions. Limits are not interpolated merely because future years are sparse.

The model sums calendar-year allowances over the global decision interval; the initial decision uses its own year. Installed stock and an annual build rate are not the same number. A total capacity limit and an annual build limit can both bind. Capture table precedence and sharing across categories prevent multiplying one physical branch capture budget by category count.

## 13. Policy tables and scenario JSON

`setup` holds the modeled years and first-row controls (`chunk_size,step_size,first_hour,last_hour`). Other policy sheets can hold RPS, CO2 limits, fuel/import/carbon prices, transport technology floors, biomass supply limits, generation calibration, hydro caps and outside trade targets. Exact names/headers are in the schema inventory. Many policy rows are System-scoped, not country-independent constants.

The separate preparation adapter's scenario JSON supports `preset,scope,years,start_year,end_year,year_step,target_year,start_share,investment_multiplier,investment_overrides`. Native `main.py` does not automatically load this JSON. Preparation CLI choices override corresponding JSON fields. Years are increasing/equally spaced and must be supported by costs. A whole-energy RES preset requires the e-fuel representation and a compatible model adapter; this documentation did not certify the adapter against all 12 November extensions.

Investment overrides select supported sheets, a native column, value, optional row conditions and years. Unsupported sheet names are errors. A reference to `Industry_data` is not automatically an override of the separate `complex_industry` workbook. The supported complex multiplier can scale its build limits; use documented direct editing for unsupported per-row complex changes.

## 14. Manifests and evidence files

| File | What it establishes |
|---|---|
| `model_reference/manifest.json` | Template origin, captured file/source-reader hashes |
| `model_inputs/bundle_manifest.json` | Prepared sectors, countries, chosen variants, replaced sheets, template-retained inputs and reported repairs |
| `model_inputs/validation.json` | Implemented key/schema/hour/profile/zone coverage checks |
| `model_inputs/scenario.json` | Requested future policy and integration assumptions |
| `complex_generation.json` | Process sources, allocation, case, cost donors, profile basis and limitations |
| `source_reconciliation.csv` | Source-to-generated energy/emission closure for selected observation bases |
| `reference_calibration_diff.csv` | Matching HR1 process-equipment differences for the defined comparison fields |
| `scenario_reader_validation.json` | Separate actual-model input-reader check, if explicitly performed |
| `validation/*.json` | Bounded development verification; read its scope and timestamp |

## 15. Minimum review before handing inputs to H2RES

Check requested geography against active/generated keys, unique hourly periods, matching unit/profile names, full sector/year coverage, useful/final-energy distinctions, scenario investment units, non-energy feedstocks, process/combustion carbon separation, finite efficiencies and stock/cost bases. Inspect warnings about fallback allocations and retained reference rows. Preserve the raw data and exact hashes so the handoff can be reproduced.

The model will also require consistent flag selection and any separately implemented whole-energy policy equations. Structural input compatibility is an interface property; historical accuracy and scenario feasibility require additional review.

## 16. New product-industry input contract

`data/simple_industry.xlsx` is read only when `model_simple_industry=True`. It is unrelated to the pooled-remainder worksheet of that name inside a flex-tech workbook. The product mode disables overlapping legacy industry/transport, e-fuel, hydrogen and industrial capture/storage blocks. Active example zones are configured separately in model policy.

| Worksheet | Principal quantities / purpose |
|---|---|
| `plants` | Fixed product/route/geography, t/h capacity, MWh/t electricity, MW connection, operating years, flexibility and capital |
| `inputs_per_tonne` | Non-electric GJ/t recipes, emissions tCO2/GJ; avoid duplicate coke/process carbon |
| `economics`, `fuel_prices` | Plant/year economics and fuel/year EUR/GJ |
| `markets`, `market_years` | Eligibility and mandatory/optional markets; annual tonnes, sale/delivery costs and hourly ceilings |
| `carbon_policy` | Plant/year industrial price, benchmark, allocation and credits |
| `import_suppliers`, `import_years` | Outside origin/eligibility and year-specific supply limits, prices, embedded footprints and credits |
| `trade_routes` | Optional enabled supplier/market pairs with delivery costs and hourly limits |
| `profiles` | Named full-year profiles; `flat` is built in |
| `baseline_load` | Explicit year-specific MWh to remove from basic electricity before adding product-industry consumption |
| `metadata` | Example/calibration status, boundaries and provenance |

The example contains illustrative BF-BOF/EAF plants, mandatory domestic/Europe product demand and bounded outside offers. Zero baseline removals mean added electricity demand. Every modeled plant/year, market/year and required fuel/year needs its corresponding input row. Read the [supplied module notes](model_notes_2026_11_12/SIMPLE_INDUSTRY.md) and exact headers in the schema inventory before changing these inputs.

## 17. DSM parameters and additional output contracts

Basic-electricity DSM uses `main.py` switches and `policy/runtime_policy.py` parameters; it does not require a new DSM input workbook. Defaults are documented in model manual section 19 and the [supplied DSM notes](model_notes_2026_11_12/ELECTRICITY_DSM.md). The energy fractions, hourly power cap, rollout and costs are explicit scenario assumptions.

DSM results include `dsm_hourly_YEAR.csv`, `dsm_classes_YEAR.csv`, `dsm_summary_YEAR.csv` and `dsm_assumptions.json`. Product-industry results include hourly production, fuels, sales, markets, summary, imports, demand, fiscal and border-carbon tables. Geography, year, physical/embedded carbon and annualization must be read with their recorded boundaries. These result names describe enabled module outputs, not files created while writing this documentation.

## 18. Formula caches and workbook handling

The screenshots deliberately show stored formulas. The inventory's cached-value read does not recalculate Excel formulas and is not a formula-validity audit. Inspect both formulas and numeric values when editing `Industry_data`, `_remainder_calc`, `simple_industry`, annual limits or dependent policy tables. Preserve the workbook, sheet names, header rows and native stacked-table layout. For missing or stale cached results, recalculate a working copy in a spreadsheet application and verify its saved values with the model reader.

The 12 November model also supplies read-only checking instructions in `data/README.md`, including `python -m scripts.repair_flex_workbooks data/flex_tech_efuel_categories.xlsx --check`. Read that helper's options before using a repair mode. No repair or recalculation was performed as part of this manual update.
