# Configuring main.py: complete workflows and option interactions

**Applies to:** the inspected `H2RES_12.11.2026` model. This guide explains the available structures, how to combine their controls and how to interpret the resulting study. The [complete option reference](MODEL_OPTION_REFERENCE.md) explains every recorded assignment in `main.py` and the three loaded policy files. The [equation chapter](MATHEMATICAL_FORMULATION.md) explains the physical, economic and policy mechanisms. Desktop GUI operation is excluded.

The examples are configuration instructions, not reports of new solved cases. Enabling a technology allows its modeled activity; it does not guarantee that the optimizer will build or dispatch it. Results depend jointly on demand, prices, stock, retirement, resources, investment limits, networks and all active policies.

## 1. Five decisions define a study

Choose the following independently, then check their dependencies:

| Decision | Principal choices | Where configured |
|---|---|---|
| Physical boundary | Electricity, heat, legacy industry/transport, product industry, H2/e-fuels, capture, trade | Main module switches plus eligible data rows |
| Industry representation | Pooled/mixed detailed services, temperature categories, selected complex processes, separate product model | Main industry flags, Industry_data inclusion and companion workbooks |
| Planning information/time | Joint foresight, ordinary sequential planning, partial foresight, representative capacity, rolling fixed dispatch | Main time-mode flags, runtime policy and policy setup |
| Policy experiment | RPS, emissions caps, removals, transition rules, electricity CBAM, product CBAM, domestic carbon prices | Main switches, model policy and policy/workbook trajectories |
| Numerical acceptance/output | Algorithms, retries, time limits, provisional/strict checks, diagnostics, histories, plots | Main/runtime settings and exporters |

A meaningful comparison normally changes one documented group at a time. For example, compare e-fuel and no-e-fuel cases using an explicitly matched demand/service boundary; otherwise different workbooks may change more than the carrier representation.

## 2. How to make a configuration change

1. Preserve the original model/input snapshot. Select the model's Python/Gurobi environment.
2. Set a fresh `scen` in `main.py`, identifying the intended experiment.
3. Edit the original declarations in `main.py`. Do not append settings below the execution section: the model may already have solved by then.
4. Edit numerical and transition parameters in the appropriate policy module. Main loads these before most switches and later derives filenames.
5. Edit the selected workbook's `setup`, active geography, inclusion flags, limits and policy paths. Saving a different workbook does not change the selected path.
6. Check the normalized configuration and selected input paths. A flag may be overridden, ignored outside its parent module, or rejected.
7. Run `main.py`; inspect the first input/read/build messages before interpreting the eventual result.

The following snippets show the settings to change, not complete standalone Python programs. Apply them at their original declarations. A scenario JSON from the data extractor is not automatically loaded by native `main.py`. The source uses a shared namespace, so policy modules and helper normalization matter as much as the visible main switches.

## 3. Dependency and normalization map

| Requested combination | Effective behavior / requirement |
|---|---|
| Categories plus complex industry | Rejected; these are alternative representations |
| `industry_storage=True` | Requires transport/industry, categories and multi-sector operation |
| Complex industry | Requires legacy transport/industry and `industry_single_sector=False`; selected sectors come from policy |
| Either complex alias True | Both aliases are normalized to the same effective complex selection |
| E-fuels plus standalone H2 pipelines | Main disables standalone `model_H2_transmission`; carrier transmission already handles H2 |
| Explicit Oil/Gas supply without e-fuels | Main disables that supply flag |
| E-fuels plus no base-year vehicle investment | Main permits base-year additions to meet the e-fuel case's initial fleet floors |
| Capture off with amine storage on | The variable/setup path turns amine storage off |
| Capture and e-fuels both off | The applicable setup turns post-generation CO2 storage off |
| Standalone terminals without e-fuels | Requires legacy transport/industry, the H2 balance and valid H2 terminal/routes/cost data |
| Terminals with e-fuels | Uses the product-terminal, route and carrier tables instead of assuming the standalone schema |
| Lightweight representative mode | Enables automatic mode but skips its stage-2 rolling dispatch |
| Fixed capacity without rolling dispatch | Main normalizes fixed capacity off for a normal capacity solve |
| Rolling dispatch alone | Does not select the standalone dispatch runner; fixed capacity must also be True |
| More than one electricity CBAM option | Rejected |
| Electricity CBAM with `Myopic=False` | Rejected by the inspected builder |
| Product industry enabled | Configure step disables overlapping legacy industry/transport, e-fuel/H2/capture blocks and selects its active example systems |
| Product carbon pricing/CBAM with product mode off | Invalid as an independent product-policy configuration |
| Building heat technology flag with heating off | Does not create an active heating subsystem |
| Legacy industry with heating off | Not presented as a fully costed preset: current industry CAPEX definitions include heating-nested paths |
| No active/eligible input row or zero build allowance | A main technology flag does not create the missing asset or permit forbidden additions |

These include explicit errors, automatic normalization and reviewed support limitations; they are not all the same kind of check. The absence of a blanket `ValueError` does not prove a combination has complete costs, variables and balances. Keep experimental/debug settings separate from production scenarios.

## 4. Time modes: select one execution structure

The calendar-year list in `policy.xlsx` or `policy_efuel.xlsx` is separate from hourly sampling. The inspected e-fuel setup lists 2025, 2030, 2035, 2040, 2045 and 2050, with `chunk_size=1`, `step_size=1`, and hours 1–8760. Thus a name containing `5y` does not itself select five-year chunks.

| Workflow | Myopic | Partial | Auto two-stage | Lightweight | Fixed / rolling |
|---|---:|---:|---:|---:|---|
| Joint full-hour planning | False | False | False | False | False / False |
| Ordinary sequential planning | True | False | False | False | False / False |
| Sequential planning with sampled future lookahead | True | True | False | False | False / False |
| Representative capacity screening | Either | False | True | True | Initially False / False; controller manages stages |
| Capacity planning followed by chronological fixed dispatch | Either | False | True | False | Initially False / False; controller manages stages |
| Dispatch from a trusted existing bundle | Match the intended study | False | False | False | True / True |

Leave `representative_capacity_mode=False` for the ordinary full-hour and partial-foresight recipes. The automatic controller sets representative/fixed/rolling modes internally. Do not manually turn on every time-related flag.

### 4.1 Joint full-hour perfect foresight

Use this to optimize the provided decision years jointly with their full configured hourly periods:

```python
Myopic = False
partial_perfect_foresight = False
two_stage_auto_mode = False
lightweight_representative_weeks_mode = False
representative_capacity_mode = False
fixed_capacity_mode = False
rolling_dispatch_mode = False
```

The optimizer knows the supplied future costs, demands and policies. This is an information assumption, not a forecast of real decision-maker knowledge. Size can grow rapidly with zones, years, carriers and process detail. Electricity Options 1–4 must remain off in this source. Ordinary sector choices, RPS, carbon caps, DSM and eligible product policies have their own compatibility requirements.

Expected evidence: the joint solve log, accepted capacities across the horizon, full configured operational coverage and physical-quality checks. A five-year decision grid still requires explaining how annual investment and operating costs are represented between decisions.

### 4.2 Ordinary sequential myopic planning

Start with the preceding settings, change `Myopic=True`, keep partial foresight False and use a new scenario. `chunk_size` and `step_size` count positions in the decision-year list. With one year per chunk and one-position advance, each point is solved sequentially and saved history constrains later decisions. On a 2025/2030/... grid, one position is five calendar years; on an annual grid it is one year.

Increasing chunk size exposes more decision points jointly to each solve. The exact exporter and history behavior matters for overlapping chunks; do not assume every ordinary multi-year chunk commits only its first year. That first-year restriction is explicit in the partial-foresight path. Prefer a clearly documented chunk/step structure and inspect accepted-year exports.

Use this for limited-information or path-dependence experiments, while recognizing that a one-point solve can make choices that later demand/policy makes expensive or infeasible. Myopic results are not necessarily as low-cost as joint foresight under otherwise matched assumptions.

### 4.3 Partial foresight with a detailed decision year

```python
Myopic = True
partial_perfect_foresight = True
two_stage_auto_mode = False
lightweight_representative_weeks_mode = False
representative_capacity_mode = False
fixed_capacity_mode = False
rolling_dispatch_mode = False
```

In `policy/runtime_policy.py`, review:

```python
partial_foresight_representative_days = 4
partial_foresight_day_hours = 24
partial_foresight_representative_day_start_hours = (337, 2521, 4705, 6889)
partial_foresight_lookahead_years = 10
```

The current year uses the full configured calendar; future decision years use four sampled days. Ten is a calendar-year reach, not ten decision points. From 2030 on a five-year grid, the allowed points are 2030, 2035 and 2040. `None` exposes the remaining tail. The current decision-year result is exported as committed history; sampled future solutions guide that decision and are revisited later.

This can reduce solve size relative to giving every future point a full year. It does not establish seasonal storage feasibility for the sampled future years. A shorter lookahead can change investments materially. Report the actual sampled starts and weights with the result.

### 4.4 Representative capacity screening only

```python
Myopic = True
partial_perfect_foresight = False
two_stage_auto_mode = True
lightweight_representative_weeks_mode = True
fixed_capacity_mode = False
rolling_dispatch_mode = False
```

Choose `Myopic=False` instead if a joint representative capacity study is intended. The controller performs stage 1 and skips stage 2. Its historical setting names are misleading in this snapshot: `representative_weeks_count=4` and `representative_week_hours=24` mean 96 sampled hours, not 672 hours. Equal sample expansion is 8760/96 = 91.25 where that annualization convention applies.

Use it to screen assumptions and inspect indicative capacity/cost changes. Do not call it a full-year operational validation. The annualized energy totals and sample metadata must accompany plots. If changing to actual week-long blocks, set compatible lengths/starts/counts and reassess all module chronology; changing the label alone has no effect.

### 4.5 Automatic capacity planning plus rolling dispatch

```python
Myopic = True
partial_perfect_foresight = False
two_stage_auto_mode = True
lightweight_representative_weeks_mode = False
representative_capacity_mode = False
fixed_capacity_mode = False
rolling_dispatch_mode = False
```

The controller samples stage-1 capacity planning, exports a dispatch bundle, then freezes capacity for rolling operation. Use `Myopic=False` for the joint stage-1 variant, subject to the selected policies. Keep `two_stage_stage1_export_timing='before_stage2'` so investment/history outputs exist. Turning those exports off can affect later sequential chunks.

This asks whether sampled planning capacities can operate under the configured chronological dispatch assumptions. It is not a single all-hours capacity optimization. Forecast deviations, annual budgets, guidance, stock end conditions and penalized shortages all affect stage 2. Inspect the original window files and stitched annual balances, not only representative stage-1 plots.

### 4.6 Daily versus weekly intra-annual dispatch

In runtime policy, `rolling_dispatch_granularity='day'` sets 48 optimized hours, 24 committed hours and a 24-hour advance. `'week'` sets 336 optimized hours, 168 committed hours and a 168-hour advance. `'custom'` uses the explicit window, step and realized-horizon settings. With day/week selected, editing only `rolling_window_size` is overwritten by the granularity function.

The second half of a daily window provides forecast/lookahead; it is not committed twice. The next window inherits the last committed physical states and accepted budgets. Storage, maritime transit, annual imports and carbon guidance require correct handoff metadata. Longer windows can reduce short-sighted dispatch while increasing memory and solve time.

The author reports improved intra-annual myopic stability in a more recent no-e-fuel working version. That report should not be generalized to all e-fuel, capture, terminal and process combinations or treated as a new regression result for this documentation snapshot.

### 4.7 Fixed dispatch from an existing capacity bundle

```python
two_stage_auto_mode = False
lightweight_representative_weeks_mode = False
representative_capacity_mode = False
fixed_capacity_mode = True
rolling_dispatch_mode = True
export_stage2_dispatch_bundle = False
dispatch_stage_data_path = './results/REFERENCE_SCENARIO/stage2_dispatch_bundle.pkl'
```

First obtain a trusted bundle through planning with `export_stage2_dispatch_bundle=True` or automatic stage 1. The file contains model state/metadata, not just capacities. Match units, active geography, years, technology/accounting conventions and module settings. This recipe freezes supported assets; it does not mean setting every `cap_inv_lim` cell to zero has the same effect.

A zero build limit allows surviving existing capacity but may not pin every state, retirements or previously planned investment. Use the dedicated fixed-capacity mechanism for a dispatch experiment. Report any unsupported or unpinned asset family explicitly.

## 5. Electricity-only and integrated-energy boundaries

For a deliberately reduced electricity-only structure, disable the legacy coupled modules consistently:

```python
model_simple_industry = False
model_heating = False
model_cooling = False
model_transport_and_industry = False
model_industry_categories = False
model_complex_industry = False
model_complex_non_metallic_minerals = False
industry_storage = False
model_efuel = False
model_oil_and_gas_products_supply = False
model_H2_supply_demand_balance = False
model_H2_transmission = False
model_terminals = False
model_CC = False
model_CO2_ammine_storeage = False
model_CO2_post_gen_storeage = False
```

This is a reduced-boundary configuration for validation, not a claim that the existing input demand has been calibrated to an electricity-only study. Inspect the reader's decomposition and demand CSV: demand already assigned to explicit sector blocks must not disappear unintentionally, nor be counted twice. Retain the intended generation, storage, network, RPS and carbon policies separately.

For the delivered integrated case, keep heating and legacy transport/industry on and select the appropriate industry/carrier representation. Disabling heating alone while retaining legacy industry is not a reliable shortcut because current cost paths include heating-nested industry definitions. Model-size reduction should preserve a complete accounting boundary.

## 6. Heating technologies and three different thermal stores

`model_heating=True` activates the heating subsystem. The individual and DH boiler flags select their eligible boiler lists; the individual and DH HP flags select their HP lists. Solar flags select solar thermal, not PV. `model_cooling` is a separate legacy request requiring its cooling data and verification.

| Intended change | Controls and input review |
|---|---|
| Permit individual building HPs | `model_HP_units=True`; individual heat demand, COP/efficiency, capacity, retirement and cost trajectories |
| Permit DH HPs | `model_HP_units_DH=True`; DH demand/losses and district technology rows |
| Permit solar heat | Applicable solar flag, availability, technology/cost and storage rows |
| Individual HP heat shifting | `individual_heat_pump_storage=True` with heating and individual HPs |
| District heat/cooling storage | `DH_Storage=True` with the relevant thermal subsystem and its storage parameters |
| Industry category thermal storage | `industry_storage=True` with category industry; independent of both building/DH stores |
| Fix the pool of available boilers | Review capacity/retirement and build limits; the technology-selection flag alone does not freeze stock |

Keep `NoResToHeatInv=False` for normal individual HP electricity/capacity equations. Its inverted legacy gate skips those equations when True; it should not be used as a general prohibition of renewable-to-heat investment. Likewise, `ratio_heat_indv` and `heating_shares_regulate` add specific equation branches and do not simply select a national heating fuel split.

Heating transition policies operate in addition to technology eligibility. Current controls include base-year CHP heat calibration, CHP year-to-year change, individual electric/gas heat change, fossil heat nonincrease, boiler phaseout and biomass heat nonincrease. To study a different phaseout, change both the intended switches and their fuel/year/rate data; disabling only `fossil_boiler_phaseout_active` can leave nonincrease or the carbon limit binding.

## 7. Industry without temperature categories: pooled or mixed detail

```python
model_transport_and_industry = True
industry_single_sector = False
model_industry_categories = False
model_complex_industry = False
model_complex_non_metallic_minerals = False
industry_storage = False
```

With `model_efuel=False`, the active technology file is `flex_tech.xlsx`; with e-fuels True it is `flex_tech_efuel.xlsx`. The detailed-industry inclusion field determines which native industry services remain explicit. Setting the applicable detailed services to N must transfer their quantities to the pooled `simple_industry` worksheet. It does not mean industrial energy vanishes.

Mixed configurations are possible: retain chosen branches/services explicitly and pool excluded ones. Recompute and reconcile the remainder whenever inclusion changes. Retained detailed plus pooled demand must equal the original intended industrial demand, with capacities and efficiencies on a consistent basis. Do not confuse a stored formula with a current cached numeric value.

This mechanism is distinct from `industry_single_sector=True`, which selects an older branch. The latter is not the recommended route to obtain a pooled integrated e-fuel or category case.

## 8. Industry with temperature/service categories

```python
model_transport_and_industry = True
industry_single_sector = False
model_industry_categories = True
model_complex_industry = False
model_complex_non_metallic_minerals = False
industry_storage = True
```

Choose True or False for the last setting depending on whether industrial thermal storage is part of the experiment. The active technology file is the applicable category variant. Review `Industry_data`, category costs, industry thermal storage, HP applicability and capture data. `industry_category_profiles.csv` supplies service timing.

Use `industry_category_electricity_case='conservative'` for the main e-fuel category workbook; use `'technical_2050'` for its nested alternative. This changes applicability assumptions, not the planning-year list or a mandatory share. A fully detailed category case can legitimately leave no pooled remainder. The category, fuel-compatibility and adoption ceilings still interact.

## 9. Process-based complex industry and tested sector scope

```python
model_transport_and_industry = True
industry_single_sector = False
model_industry_categories = False
model_complex_industry = True
model_complex_non_metallic_minerals = False
industry_storage = False
```

The compatibility alias will be normalized to the effective complex selection. In `policy/model_policy.py`, select exact supported branch names through `complex_industry_sectors`; the delivered tuple is `('Non_metallic_minerals',)`. Selected branches replace matching ordinary service rows. The remaining sectors retain the ordinary formulation for that configuration.

Use `industry_complex.xlsx` without e-fuels and `industry_complex_efuel.xlsx` with e-fuels. The complex electricity-case selector can choose each companion's technical alternative. Check `Process_data`, product demand, component units, useful service, feedstocks, compatibility and capture mappings together.

The author reports testing non-metallic minerals, while additional process data are prepared but not comprehensively tested across all sectors. The reported order of 150–200 processes describes the broader development scope, not a verified active process count for every case. Extend sector selection progressively and check demand/energy/process-carbon reconciliation before comparing national results.

## 10. Industrial heat pumps and adoption constraints

Industrial HPs use `industry_heat_pumps_active` in model policy, not the building `model_HP_units` flag. They need eligible useful-service temperatures, source heat, profiles, costs and investment limits. Their cumulative low-temperature potentials overlap: several cumulative thresholds must not be added as separate available heat pools.

`industry_electrification_full_applicability=True` permits the implemented full applicability treatment but retains capacity, transition, resource and other process restrictions. It is not a command to electrify all industry. The conservative/technical workbook case remains a separate choice.

General ramps, S-curve selection and annual combined electric/HP share controls are independent. For the delivered finite transition, review the 2045 completion year, seed 0.02, growth 0.5 and five-year reference interval. The finite progress function is a cubic smoothstep; do not describe it as a calibrated logistic diffusion forecast. A direction override is a policy choice distinct from a technical maximum share.

To compare transition-constrained and unconstrained industry, document which of `industry_fuel_share_ramp_active`, `industry_fuel_share_s_curve_active` and `industry_electric_share_yoy_limit_active` changed. Disabling one does not erase the remaining adoption, applicability, stock or carbon restrictions.

## 11. Integrated e-fuel modeling

For the author's supplied integrated e-fuel configuration, use:

```python
model_transport_and_industry = True
industry_single_sector = False
model_efuel = True
model_oil_and_gas_products_supply = True
model_H2_transmission = False
```

Select regular, category or complex industry as described above. Keep heating enabled for the documented legacy integrated cost paths. The technology and policy filenames acquire the e-fuel family, with `policy_fuels.xlsx` for applicable carrier prices. Review conversion recipes, primary inputs, carrier storage, compatible final demand, external supply, terminal/routes, reserve/extraction assumptions and all cost/build trajectories.

E-fuels can require H2, CO2, electricity, heat and other feedstocks. Process carbon, DAC and eligible industrial biogenic CO2 can supply CO2 feedstock under their actual source/capture mappings. When process emissions are present, a tight carbon cap also needs a feasible net-emissions treatment; feedstock demand alone does not guarantee enough permanent storage or offsets.

`model_oil_and_gas_products_supply=True` is part of the supplied integrated configuration, and main disables it when e-fuels are off. The code does not impose a blanket error for every hypothetical e-fuel case with this flag off; such an alternative must establish its own complete supply boundary. Do not silently substitute that alternative for the author's tested setup.

Expected outputs include electricity and carrier balances, electrolysis and conversion capacities, feedstock demand, storage/trade, refinery/fossil supply, capture and emissions. Zero e-fuel output can be the economic result of permitted alternatives, absent final demand, limited CO2/H2, expensive electricity or build restrictions; activation is not a production target.

## 12. No-e-fuel scenarios and matched comparisons

Set `model_efuel=False` and `model_oil_and_gas_products_supply=False`, choose the corresponding non-e-fuel technology/policy inputs and review exogenous CO2 demand if capture remains enabled. Retain the intended heating, transport and industry service boundary. Do not compare the result with an e-fuel run while assuming every price, technology or service row is identical across workbook families.

Without e-fuels, standalone H2 supply/demand, pipelines and aggregate H2 terminals can be used under their own requirements. Capture and geological storage can still be relevant to process emissions. No-e-fuel does not automatically mean no H2, no industrial capture or no product carbon policy: each belongs to a separate valid representation.

## 13. Capture, amine flexibility and the CO2 destination

For eligible industrial capture, enable `model_CC=True` and activate the corresponding capture rows and equipment limits in the selected native technology/process inputs. Confirm capturable streams, capture rates, electricity/heat demand, reboiler capacity and costs. A capture switch does not create an available carbon source or a final destination.

`model_CO2_ammine_storeage=True` adds absorber/stripper timing flexibility through amine inventory. With capture off, the setup turns it off. `model_CO2_post_gen_storeage=True` permits the applicable post-capture stock/capacity representation; geological storage additionally needs eligible active geological units and positive capacity/build allowances. Rich-amine stock, reusable CO2 buffer, geological inventory and injection capacity have different physical meanings and units.

| Intended CO2 experiment | Required interpretation |
|---|---|
| Capture off | No eligible industrial capture assets; e-fuel DAC may still exist through its own representation |
| Capture on, amines off | Capture and stripping follow the corresponding immediate/non-storage relationship |
| Capture with amines | Add inventory flexibility and enforce mass/energy balances and bounded cyclic/rolling states |
| Captured carbon for e-fuels | Needs permitted source/feedstock mappings and conversion demand; reuse is not permanent sequestration |
| Geological storage | Needs main switches plus active native storage rows, stock/injection/build capacities and permitted provenance |
| Mandatory eligible process capture | Set `complex_industry_process_capture_required=True` in a compatible complex case; uncapturable residuals remain possible |

Industrial biomass carbon is counted physically for capture/feedstock where eligible but is not charged as fossil combustion in the supplied aggregate budget convention. Document this distinction; it does not establish biomass sustainability or a complete lifecycle balance.

## 14. Process emissions under a binding carbon limit

If `carbonLimit=True`, residual process emissions can make a stringent or zero-carbon endpoint infeasible even when fossil combustion has been eliminated. There are two distinct configured mechanisms:

1. Capture eligible process carbon and send it to enabled geological storage with sufficient capacity, injection and build allowances.
2. Include a justified LULUCF removal allowance in the carbon budget through `lulucf_removals_active=True` and the supported CSV/fixed input convention.

LULUCF is an accounting offset; process CO2 is not physically sent to a land-use technology. It does not create capturable CO2 or satisfy an e-fuel feedstock requirement. Avoid assigning the same removal allowance twice across fixed and scoped inputs.

For process-only geological eligibility, use:

```python
carbonLimit = True
model_CC = True
model_CO2_post_gen_storeage = True
separate_industry_process_carbon_balances = True
```

Also activate the required process capture/storage entries in the selected native sheets. The separated balance prevents other combustion, DAC and untagged imported/buffer carbon from acquiring geological process provenance. Without this separation, the applicable aggregate carbon branch has a different eligible-credit boundary.

Before relaxing the carbon cap, check source emissions, capture eligibility/rates, geological rows, annual build limits, energy for capture, final storage capacity and permitted LULUCF. If uncapturable process emissions exceed the remaining budget, removing a numerical warning cannot make the intended physical scenario feasible.

## 15. Electricity transmission, HVDC and outside systems

`use_HVDC=True` includes eligible HVDC link technology and converter requirements in the electricity transmission representation. Existing/new capacity, transformer/converter costs, routes, distance losses and investment limits still come from the network inputs. False filters that technology; it does not turn off all inter-zonal exchange.

`include_secc_links=True` includes secondary routes through intermediate zones where supplied. Review double counting, route keys and primary/secondary interactions. Transmission has a deterministic duplicate policy (`first` in the delivered settings); reconcile conflicting records rather than assume the first is scientifically correct.

Outside-system trade can be limited by hourly supply shares/curves, annual outside-trade calibration, transfer capacity, prices and the selected carbon representation. To study an isolated system, constrain or deactivate its external routes in the native network tables and inspect the actual balance. Turning off `outside_system_availability` removes an availability restriction and can increase trade; it does not isolate the system.

## 16. H2 pipelines and terminals with or without e-fuels

For standalone H2 pipelines without e-fuels:

```python
model_efuel = False
model_transport_and_industry = True
model_H2_supply_demand_balance = True
model_H2_transmission = True
```

Keep a compatible industry/heating representation, H2 production/demand/storage and pipeline/compressor/cost data. Pipeline aliases and compressor electricity inputs matter. With e-fuels True, use the product transmission tables for H2; main normalizes the standalone pipeline flag off.

Terminals are possible in either carrier representation. Set `model_terminals=True`, then select active terminal rows and allowed flow directions in the applicable tables. With e-fuels, review product terminal/transmission, terminal activation, import/export, shipping and storage mappings. Without e-fuels, review `h2_terminals.xlsx` with `terminals` and `shipping_routes`, H2 balance and `H2_terminal` cost coverage.

The no-e-fuel terminal model uses aggregate delivered H2 in MW/MWh and annual throughput capacity in TWh/year, buffered by zonal H2 storage. It is not automatically a full liquid-H2/ammonia vessel, liquefaction and cracking model. Terminal throughput, shore/storage energy, vessel travel time and route capacities must not be conflated.

The author reports repeated successful annual runs for Croatia divided into four zones using HVDC, H2 transmission and terminals. This is author-reported case evidence, not a guarantee for other geography, year grids or all combinations. The equations and exact configured inputs determine transferability.

## 17. Transport: fleet, electrification, alternative fuels and infrastructure

Legacy transport is part of `model_transport_and_industry=True`. Use the correct workbook family, sector demand, activity/plug-in/V2G timing and policy targets. Continuous vehicle-equivalent stock, transport service, final energy and battery stock are distinct model quantities.

| Control group | What to change for a study |
|---|---|
| Electrification pathways | Main electrification switch, target sectors, policy floors and applicable nondecreasing stocks |
| Final service applicability | `transport_max_share_limits_active` and `transport_all.max_share`; a ceiling is not a required share |
| New purchases/turnover | Investment-limit switch, unit/sector caps, turnover life/ramp, inherited fleet age and forbidden new units |
| Rail | Direct-electric ceiling, optional rail linkage and battery-rail specifications; do not treat direct EL and battery rail as one unbounded stock |
| Alternative ICE fuels | Pathway corrections, blend/volume-to-energy rules, paid upgrades, costs and remaining life |
| Marine methanol/ammonia | New equipment CAPEX, retrofit fractions, pilot-fuel energy and eligible existing stock |
| Fossil transition | Passenger-car 2050 sensitivity, optional ICE/hybrid fossil decline and annual fuel-composition ramp |
| Infrastructure | Keep `disable_transport_infrastructure=False` for fleet-linked charging/refueling stocks and costs; supply existing infrastructure data |

An ICE vehicle running a compatible non-fossil fuel is different from an electric vehicle or a retired vehicle. A paid conversion consumes eligible incumbent stock and does not permit arbitrary fuel mixing. The test-only unconstrained-upgrade bypass is not a production scenario. E-fuel mode overrides the no-base-year-investment flag because its initial floors can require fleet replacement immediately.

To study infrastructure omission as a sensitivity, label the changed boundary explicitly; a cheaper result without charging/refueling CAPEX is not the same scenario solved more efficiently. Similarly, relaxing turnover or blend limits changes the physical/adoption assumptions, not just runtime.

## 18. Daily and weekly basic-load DSM

For both budgeted classes with rollout:

```python
DSM_day = True
DSM_week = True
dsm_energy_budget_active = True
dsm_availability_ramp_active = True
```

Review daily/weekly energy fractions, hourly adjustment fraction, full-availability year and enabling/activation costs in runtime policy. The supplied daily-capable 7% includes the weekly 1.5%; with both active, 5.5% balances daily and 1.5% weekly. The hourly power cap is an independent 10% of basic load.

For daily-only or weekly-only studies, activate only that class and retain coherent budget/rollout controls. Both false preserves fixed basic demand. Legacy hourly-only variants exist with budgets disabled, but they are not the same flexibility assumption as the constrained new DSM. Changing budgets/rollout can invalidate saved histories and bundles.

DSM acts on residual basic electricity, not automatically on every separate heat, transport or process demand. Daily and weekly blocks are anchored to model hour 1, including final incomplete closure; they are not ISO calendar weeks or appliance-level deadlines. Inspect moved MWh, capacity, costs and block-energy conservation rather than assume the allowance must be fully used.

## 19. Separate product industry and industrial CBAM

```python
model_simple_industry = True
industry_cbam_active = True
industry_carbon_pricing_active = False
industry_external_imports_active = True
industry_external_exports_active = True
steel_flexible_operation = True
```

This selects the product model through its configure step, disabling overlapping legacy industry/transport, e-fuel, H2 and industrial capture blocks. It is not an additional industry layer placed on top of all category/complex demand. Heating keeps its independent selection. Review the configured active HR/RS/BA systems or provide a calibrated alternative.

The separate workbook contains fixed plant recipes, electricity/grid requirements, prices, product demand, eligibility, bounded outside suppliers and trade routes. Example plants and offers are illustrative. Calibrate `baseline_load` removal if their electricity is already inside basic demand; zero removal adds their load. Demand is mandatory where specified even if local plants become uneconomic.

Industrial CBAM and domestic carbon pricing are independent. Compare both off, domestic only, border only and both on, while keeping supplier/market/recipe data fixed. The policy fields determine benchmarks, free allocation, credits and exporter/importer allocation. Electricity Options 1–4 are separate again and retain their own Myopic requirement.

Turning outside imports off does not remove modeled cross-country trade or turn off required Europe demand. Restricted European background supply remains only where its eligibility allows it. Turning optional outside exports off does not erase mandatory domestic/Europe markets. Track original origin and final destination when interpreting embedded carbon and fiscal payments.

`steel_flexible_operation=False` applies the appropriate within-day constant-operation treatment to eligible plants; it is not a requirement that plants operate at full load or that each country produces its own required product. Domestic production can be displaced by eligible imports under bounded supply.

## 20. Electricity carbon-pricing Options 1–4

Choose at most one of `Option_1`, `Option_2`, `Option_3`, `Option_4`; leave all False for no selected electricity-CBAM option. The builder requires `Myopic=True` when any is active. Carbon prices and the carbon quantity cap are different instruments: turning one off does not necessarily remove the other.

Option 1 represents border-only electricity CBAM. Option 2 combines border and national tax/ETS treatment. Option 3 uses the applicable national ETS/EU-price relationship. Option 4 is the mixed national/border branch; supplied structural notes flag a national-cost auxiliary without its own nonzero definition, so it is not presented as a fully verified policy recipe. Inspect its exact rows before relying on it.

Supply active membership, border/network mappings, carbon prices and valid source-zone intensities. Base-year signals, realized predecessor signals and future lookahead overrides have different roles. A valid historical zero is retained; absent required history must not be silently converted to zero emissions. These are the model's scenario representations, not a legal determination of current CBAM obligations.

## 21. Renewable targets, carbon caps, biomass and policy sensitivities

`rps_inv=True` activates native renewable-electricity share constraints from `RPS`. `res_inv=True` selects reporting branches. These similarly named flags do different things. Setting the RPS path to 100% does not certify the renewable origin of all imported fuels, process inputs or final-energy use.

`carbonLimit=True` adds the applicable emissions budget. Prices, capture, geological credit and LULUCF can change how that budget is met. A zero territorial carbon outcome is not necessarily zero embedded imports or a full lifecycle net-zero outcome. Separate process provenance changes which geological credits are permitted.

Resource and transition policies also matter: biomass feedstock limits, biomass-heat nonincrease, generation calibration, hydro caps, outside-trade targets, heating turnover and industrial adoption envelopes can all bind. To remove a historical calibration for a future sensitivity, identify its exact scope and flag rather than delete unrelated resource constraints.

For a whole-energy 100%-renewable study, explicitly define covered carriers, imports, stock origin, biomass/waste eligibility, feedstocks and non-energy/process emissions. The extractor's whole-energy preset adds adapter equations with its own compatibility limits. Native RPS alone is insufficient, and this manual did not validate every 12 November extension through that adapter.

## 22. Changing years, geography and investment opportunities

Change decision years and hours in the selected policy workbook's `setup`, not only the scenario name. Extend every required annual cost, build, demand, product market/supplier, carbon and retirement path. Annual and five-year decision grids must preserve the global investment-window convention. Reference-interval S-curve settings must remain compatible with the decision step.

For another country or subnational/custom zones, establish complete `System`/`zone` mappings, selected active rows, generator and curve IDs, sector demand, outside links, network reachability, stock and cost/limit keys. `active_zone_overrides` can change scoping but cannot manufacture missing inputs. A zone with no existing generator can import through modeled links; it should not receive a fabricated plant merely to fill a table.

To allow more investment, adjust the relevant native annual or total capacity bounds in their correct units and review applicable generator multipliers/adoption policies. MW, MWh, vehicles, tonnes/hour and tonnes of storage are not interchangeable. Increasing an investment limit does not supply more biomass, change a COP or create available CO2 feedstock.

## 23. Solver controls and strict versus exploratory acceptance

The delivered numerical selection uses barrier for planning and dual simplex for rolling operation, with explicit scaling and recovery paths. Time limits of zero are treated as unlimited in the applicable wrappers. A different algorithm can change time or numerical behavior; it does not fix missing physical supply or inconsistent demand.

For a stricter acceptance study, review:

```python
solver_allow_provisional_solution = False
solver_postoptimal_checks_warn_only = False
write_solver_diagnostics = True
solver_diagnostics_on_problem_only = True
```

Retain `solver_require_annual_cc_quality=True` where capture is modeled, and review physical energy/amine tolerances. These settings strengthen the applicable acceptance path; they do not remove explicit rolling shortage, carbon or guidance slack variables. If strict policy feasibility is required, also review the relevant slack switches/bounds and actual exported values.

For difficult numerical cases, inspect scaling, coefficients, physical units and history residue before increasing tolerances. The annual aggregation retry and optional simplex fallback are separate from the generic stronger retry. Exact Kappa diagnostics can be expensive. Changing thread count, focus, crossover, aggregation or time limits must be recorded with the solver log.

An infeasible model has no feasible solution under its encoded assumptions. A numerical failure or interrupted solve is a different outcome. A provisional export is not a certified optimum. Report the status and physical residuals independently of whether plot scripts completed.

## 24. Resume, caches, outputs and reproducibility

Ordinary myopic resume uses `myopic_resume_from_results` and the contiguous completed prefix. Automatic two-stage mode separately checks completed dispatch chunks and may reuse a stage-1 bundle only under its settings. Rolling-window resume separately requires saved window files and compatible incoming states. Do not treat these three resume controls as interchangeable.

A new scenario name is appropriate after material changes in geography, identifiers, recipes, accounting, costs, year grid, DSM budgets, product markets or carbon policy. `validate_completed_heating_policy_history=False` preserves old accepted years without proving they satisfy newly changed heating rules. Reusing an old bundle/history can create an internally inconsistent comparison even when it loads successfully.

Local pandas/Excel read caching improves repeated input reads. It is not Open-Meteo download caching, API quota control or proof that online observations were refreshed. Deep-copy settings concern shared-data mutation and memory. Do not use the cache counters to estimate internet requests.

Preserve CSVs needed for investment/stock histories, hourly/annual balances, costs, carbon and module diagnostics. Additional shadow-price exports need their appropriate accepted LP/dual treatment. Archive model and input hashes, policy/configuration files, environment/license configuration without credentials, console logs, representative weights, accepted-year metadata, checkpoint identity and figure-generation scripts.

## 25. Goal-to-configuration checklist

| Study question | Required controls / review | Evidence to inspect |
|---|---|---|
| Effect of future information | Joint versus ordinary/partial myopic; matched costs, demand and year grid | Investment timing, objective boundary and committed history |
| Faster indicative planning | Representative capacity-only with declared samples | Sample metadata and annualization; no full-year feasibility claim |
| Chronological operation of planned assets | Automatic two-stage or trusted fixed bundle | Stitched/window balances, stock carryover, shortages and guidance slack |
| Industrial electrification | Category/regular/complex applicability, HPs, transition and resource limits | Useful-service electric share, final electricity, HP COP and build constraints |
| Industrial thermal flexibility | Category mode plus industry storage and eligible service data | Charge/discharge, useful heat, energy/power capacity and losses |
| Alternative industrial process routes | Complex sectors and compatible process/product inputs | Product activity, component energy, legacy replacement and process carbon |
| E-fuel production | Integrated e-fuel/Oil-Gas recipe plus final demand and feedstocks | H2/CO2/electricity/heat inputs and carrier balances |
| Fossil-product export sensitivity | `allow_fossil_fuel_exports`, prices, reserves and external routes | Outside fossil exports, refinery activity, revenue and emissions |
| Process emissions near a zero cap | Capture/geological eligibility or justified LULUCF budget offsets | Gross/net process emissions, injections, inventory and removal accounting |
| Restrict geological credit to process carbon | Separate process/other carbon balances | Tagged capture/stripping and geological source ledger |
| Standalone hydrogen network | No e-fuels, H2 balance, pipelines/compressors | H2 production, demand, link flow/losses and auxiliary electricity |
| Maritime/product imports | Terminals and active allowed routes in the matching schema | Throughput, arrivals, inventory, direction and annual supply bounds |
| HVDC expansion | Eligible HVDC links, converter/cost/build data | New transfer capacity, delivered flows and losses |
| Isolated-system study | Deactivate/constrain outside routes, preserve complete domestic balances | Zero outside exchange and resulting shortages/capacity |
| Accelerated fleet electrification | Floors, turnover, purchases, infrastructure and compatibility | Service shares, physical stocks, energy and charging/refueling |
| Alternative ICE/marine fuels | Pathways, blends, paid upgrades and pilot fuel | Compatible fuel shares, retrofit stock/cost and emissions |
| Basic-load flexibility | Daily/weekly DSM plus budgets, rollout and costs | Block conservation, moved MWh, power and costs |
| Industrial product border pricing | Product model plus industrial CBAM | Origin/destination footprint, liability, credits and fiscal allocation |
| Industrial domestic pricing | Product module plus domestic-price policy | Direct territorial emissions and domestic payments |
| Electricity border/national policy | One permitted Option, Myopic and intensity history | Eligible flow, price/intensity signal and separate carbon charges |
| Renewable electricity target | RPS path and native qualifying generation sets | Native numerator/denominator; distinguish imported/all-energy origin |
| Tighter solution-quality acceptance | Provisional off, warning-only off, appropriate physical gates | Solver status, physical residuals and every explicit slack |

## 26. Evidence and author-supplied implementation notes

The following distinctions are essential when using this guide in a report:

| Evidence category | What it supports |
|---|---|
| Inspected source/input snapshot | Exact defaults, named equations, guards, schema and option coverage recorded here |
| Supplied module/integration reports | Their stated component and example validation scope, including recorded baseline exceptions |
| Author's implementation explanation | Intended e-fuel/Oil-Gas pairing, process-carbon handling, pooled/mixed industry, tested non-metallic-mineral scope and network interpretation |
| Author-reported HR four-zone runs | Repeated annual experience with HVDC, H2 transmission and terminals; no new logs reproduced during documentation |
| Author-reported newer no-e-fuel intra-annual stability | A report about that working version; not automatic certification of every delivered e-fuel case |
| This documentation build | Static source linkage, complete option explanations, rendered equations, image/link/package integrity and unchanged original model files |

No full national optimization was run to produce the manual. Other complex sectors, incomplete pollutant code, flagged electricity Option 4 behavior, changes in time sampling and combinations outside the reported tested cases require their own validation. This distinction preserves the value of the available evidence without extending it to unsupported results.
