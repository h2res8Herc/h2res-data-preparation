# H2RES model manual

**Documented model:** `D:\POSAO\H2RES_12.11.2026`. **Documentation edition:** 12 November 2026. The [source/version inventory](inventory/documented_version.json) identifies the exact files reviewed. The model is separate from the data-preparation interface.

The expanded [mathematical formulation](MATHEMATICAL_FORMULATION.md) supplies 62 numbered equations with source anchors and physical interpretation. Use the [main configuration guide](MAIN_CONFIGURATION_GUIDE.md) for detailed workflow/combination instructions and the [complete option reference](MODEL_OPTION_REFERENCE.md) for every recorded main/policy setting. The equations below retain the original narrative overview and complement the more detailed formulation chapter.

## 1. Model purpose, lineage and scientific use

H2RES is used to study integrated energy systems and transition pathways across electricity, heat, transport, hydrogen and other energy carriers. Its historical island-energy modelling lineage and the later optimization formulation are distinct developments. The 2004 island study and the 2022 planning formulation are appropriate background references; the newer local code contains additional processes and workflows that those articles do not document [R01](REFERENCES.md#r01), [R02](REFERENCES.md#r02).

The formulation examined here is a linear investment-and-operation model implemented in Python with Gurobi. The static inventory of active runtime source files found continuous variable declarations, including the `_add_vars` wrapper. Vehicle numbers may therefore be fractional optimization quantities; they are not automatically integer purchase decisions. A fuel called a binary choice in ordinary language does not imply a binary solver variable. Confirm the constructed model if additional user modules are added.

The model minimizes a configured economic objective subject to physical, stock, investment, service, network, resource and policy constraints. It can help compare pathways under alternative assumptions. It does not discover future policy targets, determine a unique forecast, prove causation in a real market, or by itself establish full lifecycle sustainability. Published H2RES applications are examples of model use, not a validation certificate for this source snapshot [R03](REFERENCES.md#r03), [R04](REFERENCES.md#r04).

## 2. Architecture and execution flow

### 2.1 Main runtime files

| File | Responsibility |
|---|---|
| `main.py` | Working directory, scenario name, feature flags, file selection, caching, planning/dispatch execution and exports |
| `policy/model_policy.py` | Entered economic, transition, resource and policy assumptions |
| `policy/runtime_policy.py` | Numerical tolerances, sampling, solver and recovery settings |
| `policy/transport_pathways.py` | Transport conversion/compatibility assumptions and default migration values |
| `scripts/read_process_data.py` | Reads/scopes input tables, constructs sets/dictionaries, annual limits and processed demand |
| `scripts/reading_prev_and_vars_def_dual_industry_categories1.py` | Loads historical decisions/stocks and declares optimization variables |
| `scripts/Build_model_dual_industry_categories_named_debug.py` | Core physical/policy constraint construction |
| `scripts/CAPEX_OPEX_Gurobi_settings_dual_industry_categories1.py` | Economic expressions, objective, solver configuration, optimization and recovery |
| `scripts/complex_industry_support.py` | Validates/adapts process activity and replaces selected ordinary industry services |
| `scripts/industry_annual_s_curve.py` | Demand-weighted adoption envelopes and shared electric-service transition policies |
| `scripts/transport_pathways.py` | Fuel compatibility, paid conversion pathways and stock/energy links |
| `scripts/energy_accounting.py` | Shared CHP fuel-equivalent and refinery physical accounting |
| `scripts/physical_solution_audit.py` | Physical-unit checks for solutions and history |
| `scripts/run_stage2_rolling_dispatch.py` | Rolling operational checks with fixed stage-1 capacities |
| `scripts/export_plot*.py` and `combine_plot.py` | Investment/history exports, balances, summaries and visualizations |

Scripts are executed in a shared namespace through `exec_script`. A variable can therefore be created by a reader/helper and consumed later without a conventional function argument. Configuration provenance must include the imported policy modules as well as `main.py`. Static code review must account for this execution pattern.

### 2.2 Runtime sequence

```text
main + three policy modules
    -> select technology/policy/profile files
    -> read and normalize inputs
    -> choose planning/dispatch mode and time grid
    -> load previous accepted investment/stock history
    -> declare variables
    -> build balances and constraints
    -> define costs/objective and solve
    -> check solution/status/physical quality
    -> export accepted results and historical handoffs
```

A separate data-preparation run stops before the model sequence above. Its optional bundle launcher configures the separate model in memory, redirects data paths and inserts the whole-energy renewable constraints before solving. The original model's `main.py` does not automatically read the preparation GUI settings.

## 3. Exact configuration and precedence

`main.py` changes its working directory to its own model directory, then executes the three policy modules in its namespace. It subsequently sets feature flags and derives file names. Reader/workbook settings supply additional numerical inputs. A preparation-bundle adapter can override selected flags and data paths at its supported execution boundary. The resulting precedence is contextual rather than a single universal JSON configuration layer.

The [configuration reference](CODE_REFERENCE.md) lists source assignments and line positions. Values described below are the examined local snapshot, not universal H2RES defaults. Historical README files include other scenario names and mode selections.

### 3.1 Observed local selection

The reviewed `main.py` uses scenario name `industry_CC_5y`, `Myopic=True`, `partial_perfect_foresight=False`, heating and transport/industry enabled, e-fuels enabled, category industry enabled and complex industry disabled. Category electricity is `conservative`, industrial category storage is enabled, and industry fuel-share/S-curve controls are enabled. Solar individual/DH heating and cooling switches are disabled in this snapshot; model availability and a currently enabled option are different matters.

The snapshot also has transport pathway corrections/electrification/share ceilings enabled, standalone H2 transmission and standalone terminals disabled, and `disable_transport_infrastructure=False`. Transport infrastructure is therefore not suppressed by that debug switch. Product based simple industry and both daily/weekly electricity DSM are disabled in the delivered selection; they are documented in sections 19 and 20.

### 3.2 Mutually exclusive or dependent modes

Category and complex industry are alternatives. Complex mode requires transport/industry and cannot use the legacy single-sector industry option. Category industrial storage requires category mode. Standalone hydrogen pipelines are disabled when e-fuels handle carrier transmission. Standalone H2 terminals use a separate non-e-fuel implementation. Oil/gas product supply depends on e-fuels. These guards are executed, not merely suggestions.

The model policy defaults complex sector selection to `Non_metallic_minerals`; preparation may generate all eleven sectors. An exported selection must be applied explicitly in the model configuration or supported adapter. Otherwise a workbook containing all sectors can still run only the selected subset.

### 3.3 Input workbook selection

Technology file selection follows regular/category/complex and e-fuel flags. Category e-fuel conservative mode now selects `data/flex_tech_efuel_categories.xlsx`; its technical alternative selects `data/variants/technical_2050/flex_tech_efuel_categories.xlsx`. Complex electricity variants select the corresponding `industry_complex*_electricity_technical_2050.xlsx` process workbook while retaining their normal flex-tech filename. Categories and complex industry are alternatives. See the [visual user guide](H2RES_USER_GUIDE.md) and [data reference](DATA_REFERENCE.md) for the exact mapping.

## 4. Spatial and temporal representation

Let s denote a model System, z a zone belonging to it, y a modeled decision year, t an operational period, g a generation asset, k another technology, f a carrier, i an industrial service/process and a an investment vintage. Assets and flows are created for active mappings; country names elsewhere in a workbook do not imply active modeled systems.

The full input calendar is normally 8,760 hourly positions. Operational subsets and representative weights depend on mode. A constraint using `_periods_for_year(y)` need not cover the same periods in every optimization year. Temporal metadata must be exported with results.

### 4.1 Perfect foresight

With `Myopic=False` and the applicable mode switches disabled, the model jointly chooses investments and operations across the modeled horizon. It knows the deterministic future input trajectories provided to it. Perfect foresight is an information assumption, not a claim that actual planners possess those forecasts.

### 4.2 Myopic planning

With `Myopic=True`, overlapping windows are built from the planning grid and setup controls. The model solves a window, accepts/exports its decision-year results, and carries historical decisions into later windows. Already accepted years are not reoptimized as freely as future years. New scenario names and coherent histories are necessary after material changes to costs, units or policies.

### 4.3 Partial perfect foresight

This mode combines detailed current-year operations with sampled future-year operations in each myopic solve. Future samples guide current investment, but they are not an independently validated full-year dispatch for those future years. The current source uses explicit per-year period sets and sparse variable creation. Read the configuration snapshot for representative-day settings; do not assume all years in a chunk contain 8,760 variables per asset.

### 4.4 Representative capacity planning and two-stage operation

Representative-capacity mode can sample configured weeks, with weights representing the full year. Lightweight mode exports only the capacity stage. Two-stage mode can subsequently export a fixed-capacity dispatch bundle and perform rolling operation. These approximations have different abilities to represent storage chronology, seasonal scarcity and ship arrivals. A representative-week optimum does not prove that a full chronological year is feasible.

### 4.5 Rolling dispatch

Rolling mode advances through operational windows with capacity fixed from a stage-1 bundle. It carries stocks, relevant fuel/terminal states and guidance into subsequent windows. Resume and stitching options can reuse accepted window files. Review terminal conditions, guidance penalties and automatic slack settings; they can relax a pure hard-feasibility interpretation.

## 5. Mathematical notation and decision variables

The following equations summarize implemented families. Asset-specific dimensions, history maps and flag branches are suppressed. The [code reference](CODE_REFERENCE.md) and machine-readable call inventories give executable locations and conditional context.

| Symbol | Meaning | Typical physical basis |
|---|---|---|
| X(k,z,s,y) | New capacity decision | MW, MWh, vehicles, tCO2/h or another explicitly declared asset unit |
| K(k,z,s,y) | Available installed capacity | Same unit as the asset's capacity |
| P(g,z,s,t,y) | Electricity generation | MW for one-hour periods |
| Q(k,z,s,t,y) | Delivered heating/industrial service | MW useful heat/service |
| U(f,k,z,s,t,y) | Carrier/fuel input | MWh of carrier per hour |
| E(k,z,s,t,y) | Storage stock | MWh, tCO2 or other carrier stock unit |
| C,D | Storage charging/discharging flows | MW or corresponding hourly carrier flow |
| N(v,z,s,y) | Transport stock | Continuous vehicle-equivalent count in the LP |
| F(f,z,z',t,y) | Carrier transfer | MW-equivalent flow |
| H(i,z,s,t,y) | Industrial delivered-service demand | Useful MWh per hour |
| A(b,z,s,t,y) | Product activity | Tonnes or index-activity units per hour |
| w(t,y) | Representative period weight | Represented hours |

Variable bounds and scales differ by family. Scaled transport variables have physical-value wrappers; numerical solver column values must be converted back before comparing with raw vehicles, stock or energy data. State and investment symbols in this manual denote physical quantities.

## 6. Economic objective and investment accounting

### 6.1 Objective implemented in this source

The production objective has the following structure, in million currency units before an explicit solver scaling factor:

```text
min  sum_(y,z,s) DF(y) × [CAPEX_year(y,z,s)
                         + multip × fixed_OPEX_year(y,z,s)
                         + variable_OPEX_MEUR(y,z,s)]
     + rolling_carbon_slack_penalty
     + rolling_terminal_fuel_SOC_slack_penalty
     + stage2_quantity_guidance_slack_penalty
```

`DF(y)=(1+discount_rate)^(-(y-discount_base_year))`. The reader defines `multip=(max(years)-min(years)+1)/len(years)` for its solve grid. Variable-OPEX expressions also apply the configured annualization/multiplier and EUR-to-MEUR conversion. Those exact conventions matter on sparse decision-year grids. They must not be replaced in a report by an unexplained sum over every calendar year or by a different textbook objective.

The examined policy has discount rate 0.05, discount base year 2025, capital finance rate 0.05 and numerical objective scale 1000. Numerical scaling is intended to change conditioning, not physical economic units. Read exported objective/cost variables consistently with that scale.

### 6.2 Capital service and vintages

The cost script treats capital service as an annuity-due payment for each investment vintage. The first payment is in the build year, and payment continues while that vintage is within technical life. Its unit capital cost is the build-year cost, not each later year's learning-curve price. Payments after the modeled horizon are omitted under this accounting convention.

```text
annuity_due_factor(L,r) = 1 / sum_(n=0 to L-1) (1+r)^(-n)
annuity_due_factor(L,0) = 1/L
payment(vintage a, year y) is due when a <= y < a + lifetime
```

Costs may be MEUR per MW, per MWh of stock, per vehicle, per tCO2/hour or per terminal TWh/year. Applying one unit cost to another basis can dominate the result while leaving the LP numerically feasible. The live source includes literature-linked annual fixed-OPEX data and generic/fallback technology mappings. Matched rows and fallback paths should be audited separately.

### 6.3 Operating costs, trade and penalties

Variable OPEX includes the appropriate fuel/commodity purchases, non-fuel operation, ramping, external trade and carbon charges, with special accounting for e-fuel recipes. Do not add a fuel bill a second time merely because its energy passes through several conversion assets. Revenue signs depend on import/export terms and market configuration. The code contains separate national/external-carbon options and fuel-specific prices; study documentation must identify the active option.

Unserved electricity, rolling heat/service shortages and selected guidance or carbon shortfalls can be penalized. These are scarcity/slack representations, not real zero-cost supplies. The configured electricity unserved-load cost is a scenario penalty, not a nationally estimated VOLL. A low objective obtained with nonzero slack must be reported as such.

## 7. Capacity, lifetime, decommissioning and build constraints

For an asset class, the general available-capacity relation is:

```text
K(y) = surviving_existing_capacity(y)
       + sum_a survival(a,y) × X(a)
```

Survival/retirement is asset-specific. Existing capacity uses remaining-life/decommissioning inputs; new vintages use technical life and the implemented retirement shape. Some families retain a final-life fraction. The exact helpers and history conventions should be used when interpreting the asset's investment CSVs.

Capacity may have a total ceiling and an annual build limit. They are different restrictions:

```text
X(y) <= sum_(c in investment_window(y)) annual_build_limit(c)
K(y) <= total_installed_ceiling(y)
```

Investment windows use the global decision-year grid. For endpoints 2025 and 2030, the first endpoint represents 2025 only and the next represents 2026–2030, including on resume. Blank annual limits use the legacy scalar if present; absent/blank scalar means unrestricted. Zero disallows additions but does not delete existing capacity. A period with an unrestricted year remains unrestricted under the relevant industry-limit reader. Negative/nonfinite supplied limits are rejected.

Generation-specific runtime build multipliers can further scale workbook limits. In the reviewed policy four Croatian wind/PV names have multiplier 2; that is a scenario configuration, not a universal country potential or model constant. Transport, terminal, capture and storage additions use their native physical units and may have separate active flags.

## 8. Electricity generation, networks and storage

### 8.1 Dispatch and renewable availability

Dispatchable output is bounded by available capacity and applicable technical constraints. Renewable output uses matching availability factors. Hydro run-of-river has flag-dependent equality/inequality behavior in the source. Curtailment or excess electricity is represented where enabled; do not assume every renewable MWh available must be delivered.

The principal electricity balance includes generators, fuel cells, relevant storage discharge, vehicle-grid services, net imports and an explicit unserved-load variable. Demand includes baseline electricity plus endogenous heating, industry, transport, electrolysis, synthesis/CC and storage charging, adjusted under the code's baseline conventions.

```text
generation + fuel_cells + discharge + delivered_imports + unserved_load
 = baseline_load + endogenous_sector_electricity + charging + exports + excess
```

The exact terms and signs are in `el_balance`. This is a zonal energy balance, not a full nonlinear AC network. Do not infer voltage, frequency, transient stability or N-1 security from hourly energy feasibility alone.

### 8.2 Network transfers

Primary/secondary links, outside links and carrier networks use input mappings, transfer capacities, losses and costs. One delivered-flow conversion appearing in the electricity balance uses `1/(1+distance_multiplier*loss)`; substituting a different loss formula in a methodology description would misstate this implementation. Outside-system availability can restrict imports/exports using hourly supply-share/curve tables.

Transmission duplicates can be resolved by the configured `first` policy. The log reports removed rows and conflicts. A deterministic rule does not prove that conflicting network data are correct. New country/system aggregation requires deliberate network and outside-trade calibration.

### 8.3 Electricity and generic storage

An illustrative physical stock relation is:

```text
E(t) = retained_stock(t-1) + eta_charge × C(t) × dt
                          - withdrawal_for_discharge(t) × dt + natural_inflow(t)
0 <= E(t) <= storage_capacity
0 <= C(t) <= charge_power_limit
0 <= D(t) <= discharge_power_limit
```

Efficiency may be applied to the stock transition or to the delivered balance depending on family; the source is the authority. Representative weights used for annual accounting are not automatically multi-hour storage transition durations. Initial/final/cyclic conditions can materially change apparent flexibility. The reviewed policy has `storage_year_continuity_mode="cyclic"`, with additional rolling/fuel boundary controls.

### 8.4 Hydro reservoirs and pumped storage

Hydro includes plant-specific turbine capacity, storage, inflow and pumping where applicable. Water-energy stock balances and available generation are constrained separately. Pumped storage consumes electricity when charging; it is not a new primary renewable source merely because its fuel label is Hydro. The source/profile year and reservoir assumptions need to accompany any annual generation interpretation.

## 9. Buildings, district heating and CHP

The heating block meets individual and district-heating service demand using enabled fuel boilers, electric heaters/heat pumps, solar heat, CHP and storage. Each class has capacity, efficiency/COP and investment/retirement constraints. Cooling is a separate optional representation and is disabled in the examined selection.

For a boiler or heat pump, the conceptual conversion is `useful_heat = efficiency_or_COP × input_energy`. COP above one represents heat transfer from an external source. It is not electricity generation. Heat-source constraints, DH integration and storage options must be accounted for when comparing technology outputs.

CHP is coupled production. The shared physical helper uses condensing-equivalent electricity `P + beta*Q`; its fuel input divides that quantity by electrical efficiency. That expression is used consistently for the relevant costs and emissions. CHP feasible operating regions additionally use input ratios/parameters. Treating CHP heat as cost/emission-free while retaining the full electric output would double-allocate the fuel benefit [R30](REFERENCES.md#r30).

Current heating policies include base-year plant heat calibration, annual limits on CHP heat change, electric/gas heating transitions, fossil-heat non-increase and an explicit boiler phaseout. The reviewed entered phaseout years are coal 2030 and gas/oil 2035; the source notes that CHP is excluded from that boiler rule. These are local scenario settings, not automatic national legislation. Solar and storage options remain subject to their switches.

## 10. Industry

### 10.1 Ordinary and category formulations

Industrial equipment supplies useful service while carrier demand depends on efficiency. Regular mode uses sector/service keys; category mode adds temperature/service categories. `NON_HEAT` is retained where applicable. Excluded detailed services can be represented in a pooled remainder with its own input row. The remainder must be consistent with selected detailed demand to avoid omission or duplication.

Initial useful-service shares, maximum shares, capacity and annual build limits interact. A maximum share is applicability, not a mandatory target. An investment ceiling does not change a fuel's compatibility with the process. An asset can be technically eligible but unable to expand quickly because turnover or adoption constraints bind.

### 10.2 Process/activity formulation

Complex industry replaces ordinary demand/technology rows only for its selected services. It uses branch product activity and component intensities:

```text
useful_service(i,t,y) = product_activity(branch(i),t,y)
                        × activity_factor(i) × energy_intensity(i)
process_CO2(branch,t,y) = sum_i product_activity(branch,t,y)
                                × activity_factor(i) × process_intensity(i)
```

Output can be tonnes or an index. The generic per-activity fields are authoritative. Process emissions are not added again as combustion of a non-energy feedstock. The adapter validates selected technology/process/product coverage, activity units, annual product demand, positive-service shares and heat-pump eligibility fields.

The supplied material convention treats non-energy gas/oil labels as H2-fed demand. That is a model convention rather than a universal chemical process representation. The Croatian ammonia exception and non-HR unresolved reclassification are documented in the preparation manual and assumptions register.

### 10.3 Fuel substitution budgets

The method distinguishes common low-enthalpy/steam/drying heat, process-specific heat, electrical/mechanical/cooling services, material feedstocks and reducing chemistry. Compatible substitute families include H2 and enabled synthetic fuels, with local/shared limits so the same replaceable pool is not repeatedly allocated without restriction. Biomass has a baseline-share ceiling, and lignin expansion is constrained to at most two additional percentage points of eligible local service in the supplied screening method.

These are replacement-equipment assumptions. They are not certification of blending in an unchanged incumbent burner. The authoritative latest fuel-compatibility handoff supersedes older zero-ammonia/narrow-hydrogen/unlimited-lignin comments [R20](REFERENCES.md#r20), [R21](REFERENCES.md#r21), [R22](REFERENCES.md#r22).

### 10.4 Adoption trajectories and S-curves

Demand-weighted annual fuel/electric-service adoption constraints are separate from hourly dispatch. Technology switching can be optimized hour by hour within the accepted annual transition and applicability envelope. The electric service share combines direct electric equipment and industrial HP service; it is not simply their electrical input fraction.

The reviewed S-curve policy uses an endogenous envelope with initial fraction 0.02, growth parameter 0.50 and reference milestones every five years. Shorter model steps interpolate toward those milestones so seeds/tolerances are not restarted every year. Directions can be explicitly increasing/decreasing by fuel, unit or asset tuple; gas/coal/oil/biomass directions are entered policies. These parameters are scenario choices, not nationally measured adoption rates.

### 10.5 Industrial heat pumps and storage

Industrial HP units share cumulative temperature and source-heat budgets. If eligible shares below 60, 80, 125 and 150 °C are cumulative, their sum is not independent addressable demand. The builder also respects source and service restrictions. Category industrial heat storage is a separate optional asset family; enabling it outside category mode is rejected.

## 11. Transport and fleet transition

Annual transport service is met by stocks of ICE, hybrid, electric and fuel-cell equipment in road, rail, shipping and aviation classes represented in the selected workbook. Service/activity profiles, fuel input, stock, battery availability and infrastructure constraints have different units and purposes.

The stock identity is conceptually:

```text
stock(y) = surviving_legacy_stock(y)
           + surviving_new_stock(y) + accepted_conversions_in(y)
           - retired_or_converted_out_stock(y)
```

Calendar aging and historical stock are explicit. The reviewed transport settings include turnover periods/ramp policy and maximum technology service shares. Some investment/rail-link/infrastructure switches are disabled in the local snapshot. Document those switches before interpreting an optimized transport pathway as an infrastructure plan.

ICE/hybrid primary-fuel recipes and paid upgrades use `compat_*` metadata. Drop-in hydrocarbons, FAME, alcohol blends, marine methanol/ammonia and pilot fuel have distinct configured paths. The source's default volume-share ceilings and retrofit premiums are screening assumptions; this documentation makes no claim that they constitute current legal approvals. Marine conversion parameters drawn from container-vessel literature are transferred to model proxy classes and require case-specific calibration [R25](REFERENCES.md#r25).

EV plug-in availability constrains charging/V2G opportunities. Minimum battery state and activity-derived travel energy restrict storage use. The model can couple EV batteries to the power system, but a country-level normalized profile is not a location-specific charging-network observation.

Transport solver scaling is handled by physical wrappers. Very small fractional legacy stocks and saved residuals can cause degeneracy or infeasible histories. The code cleans tiny numerical residue using configured tolerances and checks physical history; changing tolerances can affect acceptance and should be reported.

## 12. Hydrogen, electrofuels, feedstocks and terminals

### 12.1 Hydrogen

Electrolyzers consume electricity according to conversion efficiencies and available capacity. Steam reforming can use gas with associated costs/emissions. Fuel cells convert hydrogen back to electricity. Zonal H2 service includes applicable transport/industry demand, conversion/feedstocks, storage and network exchanges. The active balance and supply switches must be enabled together for a meaningful carrier accounting.

### 12.2 E-fuel conversion recipes

The e-fuel representation includes technology rows and recipes for enabled carriers such as H2, ammonia, methanol, synthetic methane, diesel, kerosene and other workbook fuels. Electricity, heat, CO2, nitrogen and upstream carrier inputs are coupled through the recipe fields. Generic form:

```text
input_j(k,t,y) = recipe_coefficient_j(k) × production(k,t,y)
production(k,t,y) <= available_conversion_capacity(k,y)
```

Energy-carrier inputs and material inputs have different units. Nitrogen and CO2 must not be counted as energy simply because they appear in a feedstock table. Recipe coefficients and output energy bases require explicit checking; do not infer a balanced reaction solely from labels.

Fuel inventory states, conversion capacities, commodity purchases and trade can interact. The current code has separate initial stock and boundary/continuity options. An initial storage fraction is an assumption about available inventory, not a free replenishable primary-energy resource.

### 12.3 Oil and gas product supply

An optional e-fuel-associated block represents extraction/imports, crude refining and product supply. The shared helper accounts for product energy and a configured refinery process-fuel share. The reviewed share is 0.08. Whether fossil products may be exported is separately configurable and can materially change economic incentives. Assess exports and process fuel in both energy and carbon balances.

### 12.4 Standalone H2 terminals

The separate terminal module is enabled in non-e-fuel mode by its terminal/H2-balance switches. Inputs come from `h2_terminals.xlsx`, with asset and shipping-route tables. Capacity is annual TWh/year, converted to an hourly limit using 8,760 hours. Loading, unloading, imports and exports share capacity; losses and handling electricity are charged on the appropriate flows.

This is aggregate delivered hydrogen. It does not separately model every port tank, vessel, liquefaction or ammonia-cracking process. Local H2 storage supplies buffering. Carrier-specific project calibration therefore belongs in the aggregate assumptions or an explicitly extended model.

Detailed internal shipping has departure schedules, delay, cargo size and fleet occupancy. Representative planning can use an instantaneous/average-capacity approximation. The source prevents departures that would arrive beyond the annual boundary; such cargo does not automatically cross calendar years. The terminal's standalone representation and e-fuel terminal representation should not be conflated.

## 13. Carbon accounting, capture and renewable policies

### 13.1 Emissions scope

The model separately accounts for power/CHP, heating, industry, transport, reforming and refining emissions where active. Combustion coefficients, process CO2 and capture/storage flows are not interchangeable. The physical electricity/CHP helpers and stream-specific industrial emission factors avoid particular double-counting errors, but a complete study still needs a stated system boundary.

The ordinary budget has the conceptual form:

```text
sum(enabled sector emissions) - credited geological_storage
 <= policy_CO2_limit + permitted_LULUCF_removal
```

Exact coefficients/scaling and alternate branches are in the carbon-limit rows. LULUCF can be disabled or parameterized. The code's CO2 energy-system accounting is not a comprehensive product lifecycle, upstream methane, land-use, N2O, ammonia-slip or biodiversity assessment. `non_CO2_polutants` is explicitly marked incomplete.

### 13.2 Capture and geological storage

Capture capacity, rate, heat/electricity demand, reboiler capacity and optional intermediate storage impose technical and economic constraints. `model_CC`, post-generation CO2 storage and e-fuel CO2 feedstock are different switches. One can retain parts of the e-fuel CO2 handling even when a broader CC setting is disabled.

The separated industry-process/other-carbon representation restricts which captured streams can enter geological storage. It is enabled in this snapshot through `separate_industry_process_carbon_balances=True`; `model_CC`, amine storage and post-generation CO2 storage are also enabled. `complex_industry_process_capture_required=False` leaves process-capture deployment to the applicable carbon and technical constraints rather than universally forcing it. Untagged imported CO2 does not automatically become a certified process stream. Reuse of CO2 in e-fuels should not be described as permanent sequestration.

### 13.3 Renewable electricity share

The native RPS policy constrains qualifying electricity generation/share according to the source's numerator/denominator definitions. It is not a universal all-energy renewable fraction. Reservoir/pumped-storage treatment, imports, curtailment and generation calibration must be interpreted consistently with the actual equations.

### 13.4 Whole-energy renewable preset from preparation

The preparation adapter adds stricter endpoint restrictions for the selected `res100`/`all-energy` scenario. At and after the target, it blocks fossil/nuclear energy use in covered generation, heating, industry and transport, relevant reforming/refining flows, unverified outside energy imports and imports through routes whose endpoints are outside the active model geography. It also prevents unserved electricity from serving as a zero-origin substitute.

Because generic stores lack a renewable-origin tracer, affected initial stocks are cleared at the target boundary; subsequent internally renewable stocks may carry forward. Material CO2/nitrogen remain separate. Mixed fossil-waste industrial streams are blocked under the conservative origin treatment. Earlier non-electric transition is chosen subject to the other policies rather than a claimed linear whole-energy renewable trajectory.

This policy is an energy-origin definition, not net-zero CO2. Biogenic sustainability, upstream lifecycle burdens and independent process emissions require separate decisions. Its current launcher supports the standard myopic/perfect-foresight workflows and rejects the unsupported whole-energy two-stage combination. Feasibility may be prevented by fixed processes, feedstock conventions, build rates or resource limits.

## 14. Policy calibration and scenario design

Scoped policy workbooks can contain generation targets, hydro caps, transport targets, biomass caps and outside trade calibration. Rows are selected by active System/zone and modeled years. Some calibration applies only to the global base year; resource caps can apply in every year. Calibration targets are not all equivalent to future investment opportunities.

Before creating a new national study, review demand forecasts, technology prices, currency/base year, lifetimes, reserves, resource potential, fuel/commodity availability, network/outside trade, heat-share policies, transport turnover, industrial compatibility and process routes. Automatically sourced historical data do not determine those future scenarios.

Use one coherent baseline and document each changed assumption. A suggested sensitivity matrix varies demand growth, resource potentials, grid expansion, storage chronology, external trade, capital/operating costs, industrial transition rates, biomass eligibility and renewable-origin definitions. Optimized technology shares should always be interpreted conditional on this matrix.

## 15. Preparing and running a study

### 15.1 Environment and input validation

The separate model needs a suitable Python/Gurobi environment. Its supplied local reference lists Python-tested numerical packages and `gurobipy==12.0.3`; these are recorded local versions rather than a requirement that another compatible release is scientifically identical. Large national models need appropriate solver licensing and sufficient memory. No license credentials belong in published inputs.

For a native model run, work in the model's own folder, set a fresh scenario name and review the active flags, policies and file names. `python main.py` executes that model, including optimization; it is not a data-preparation command. Run an input-reader-only check before a costly solve, using a supported validation harness.

For a preparation-generated bundle, read `bundle_manifest.json`, `validation.json`, `scenario.json` and process-generation metadata. The generated integration launcher points at an existing model installation. Its default is input-reader-only; `--solve` explicitly requests construction/optimization. The preparation GUI does not invoke it.

### 15.2 Separate preparation integration

This validation command belongs to the model integration workflow, after preparation:

```powershell
python outputs_all_HR/data/run_model_scenario.py --model-root "D:\POSAO\H2RES_12.11.2026"
```

This command reads inputs without requesting optimization. Do not substitute a stale bundle merely because filenames exist. Adapter compatibility is version-specific; inspect model/source hashes when moving to another release.

The preparation contract was developed against the 2 November native layout. A current legacy bundle is not evidence that the new product-industry workbook, DSM assumptions or every later model extension has been generated or validated. Use the adapter validation output before considering a solve; this documentation did not validate that adapter against a full 12 November solve. Run the native model directly for the script-based workflow described in the visual guide.

### 15.3 Resume and historical decisions

Set resume options only for coherent, accepted results. Investment handoffs, fuel/vehicle/heat histories and terminal/stock files must belong to the same input convention and scenario. Changing costs, unit names, decision grid, physical scaling or technology representation while reusing histories can produce mathematically valid but inconsistent comparisons or an infeasible model.

A partial foresight run exports the accepted decision year, not every sampled future-year solution as a committed history. Failed/provisional outcomes need their quality gates before they can be used as later stock constraints. Preserve the exact logs and history files when investigating a transition failure.

## 16. Solver behavior and numerical quality

The cost script selects the primary solver method and applies numerical scaling/tolerances from runtime policy. The examined settings favor barrier for planning, with specialized annual-S-curve behavior and recovery options. A configured time limit of zero can mean unlimited in the implemented wrappers. Recovery calls may differ from the primary solve and can run for a long time.

Solver status and engineering quality must be reported separately. `OPTIMAL` means the solver's optimality criteria were met for the constructed problem and tolerances; it does not validate input realism. `TIME_LIMIT` or `SUBOPTIMAL` may have a usable incumbent but are not equivalent to a certified optimum. `INFEASIBLE`, `INF_OR_UNBD` and numerical failures require different diagnoses [R28](REFERENCES.md#r28), [R29](REFERENCES.md#r29).

Inspect primal constraint/bound violations, dual/residual information where meaningful, objective/bound gap and the model's physical balance audit. Numerical row scaling can make a small solver residual correspond to a different MW/MWh/tCO2 violation. Read the physical-unit gates before accepting exports. Do not use a higher tolerance merely to remove an inconvenient policy or stock inconsistency.

The delivered `main.py` has `solver_allow_provisional_solution=True` and `solver_postoptimal_checks_warn_only=True`. Consequently, a finished export can contain warnings or a provisional solution: completion alone is not a strict quality certificate. Runtime policy also requires annual capture-quality checks and sets a 0.1 physical-energy tolerance and a 0.001-tonne amine-mass tolerance in their applicable checks. Read the exported status and physical audits together with the actual branch that produced them; a warning is not proof that a gate stopped the run.

A barrier solution without crossover can lack a conventional simplex basis; shadow prices or recovery behavior need careful interpretation. Memory exhaustion can occur during building, presolve, factorization or export, and should not be labelled proof of physical infeasibility. Gurobi's numerical guidelines explain the general distinctions; the local configured thresholds are in the configuration inventory.

## 17. Results and interpretation

| Result family | Interpretation and checks |
|---|---|
| Investment/capacity CSVs | New versus surviving capacity, native units, vintage/retirement and decision windows |
| Hourly/yearly electricity balances | Generation, demand components, charging/discharge, losses, imports/exports and unmet load |
| Heat and industry outputs | Useful service versus final fuel input; direct-electric/HP shares; process replacement accounting |
| Transport stocks/flows | Vehicle-equivalent stock, demand service, primary/secondary fuel recipes and conversions |
| Hydrogen/e-fuel outputs | Production, upstream inputs, storage, trade and terminal throughput |
| Carbon outputs | Sector emissions, independent process emissions, capture/reuse/storage and budget/slack |
| Cost outputs | Unit bases, annualization, discounting, source price year and solver scale |
| Solver/quality logs | Status, method, runtime, recovery, objective/bound and physical residuals |
| Combined dashboards/plots | Derived presentation of accepted exports; not a substitute for balance tables |

Myopic results are commonly organized under `results/<scenario>/<decision-year>` with annual investment/history files; detailed paths depend on exporter and mode. Stage-2 bundles and rolling window/stitching outputs have their own metadata. Terminal outputs can include `h2_terminal_flows.csv`, annual capacity/summary tables and `transfer_terminal_new_YEAR.csv`.

Check that representative-period additive quantities are annualized exactly once. Installed capacities and shares are not summed like hourly energy. Compare runs on matching economic/energy boundaries and time grids. A shadow price is conditional on the active constraints and an accepted economic solution, not a forecast of a regulated tariff.

## 18. Validation evidence, inherited warnings and known limits

This documentation was produced by static source/input review and reference checking. It did not execute a fresh national solve. Local preparation reports establish bounded reader/schema/source-reconciliation results; they do not independently establish all model modes or years.

The supplied folder contains the unified-model implementation notes, component regression tools, and a historical critical-correction/rebuild harness. The current `docs/UNIFIED_MODEL.md` describes the integration of simple industry, electricity CBAM history handling and DSM. These are distinct from older verification files describing unpromoted candidates. In particular its `verification.json` distinguishes component tests, synthetic workflow fixtures and user-reported remote transition evidence, with no real local checkpoint promoted in that report. Historical run instructions and comments must not be cited as proof that those candidate fixes are active or that a full transition passed locally.

Validate the exact production objective and physical constraints in the documented source, then compare any proposed correction with its checkpoint/diff and acceptance certificate. A source hash, accepted transition log and scenario/input identity are stronger evidence than a filename such as `corrected` or a comment claiming a previous optimal case.

Principal study limitations are deterministic future inputs, spatial aggregation/proxies, sampled chronology in applicable modes, continuous transport stock, inherited technology/fuel compatibility assumptions, incomplete lifecycle/non-CO2 accounting, terminal aggregation, possible data-duplicate reconciliation and country-specific calibration gaps. The [assumptions register](ASSUMPTIONS_AND_LIMITATIONS.md) makes these limitations explicit.

For a publishable run, archive the exact model/inputs, environment, flags/policies, source references/hashes, solve logs, quality certificates, decision/history files, representative weights and scripts producing reported tables/figures. Cite the H2RES scientific formulation and the actual data/technology references, while stating that this local version includes later extensions.


## 19. Basic electricity demand-side management in this version

`scripts/electricity_dsm.py` adds lossless load shifting to basic electricity demand. It does not automatically shift all heating, transport or industrial service demands. `DSM_day`, `DSM_week`, `dsm_energy_budget_active` and `dsm_availability_ramp_active` are all false in the delivered `main.py`. See the [visual guide](H2RES_USER_GUIDE.md) for activation and the supplied [detailed DSM implementation notes](model_notes_2026_11_12/ELECTRICITY_DSM.md) for time-mode behavior and regression scope.

Runtime policy defines a 7% daily-capable energy pool that includes a 1.5% weekly-capable subset. With both classes enabled, 5.5% balances daily and 1.5% balances weekly. These are scenario upper bounds on moved energy, not measured Croatian loads or compulsory dispatch. The default rollout reaches its target in 2030 from the global base year. The separate shared hourly adjustment cap is 10% of baseline load; available-power cost is EUR 10,000/MW/year and activation cost EUR 5 per MWh moved.

For original hourly load `b[h]`, signed class adjustments `x[c,h]`, absolute adjustments `a[c,h]` and available power `K`, the main restrictions are:

```text
new_basic_load[h] = b[h] + sum_c x[c,h]
a[c,h] >= x[c,h]; a[c,h] >= -x[c,h]
sum_c a[c,h] <= K
sum_c a[c,h] <= hourly_shift_fraction * b[h]
sum_(h in block) x[c,h] = 0
0.5 * sum_(h in block) a[c,h] <= class_energy_fraction * sum_(h in block) b[h]
```

The half-absolute sum counts each moved MWh once. Daily blocks have 24 hours and weekly blocks 168, anchored at model hour 1; the last incomplete block also closes. Opposite class shifts share power and cannot cancel their capacity use. A symmetric 10% hourly cap can limit moved energy to 5% of block load even when the energy allowance is 7%. These are different constraints. This model does not represent individual appliance deadlines, load shedding or cross-zone demand relocation.

Review `dsm_hourly_YEAR.csv`, `dsm_classes_YEAR.csv`, `dsm_summary_YEAR.csv` and `dsm_assumptions.json`. Compare original and adjusted demand, net block energy, moved MWh, available power and enabling/activation costs. Changing budgets or rollout can invalidate existing histories and capacity bundles.

Demand-response background is provided by [R35](REFERENCES.md#r35), [R36](REFERENCES.md#r36) and [R37](REFERENCES.md#r37); these sources do not validate the local energy-pool percentages or costs.

## 20. Product based simple industry and regional trade

This is a separate optional representation, selected by `model_simple_industry=True` and `simple_industry_dat='./data/simple_industry.xlsx'`. It is different from the worksheet named `simple_industry` inside a flex-tech workbook: that worksheet is the legacy pooled-service remainder. The new external workbook contains fixed industrial product recipes, physical plants and product markets. The delivered model leaves this mode off.

Enabling product industry configures the electricity-and-product-industry run and disables overlapping legacy transport/industry, category/complex, e-fuel, hydrogen and industrial capture/storage blocks. Heating retains its switch. Active example systems are HR, RS and BA through `simple_industry_active_zones` in model policy. Independent switches control industrial CBAM, domestic carbon pricing, outside imports, optional outside exports and flexible steel operation. Only one electricity CBAM option may be selected; electricity CBAM and product CBAM are separate accounts.

The workbook uses `plants`, `inputs_per_tonne`, `economics`, `fuel_prices`, `markets`, `market_years`, `carbon_policy`, `import_suppliers`, `import_years`, `trade_routes`, `profiles`, `baseline_load` and `metadata`. Production is tonnes per one-hour interval, electricity is MWh/t, non-electric recipes GJ/t and carbon factors tCO2/GJ. Supply ceilings, grid limits and inventories limit dispatch; nameplate capacity does not require production. Fixed-operation plants remain constant within each calendar day after availability adjustment; flexible plants may vary hourly under their limits.

Mandatory product markets must be supplied. Regional plants can trade; bounded outside offers are available only under their applicable switches and eligibility. One supplier's annual budget is shared across destinations. No unlimited emergency source or automatic demand reduction is introduced. Origin tracking preserves supplier footprints for final-destination carbon charging and separates territorial direct emissions from embedded trade emissions. Prices are prescribed; there is no endogenous steel-price equilibrium.

The supplied RS BF-BOF and BA scrap-EAF plants, external supplier prices/footprints and rest-of-Europe supply are illustrative scenario inputs, not calibrated named installations. The example requires RS 800,000, BA 300,000 and HR 1,000,000 tonnes/year, plus 134,000,000 tonnes/year for Europe outside HR. The European background offer serves that Europe market, not a bypass for domestic import restrictions. Check every price, quantity and route before drawing policy conclusions.

`baseline_load` specifies already-existing plant electricity to remove from the basic profile. Example removals are zero, so example plant loads are additions. Calibrating a real plant requires a defensible removal to avoid counting the same demand twice. Likewise, do not enter coke carbon in both the fuel recipe and process-carbon field.

Review `simple_industry_hourly.csv`, `simple_industry_fuels.csv`, `simple_industry_sales.csv`, `simple_industry_markets.csv`, `simple_industry_summary.csv`, `simple_industry_imports.csv`, `simple_industry_demand.csv`, `simple_industry_cbam_borders.csv`, `simple_industry_fiscal.csv` and the applicable levelized-cost summary. For field-level operation, trade budgets and capital/CBAM allocation, use the supplied [simple-industry implementation notes](model_notes_2026_11_12/SIMPLE_INDUSTRY.md). The [unified-model notes](model_notes_2026_11_12/UNIFIED_MODEL.md) report bounded component/8760-hour example evidence and known baseline regression exceptions; they do not certify a full national transition solve.
