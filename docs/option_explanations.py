"""Editorial explanations for every public setting in the inspected snapshot.

Data only: importing this documentation module never imports or runs H2RES.
"""

MAIN = r'''
scen|Scenario and results/history identifier. Change it for a new experiment; the text does not select years, sectors or policies.
model_policy_dat|Physical/economic policy module executed before most main switches. Its values are visible in the shared model namespace.
runtime_policy_dat|Temporal and numerical policy module. Change sampling, rolling windows and solver parameters here, not in an unrelated workbook.
rps_inv|Add the native renewable-electricity generation-share constraint using the selected policy workbook. False removes this constraint; it does not remove renewable technologies or carbon prices.
carbonLimit|Apply the planning emissions cap or applicable rolling budget. False removes this budget, while ETS/CBAM costs and technical capture constraints may remain.
lulucf_removals_active|Include the configured land-use removals allowance in carbon accounting. It offsets the permitted net budget and is not a CO2 capture, transport or storage technology.
lulucf_removals_dat|Optional System/year removal trajectory. Check tCO2-equivalent/year and its interaction with the fixed removal setting.
res_inv|Select renewable-investment reporting/plot branches. This is not the RPS switch and does not independently permit or forbid renewable investment.
hydro_storage|Construct reservoir/pumped-storage operating equations for eligible hydro units. Turning it off is a different hydro formulation, not proof that hydro can meet the same chronology.
save_csv|Request applicable CSV result exports. Preserve these for history handoffs and audits; plots alone do not replace the required histories.
ceep_limit|Add the surplus-electricity cap relative to the modeled demand boundary. The surplus penalty can remain in the objective when this cap is off.
Myopic|True selects sequential planning with accepted historical decisions. False selects joint foresight unless a higher-priority automatic or fixed-dispatch workflow applies. Electricity CBAM Options 1–4 require True.
partial_perfect_foresight|In ordinary myopic planning, retain full-hour current-year operation and sampled future years within the configured lookahead. It does not mean all those future years have been validated hourly.
simple_curves|True reads reusable period-based inflow/availability curves. False expects the supported year/period schema. It is an input-layout choice, not a representative-time or spatial-resolution selector.
outside_system_availability|Apply additional hourly outside-grid import/export availability from the supplied shares and normalized curves. Turning it off does not remove every transfer-capacity or annual-trade limit.
outside_system_supply_shares_dat|Outside-system supply composition used to construct available trade. Keep System and technology mappings consistent.
outside_system_normalized_curves_dat|Hourly normalized availability by outside supply type. Values constrain trade rather than create domestic generator stock.
generation_source_calibration_active|Apply supplied source/fuel generation calibration targets in their scoped years. Removing calibration frees that restriction but does not alter the generator inventory.
hydro_generation_cap_active|Apply the extra hydro generation cap from policy. Reservoir energy and turbine limits still have their own equations.
outside_trade_calibration_active|Apply configured annual outside-trade calibration targets. Distinguish these targets from hourly availability and network capacity.
dh_chp_base_year_heat_calibration_active|Match scoped district-CHP base-year heat to entered plant targets. Requires matching generator IDs and active heat demand.
dh_chp_heat_yoy_limit_active|Constrain annual changes in CHP heat according to the model-policy rate, historical tolerance and reduction-limit horizon.
model_heating|Enable heating demand, technologies and balances. Several legacy industry cost definitions are nested within heating in this source, so an industry run with heating disabled is not a documented fully costed preset.
ratio_heat_indv|Enable the legacy individual-boiler production/capacity constraint branch. Do not interpret this as a simple population-allocation or fixed fuel-share option.
heating_shares_regulate|Add links between heating technology shares, installed capacity and scaled peak demand. This is additional to annual energy balances.
individual_heat_pump_storage|Enable local heat storage in the individual-HP branch. Requires heating and eligible individual HPs; it is separate from district or industrial thermal storage.
DH_Storage|Enable the applicable district heat/cooling storage branch. Storage requires its own energy/power parameters and boundary conditions; it is not the industrial category store.
NoResToHeatInv|Legacy inverted gate: False permits the normal individual-HP electricity/capacity equations; True skips those gated equations. Do not use True as a general ban on renewable electricity feeding heat or as a safe freeze-investment option.
model_Thermal_units|Include eligible individual fuel-boiler technologies when heating is enabled. Existing/retirement and investment tables still determine available capacity.
model_Thermal_units_DH|Include eligible district fuel-boiler technologies when heating is enabled. CHP and district heat pumps remain separately controlled.
model_HP_units|Include individual heating HP technologies and their COP/electricity links. Requires coherent thermal demand, costs and COP data.
model_HP_units_DH|Include district-heating HP technologies. Industrial HPs have an independent policy switch.
model_Solar_indv_heating|Include individual solar-thermal supply when heating is enabled. This is solar heat, not PV generation.
model_Solar_DH|Include district solar-thermal supply when heating is enabled. Availability, conversion and storage inputs must exist.
model_cooling|Request the legacy cooling block and cooling inputs. It is off in the delivered case and was not validated by this documentation exercise.
electric_heating_yoy_limit_active|Apply annual increase/decrease limits to the configured individual electric-heating technologies. These restrict transition rates, not each hour's dispatch directly.
individual_gas_heat_yoy_limit_active|Apply the entered annual gas-heating transition limits and reduction horizon to individual boilers.
fossil_heating_nonincrease_active|Prevent annual fossil heat from increasing in the applicable individual/DH scopes. Disabling it does not automatically cancel the boiler phaseout.
fossil_boiler_phaseout_active|Apply fuel-specific boiler retirement/zero-output deadlines. CHP is excluded from this boiler-specific rule; carbon policy remains separate.
Option_1|Electricity CBAM at the border only. Select at most one electricity option and use Myopic=True; supply membership, prices, transfers and valid carbon-intensity history.
Option_2|Electricity CBAM with a national carbon tax/ETS representation. Review domestic-versus-border accounting, membership and price trajectories; do not enable alongside another electricity option.
Option_3|Electricity national ETS representation with the applicable EU-price/border relationship. It is a distinct scenario branch, not an automatic calibration to current law.
Option_4|Mixed electricity national/border carbon-tax branch. Inspect the national-cost auxiliary and equations before use: the supplied structural notes flag an auxiliary without its own nonzero defining equation. Do not present this as an independently validated policy preset.
include_secc_links|Include eligible secondary electricity transfer routes through intermediate zones. Requires complete secondary route mappings and compatible capacities/losses.
model_simple_industry|Enable the separate fixed-recipe product-industry module. Its configure step disables overlapping legacy industry/transport, e-fuels, H2 and capture blocks and changes active example systems. It is not the pooled flex-tech worksheet.
industry_cbam_active|Apply industrial product CBAM in simple-industry mode, using supplier origin, final destination and embedded footprint. It is separate from electricity Options 1–4.
industry_carbon_pricing_active|Apply the simple-industry domestic carbon-price policy. Independent of industrial CBAM; requires the product module and complete plant/year policy rows.
industry_external_imports_active|Allow eligible additional outside product suppliers in simple-industry mode. Their annual/hourly budgets remain binding. Europe background supply retains its restricted Europe-market treatment.
industry_external_exports_active|Allow optional non-EU product sales in simple-industry mode. Mandatory domestic/Europe demand is not disabled by turning this off.
steel_flexible_operation|Permit hourly operation of product plants marked flexible. False uses the applicable within-day constant-operation formulation, not mandatory full-load production.
simple_industry_dat|Separate product-industry workbook with plants, recipes, markets, suppliers, prices, carbon policy and baseline load removals.
model_transport_and_industry|Enable legacy transport/industry data, equipment and associated carrier blocks. E-fuel recipes and industry CAPEX have additional dependencies; turning this off is not a supported way to retain the same integrated e-fuel case.
industry_single_sector|Legacy single-sector branch. Keep False for the documented e-fuel, category and complex-industry cases. Pooled Industry_data rows are a separate mechanism.
model_industry_categories|Use temperature/service categories for detailed legacy industry and select the category technology/profile layout. Mutually exclusive with complex industry.
industry_category_electricity_case|Choose conservative or technical_2050. In the e-fuel category case, technical_2050 selects the nested technology workbook; it is an applicability sensitivity, not a target year selector.
industry_complex_electricity_case|Choose conservative or technical_2050 for the complex companion process workbook. Selects the corresponding process electricity-assumption file.
industry_storage|Enable category-specific industrial thermal storage. Requires transport/industry, categories and multi-sector operation; turn it off for regular or complex recipes.
industry_fuel_share_ramp_active|Enable general industrial transition envelopes in planning. They constrain annual adoption; hourly dispatch can still respond to prices and availability.
industry_fuel_share_s_curve_active|Permit the configured endogenous S-curve mode when general ramps are active. False forces the applicable flat-ramp interpretation; the independent annual electric-share control can remain active.
industry_electric_share_yoy_limit_active|Apply the combined direct-electric plus industrial-HP delivered-service share policy. This is a useful-service share, not an electricity-input fraction.
model_complex_industry|Select process-based replacement for configured industrial sectors. Categories must be False and legacy multi-sector industry must remain enabled. Non-metallic minerals is the author's tested scope; other sectors are not equally evidenced.
model_complex_non_metallic_minerals|Backward-compatible alias normalized together with model_complex_industry. Set both consistently when switching recipes so an old True alias cannot reactivate complex mode.
complex_industry_dat_efuel|Base companion process workbook for complex industry with e-fuels. The electricity-case selector can choose its technical_2050 variant.
complex_industry_dat_no_efuel|Base companion process workbook for complex industry without e-fuels. It must match the no-e-fuel technology and carrier representation.
two_stage_auto_mode|Run representative capacity planning followed by fixed-capacity rolling dispatch. The controller sets internal stage flags; supports sequential or joint capacity planning through Myopic.
lightweight_representative_weeks_mode|Run the automatic controller's representative capacity stage only and skip rolling dispatch. It enables automatic mode and is a screening workflow, not an hourly feasibility certificate.
two_stage_skip_stage1_shadow_exports|Skip the expensive stage-1 shadow-price export path in automatic mode. Ordinary investment/history outputs still need to be retained.
two_stage_resume_skip_completed_chunks|Skip chunks whose required stage-2 completion outputs are found. This is a resume convenience, not proof that changed inputs are compatible with old results.
two_stage_resume_reuse_stage1_bundle|Allow reuse of an existing stage-1 capacity bundle where its checks permit. Keep False after structural changes unless bundle identity and chronology are established.
myopic_resume_from_results|Resume ordinary myopic planning after the contiguous accepted completed prefix. False starts at the base year; a new scenario is safer than overwriting a prior experiment.
validate_completed_heating_policy_history|Request validation of completed heating histories against current rules. False does not certify old policies; it lets existing accepted years remain while unsolved years use current rules.
two_stage_timing_logs|Emit timing information for the automatic stage sequence. It changes diagnostics rather than the physical feasible set.
representative_capacity_mode|Internal/manual capacity-planning time-sampling selection. Automatic mode controls it itself. The legacy week-named parameters currently describe four 24-hour blocks.
fixed_capacity_mode|Freeze capacity from the dispatch bundle in the dedicated rolling path. Without rolling_dispatch_mode, main normalizes it back to False.
dispatch_stage_data_path|Path to the stage-2 pickle capacity bundle. Use a trusted bundle from the same model/data conventions; it is not an Excel input file.
export_stage2_dispatch_bundle|Export a capacity/state/metadata bundle after planning for later fixed dispatch. Automatic mode sets this during stage 1.
rolling_dispatch_mode|Select rolling-operation behavior. The standalone runner requires fixed_capacity_mode=True; True alone does not select that execution branch.
rolling_write_solution_quality|Write additional rolling solution-quality artifacts. Their presence is diagnostic; inspect whether the solve was provisional or warnings were allowed.
rolling_write_window_files|Save individual rolling-window outputs/checkpoints. Needed for an auditable interruption/resume workflow.
rolling_keep_results_in_memory|Retain rolling results in memory instead of relying exclusively on streamed/window files. Consider RAM use for many zones, carriers and hours.
data_read_cache_enabled|Cache repeated CSV/Excel reads inside a run using path, modification time, size and reader arguments. This is separate from internet/weather download caching.
data_read_cache_copy_deep|Return deep copies of cached frames to prevent later mutations from contaminating reused inputs. False changes memory/copy behavior and requires care with shared dataframes.
transport_investment_limits_active|Activate the applicable extra transport investment-limit policy. Vehicle service shares, stock turnover and electrification targets are independent restrictions.
transport_pathway_corrections_active|Apply fuel compatibility, paid physical conversions and supported drop-in fuel rules. Turning this off is not a calibrated unrestricted-conversion scenario.
transport_passenger_car_zero_fossil_2050_sensitivity|Apply the named zero-fossil passenger-car sensitivity. This is not automatically zero fossil use in every transport sector.
transport_allow_unconstrained_paid_upgrades_for_test|Test-only bypass for persisted paid-upgrade rows when pathway constraints are disabled. Do not use it for a reported policy case without establishing the missing stock/fuel constraints.
transport_no_base_year_vehicle_investment|Prevent base-year fleet additions in the applicable ordinary case. E-fuel mode overrides this to False to allow its nonzero initial electrification floors.
transport_max_share_limits_active|Enforce annual service ceilings from transport_all.max_share. A service-share ceiling is different from a vehicle-stock share.
transport_ice_hybrid_stock_share_non_increasing_active|Add per-family ICE/hybrid stock-share nonincrease. The delivered case leaves this off because aggregate electrification/history constraints already restrict transition and tiny redundant anchors can harm conditioning.
transport_electrification_limits_active|Apply selected electrification target paths. Requires the applicable sector/technology mapping and workbook targets.
transport_rail_electrification_link_active|Apply the optional linkage between rail electrification representations. Independent of the direct-electric share ceiling and battery-rail specifications.
transport_rail_direct_electric_share_limit_active|Cap direct-electric service for passenger and freight rail under the configured maximum share. It does not impose that share as a minimum.
rolling_auto_carbon_budget_slack|Allow the configured penalized automatic rolling carbon-budget recovery. Nonzero slack means the strict carbon allocation was relaxed and must be reported.
rolling_terminal_fuel_soc|Apply terminal/end-of-horizon fuel-inventory guidance or targets. This refers to end conditions, not only physical maritime terminals.
rolling_terminal_fuel_soc_hard_balance|Use hard end-inventory constraints in the applicable rolling branch. False permits the configured soft treatment; check actual slack use.
rolling_terminal_fuel_soc_link_sequential_years|Carry/coordinate terminal fuel-inventory targets across sequential years in the rolling workflow. Distinguish this from independent cyclic annual storage.
rolling_terminal_fuel_soc_ramp_targets|Ramp toward terminal inventory targets over the configured lead interval. Controls guidance timing rather than physical storage capacity.
rolling_resume_from_window_files|Reuse compatible solved rolling windows after interruption. Requires saved files, consistent metadata and coherent incoming stocks/budgets.
rolling_zero_stage1_fuel_soc0|Prevent representative planning storage capacity from receiving free initial fuel inventory. This is an energy-accounting boundary condition.
rolling_fuel_soc_stage1_floor|Permit the applicable stage-1 SOC floor guidance in rolling operation. Leaving it off avoids lifting chronological carryover to an unearned representative-week stock.
stage2_quantity_guidance_active|Guide stage-2 annual/rolling quantities toward stage-1 results with configured tolerance and penalties. Guidance is not identical to an unconstrained chronological reoptimization.
oil_refinery_product_generation_decline_active|Apply the extra refinery-product output-decline policy. Separate from product reserves, carbon limits and outside export permission.
transport_ice_hybrid_fossil_share_decline_active|Apply the extra ICE/hybrid fossil-fuel share-decline policy in its configured scope. Compatible non-fossil fuel operation can differ from retiring the entire vehicle.
transport_ice_fuel_share_ramp_active|Limit changes in ICE fuel composition using the entered change limit. This acts alongside conversion/blend compatibility.
biomass_heating_nonincrease_active|Prevent applicable annual biomass-heating expansion. It is a scenario restriction, not a statement that biomass cannot serve existing demand.
biomass_feedstock_limit_active|Apply the scoped biomass feedstock/resource limits. Do not equate carbon-neutral bookkeeping with unlimited sustainable supply.
model_efuel|Enable the e-fuel carrier, conversion/feedstock, storage and trade representation and select e-fuel input families. Use the author's integrated recipe with explicit Oil/Gas supply and matching CO2 handling; production remains an economic decision.
complex_industry_dat|Derived active companion process path after e-fuel and electricity-case selection. Do not edit this while leaving conflicting selectors unchanged.
use_HVDC|Include eligible HVDC electricity links and converter requirements. HVDC is a network technology under transmission, not a separate energy sector or a switch for all cross-border trade.
model_terminals|Enable terminals. With e-fuels, use the product-terminal/route tables; without e-fuels, use the standalone H2 terminal workbook and H2 balance. Activate individual assets and permitted flow directions in the applicable tables.
h2_terminal_dat|Standalone no-e-fuel H2 terminal workbook. Requires its terminals/routes schema, eligible active geography and H2_terminal cost years.
model_H2_transmission|Enable standalone H2 pipelines/compressors when e-fuels are off. Main disables this flag with e-fuels because carrier transmission already handles H2 there.
model_oil_and_gas_products_supply|Enable explicit Oil/Gas/refinery-product supply in the e-fuel representation. Main disables it without e-fuels. Enable it for the author's supplied integrated e-fuel recipe; review reserves, imports, storage and processing inputs.
allow_fossil_fuel_exports|Allow eligible fossil refinery products to leave the modeled systems. False prevents that outside revenue channel while retaining applicable internal deliveries.
exogeneous_NH3_demand|Add prescribed ammonia demand in e-fuel mode. Requires matching nh3_demand.csv and year/geography policy; endogenous ammonia feedstock demand is distinct.
non_CO2_polutants|Request an explicitly incomplete legacy pollutant branch. It is not a complete non-CO2 or lifecycle environmental assessment.
model_H2_supply_demand_balance|Request the standalone H2 supply-demand balance used by eligible non-e-fuel configurations. Other integrated flags can also build H2 balances; False does not necessarily erase every H2 term.
model_CC|Enable eligible industrial capture/stripper/reboiler equipment and constraints. Capture capacity, active rows, energy inputs and a CO2 destination are still required. DAC in e-fuel mode is a distinct source.
model_CO2_ammine_storeage|Enable capture-linked rich/lean-amine inventory flexibility. The historical misspelling is the actual configuration name. Capture off normalizes this option off.
model_CO2_post_gen_storeage|Enable post-capture CO2 capacity/inventory handling where capture/e-fuels permit it. Geological storage additionally requires eligible active storage rows, capacity/build limits and allowed provenance.
complex_industry_process_capture_required|Require the capturable share from eligible complex process sources to be captured. False lets budgets/economics decide; True does not remove uncapturable residual emissions.
separate_industry_process_carbon_balances|Track process and other carbon separately and restrict geological injections to eligible captured process carbon. DAC/combustion/imported CO2 cannot acquire process provenance merely by entering a common buffer.
DSM_day|Enable the daily basic-load shifting class. Combine with budget/rollout controls for the new constrained DSM formulation; does not automatically shift all sector-specific loads.
DSM_week|Enable weekly basic-load shifting. With both classes and budgets enabled, the weekly pool is a subset of the daily-capable potential, not an additional unrestricted allowance.
dsm_energy_budget_active|Apply moved-MWh budgets per daily/weekly block, counted once by half the absolute adjustment. These are separate from hourly power limits.
dsm_availability_ramp_active|Scale DSM energy availability from the global base year toward its configured full-availability year. Turning it off removes that rollout restriction, not every DSM bound.
shadow_prices|Request the applicable marginal/shadow-price export workflow. An LP solution without an accepted basis/dual treatment is not automatically an interpretable market-price forecast.
solver_stage1_auto_retry_suboptimal|Allow the optional stronger generic retry for problematic stage-1 outcomes. Off in the delivered case; the separately enabled annual aggregation retry can still operate.
solver_stage1_annual_pf_aggregation_retry|Retry eligible annual-myopic problems using the configured alternate aggregation setting. Despite its name it applies with or without partial foresight in this snapshot.
solver_allow_provisional_solution|Permit acceptance of an eligible non-certified/provisional point within configured checks. True does not convert SUBOPTIMAL or TIME_LIMIT into OPTIMAL.
solver_postoptimal_checks_warn_only|Let applicable postoptimal balance/bound/diagnostic checks warn instead of abort. For a stricter study set False and inspect the independent annual-CC gate and all remaining slack mechanisms.
solver_enable_dual_simplex_fallback|Permit Method=1 recovery after the applicable failed/poor barrier outcome. Recovery can have its own focus, threads and unlimited time limit.
solver_finalize_stalled_barrier_with_crossover|Attempt crossover finalization after an eligible barrier stall. It changes recovery behavior, not the physical model.
solver_skip_dual_simplex_after_acceptable_stall|Skip the simplex recovery after an accepted stall in the applicable path. Leaving False preserves the fallback attempt.
write_solver_diagnostics|Write available scale/quality diagnostic artifacts. This does not itself enforce strict acceptance.
solver_diagnostics_on_problem_only|Restrict expensive diagnostics to problematic cases. False can substantially increase time and files on otherwise clean runs.
solver_diagnostics_compute_kappa_exact|Opt into exact conditioning calculations. These can be very expensive and are not a prerequisite for an ordinary run.
disable_transport_infrastructure|Inverted debug control: False retains fleet-linked EV charging/H2 refueling stock and cost constraints; True suppresses them and changes the study boundary.
transport_infrastructure_dat|Technology/cost/connection requirements for fleet-linked transport infrastructure.
transport_infrastructure_existing_dat|Existing infrastructure stock by active geography. Keep it consistent with the fleet and technology input conventions.
fuel_price_dat|Primary fuel-price input; distinguish it from e-fuel policy carrier prices and electricity trade prices.
inflows_dat|Hydro inflow profiles using exact reservoir/pumped-hydro IDs and the selected simple_curves schema.
heat_demand_dat_indv|Individual heating service profiles. Annual growth is applied through the applicable policy paths.
cool_demand_dat_indv|Individual cooling profiles for the optional cooling representation.
heat_demand_dat_DH|District-heating service profiles; use the expected delivered/network-loss boundary.
cool_demand_dat_DH|District cooling service profiles for the optional cooling block.
ev_transpload_dat|Transport activity, plug-in and V2G timing input. These are not interchangeable with annual service quantities.
transploaddemand_dat|Annual transport-service demand by the native sector/geography keys.
importcost_dat|Electricity import-price input for the selected trade formulation. Fuel purchases have separate prices.
heat_dem_industry_dat|Industry useful-service timing path. Later assignment selects category profiles when categories are enabled, otherwise industry_heat.csv.
genco_dat|Generator inventory with exact asset names, stock, location, efficiency, retirement, CHP and storage parameters.
policy_dat|Derived choice of policy_efuel.xlsx or policy.xlsx. The workbook horizon and trajectories must match the selected technology representation.
demand_dat|Basic electricity demand by period/System/Zone. Sector-accounting adjustments must avoid double counting.
demand_industry_el|Industry electricity baseline/accounting input used by the reader's sector decomposition.
demand_heating_el|Heating electricity baseline/accounting input used by the reader's sector decomposition.
solar_thermal_aval|Solar-thermal availability input. It is separate from renewable generator/PV availability.
flex_tech_name|Initial basename used to construct the technology workbook. Flags append e-fuel/category/complex suffixes before reading.
flex_tech_directory|Technology directory; the e-fuel category technical case changes it to the nested variants/technical_2050 folder.
flex_tech_dat|Derived final technology-workbook path. Check the reader's selected path rather than assuming the open Excel tab is active.
el_hourly_cost_dat|Hourly electricity price input for applicable cost/trade operations; keep its period and geography schema consistent.
_data_read_cache|Internal ordered cache created at runtime. Do not use it as a user-facing scenario parameter.
_excel_file_cache|Internal cached Excel reader handles. Do not change it to select another workbook.
_data_read_cache_stats|Internal hit/miss/read-time counters. They describe local file-reading performance, not API requests or model feasibility.
'''

POLICY = r'''
generation_annual_build_limit_multipliers|Multiply scoped generator annual build allowances by exact unit ID. Values above one permit faster additions, not higher weather availability or free capacity.
dh_chp_heat_max_annual_change|Relative annual CHP heat-change allowance; 0.25 denotes 25% under the implemented historical/interval rule.
dh_chp_heat_reduction_limit_years|Number of years over which the extra CHP heat-reduction restriction is applied; separate from plant technical lifetime.
dh_chp_heat_history_tolerance_mwh|MWh numerical allowance when comparing saved/current annual CHP heat. Do not use it as an intended heat-supply slack.
individual_gas_heat_max_annual_change|Relative annual individual gas-boiler heat-change allowance.
individual_gas_heat_reduction_limit_years|Duration of the extra individual-gas heat reduction restriction.
fossil_heating_history_tolerance_mwh|MWh tolerance on historical fossil-heating comparisons, not a policy exemption.
fossil_boiler_phaseout_years|Fuel-to-calendar-year boiler phaseout mapping. The delivered coal/gas/oil years are scenario choices; CHP is handled separately.
dh_chp_base_year_heat_targets_twh|Exact CHP asset/zone/System base-year heat targets in TWh. Requires matching identifiers and calibration enabled.
lulucf_removals_fixed_tco2e_per_year|Fixed annual removal allowance in tCO2-equivalent for the supported accounting path. Default zero; inspect its relationship to CSV/scoped removals before changing it.
electric_heating_max_annual_decrease|Relative annual reduction allowance on the configured individual electric-heating service scope.
electric_heating_max_annual_increase|Relative annual increase allowance on the configured individual electric-heating scope.
electric_heating_week_hours|Block length for applicable electric-heating history comparisons; 168 hours is a week, not a representative sample count.
electric_heating_individual_units|Exact technologies included in the individual electric-heating transition policy.
industry_fuel_share_max_change_per_year|General fuel/service share-change allowance in the selected ramp formulation. Its interpretation differs from an equipment MW build limit.
industry_fuel_share_ramp_mode|Select the supported flat/endogenous_s_curve transition interpretation, subject to main switches. This is a scenario adoption rule.
industry_fuel_share_s_curve_initial_fraction|Seed fraction for adoption envelopes; not an additional physical service demand or measured adoption rate.
industry_fuel_share_s_curve_growth_rate|Growth parameter in the adoption envelope. Increasing it relaxes the permitted transition speed under that formula.
industry_fuel_share_s_curve_reference_years|Reference interval used so annual versus sparse decisions do not repeatedly restart seeds/tolerances. Must meet the helper's integer/grid compatibility checks.
industry_fuel_share_s_curve_completion_year|Finite transition deadline. Default 2045 completes the applicable fossil-combustion phaseout envelope; None retains the historical open-ended treatment.
industry_fuel_share_s_curve_directions|Explicit increase/decrease/auto directions by asset tuple, unit or fuel. Applicability ceilings remain separate; asset/unit overrides take precedence.
industry_electric_share_max_annual_decrease|Relative maximum decrease of combined direct-electric/HP useful-service share; 10% of a 40% share gives 36%, not 30%.
industry_electric_share_history_tolerance|Small share-unit comparison allowance. It is not a percentage-point adoption budget.
transport_decom_max_share|Optional additional transport decommissioning-share parameter. None leaves the implemented default treatment; do not infer unlimited vehicle replacement without the other turnover constraints.
transport_turnover_years|Reference fleet turnover life used for the selected vehicle groups.
transport_turnover_units|Exact vehicle/transport units included in the extra turnover policy.
transport_turnover_ramp_start_year|Start calendar year for the turnover-policy ramp.
transport_turnover_ramp_full_year|Calendar year when the turnover ramp reaches its full setting.
transport_turnover_ramp_initial_share|Initial multiplier/share used by the turnover ramp; inspect its formula before interpreting a value above one.
TRANSPORT_TURNOVER_MAX_SHARE|Upper turnover-policy share in the applicable implementation; separate from a vehicle's transport_all service ceiling.
transport_existing_fleet_age_spread_years|Age-spread assumption for distributing retirement of inherited fleet stock.
transport_forbidden_investment_units|Exact units prohibited from receiving new investment by the applicable transport policy. An empty tuple imposes no exclusions here.
transport_inv_max_share_by_unit|Unit-specific new-investment share ceilings, with the supported all fallback. Does not directly set final service shares.
transport_inv_total_max_by_sector|Absolute new-fleet investment caps by sector. An empty mapping supplies no extra sector-specific caps here.
transport_inv_max_ramp_start_year|Start year for investment-share ceiling rollout.
transport_inv_max_ramp_full_year|Year when investment-share ceilings reach their full configured values.
transport_inv_max_ramp_initial_share|Initial rollout fraction for the applicable investment ceilings.
transport_inv_declining_max_share_by_unit|Optional units whose investment ceilings decline along the configured path.
transport_inv_decline_start_year|Start year of optional declining transport investment ceilings.
transport_inv_decline_end_year|Final year of optional declining investment ceilings.
transport_inv_decline_final_share|Endpoint fraction for the configured declining investment ceiling, not an automatic zero-fossil rule.
transport_stock_max_share_year|Reference year for optional stock-share ceilings.
transport_stock_max_share_by_unit|Optional final/target stock-share caps by unit. Empty supplies no additional caps in this mapping.
transport_electrification_target_sectors|Sectors to which the selected electrification target policy applies. International shipping is not automatically included because aviation is listed.
transport_non_decreasing_stock_units|Exact transport units with the extra nondecreasing-stock requirement.
transport_rail_direct_electric_max_share|Maximum direct-electric rail service share in the separate passenger/freight cap; default 0.9 means a ceiling of 90%.
transport_rail_battery_specs|Battery-rail storage/charging specifications by unit, using native equipment units. Distinct from overhead/direct electric rail.
stage2_carbon_budget_mode|Rule for allocating carbon across rolling operation. The supplied cumulative_weighted mode uses cumulative budgets with configured weights, not independent unconstrained hourly caps.
stage2_carbon_hour_weight|Contribution of uniform time to the applicable rolling carbon-allocation weights.
stage2_carbon_heat_weight|Contribution of heat activity to rolling carbon-allocation weights.
stage2_carbon_el_weight|Contribution of electricity activity to rolling carbon-allocation weights. Zero removes this weighting component, not electricity emissions.
stage2_carbon_auto_slack_cost|Penalty for automatically introduced rolling carbon-budget slack. The native cost scale must be preserved when reporting it.
stage2_carbon_slack_cost|Additional configured rolling carbon-slack cost. Zero here does not imply the auto-slack mechanism is cost-free.
rolling_refinery_hourly_cap_multiplier|Scale the applicable stage-2 refinery hourly capacity allowance. It is a dispatch restriction, not a change in resource reserves.
rolling_h2_balance_shortage_cost|Penalty on supported rolling H2 shortage variables. Nonzero shortage indicates relaxed service/balance requirements.
rolling_industry_cap_shortage_cost|Penalty for supported rolling industry-capacity shortfalls. Report the slack rather than treating it as physical capacity.
rolling_terminal_fuel_soc_tolerance|Allowed end-inventory target deviation in the applicable fuel-stock guidance rule.
rolling_terminal_fuel_soc_slack_cost|Penalty for fuel terminal/end-stock slack. Inspect native stock and objective units before changing it.
rolling_terminal_fuel_soc_lead_hours|Lead time over which terminal fuel-stock targets begin influencing dispatch.
rolling_terminal_fuel_soc_ramp_exponent|Shape exponent of the terminal-stock target ramp; does not change the underlying stock balance.
storage_year_continuity_mode|Select the supported annual storage boundary convention. The delivered cyclic setting should not be described as unrestricted interannual stock carryover.
efuel_dh_heat_feedstock_aliases|Labels recognized as district-heat feedstock to e-fuel conversion. Such feedstock is served by the heat balance, not a free exogenous input.
stage2_quantity_guidance_tolerance|Relative band around stage-1 quantity guidance in stage 2.
stage2_quantity_guidance_abs_tolerance|Absolute comparison allowance accompanying the relative guidance band.
stage2_quantity_guidance_slack_cost|Penalty on allowed quantity-guidance deviations. Guidance compliance and physical feasibility are different checks.
oil_refinery_product_generation_change_limit|Rate limit used when the extra refinery output-decline control is enabled.
refinery_process_fuel_share|Refinery process-energy fraction, default 0.08. This is additional process demand, not product output efficiency by itself.
refinery_process_fuel_co2_key|Fuel/emission-factor key used for refinery process combustion.
transport_ice_hybrid_fossil_share_decline_scope|Scope of the optional ICE/hybrid fossil-share decline rule; annual is the delivered setting.
transport_ice_fuel_share_change_limit|Change allowance for ICE fuel composition when the corresponding main ramp is enabled.
biomass_heating_fuel_aliases|Fuel labels recognized by biomass-heating restrictions.
h2_transmission_cost_aliases|Map standalone H2 pipeline technologies to supported cost keys. Does not add missing technical or geographic assets.
transmission_transformer_units|Map electricity link technologies to converter/transformer cost and equipment keys, including HVDC.
h2_pipeline_compressor_unit|Technology name for standalone H2 compressor requirements.
transmission_duplicate_policy|How duplicate link records are reconciled. Delivered first keeps the first applicable record; deterministic selection is not proof conflicting inputs are correct.
active_zone_overrides|Optional explicit active-geography override. None retains normal workbook/configuration scoping; demands and links must still cover any new active zones.
simple_industry_active_zones|Active zone/System pairs when the separate product module is configured. The delivered HR1/RS1/BA1 example is different from an arbitrary NUTS3 case.
simple_industry_grid_fallback_tco2_per_mwh|Fallback electricity intensity used by applicable product-industry reporting. Distinguish fallback reporting factors from physical modeled territorial generation emissions.
electricity_cbam_future_intensity_tco2_per_mwh|Optional exogenous future zone/year factors for electricity CBAM lookahead. Missing required realized history must not be silently replaced by zero.
co2_storage_capex_input_unit|Declared geological/buffer storage cost basis. MEUR/t is a stock-capacity cost, not MEUR per tonne/hour of injection.
co2_amine_tank_capex_input_unit|Declared amine inventory-capacity cost basis. Keep tonne-stock and hourly capture equipment costs separate.
stat_grid_eff|Generic stationary electricity-storage/grid delivery-efficiency parameter in its reader/balance convention. Do not apply it twice to stock and delivered output.
ceep_price|Penalty for surplus electricity in the implemented objective. It can remain active when ceep_limit=False.
noload_el_cost|Penalty for unserved electricity. It is an entered scarcity parameter, not a measured national value of lost load.
discount_rate|Economic discount rate for cross-year objective weighting. Different from capital financing and numerical objective scaling.
discount_base_year|Reference year for discount factors. Changing it changes the reported present-value basis.
capital_finance_rate|Finance rate for annual capital-service payments over equipment life.
fuel_storage_capex_aliases|Explicit cost-key fallbacks for carrier stores; default N2_stor uses Gas_stor costs as an inherited assumption.
fuel_storage_fixed_opex_fraction|Annual fixed-cost fraction for supported fuel storage equipment, relative to its configured capital basis.
oil_gas_initial_soc_fraction|Initial Oil/Gas inventory fractions under the supported supply boundary. Check zero-initial-stage-1 and rolling-stock rules before assuming the fraction is always applied.
industry_electrification_full_applicability|Use the supported full-electrification applicability setting while retaining other process, transition, resource and capacity limits. It does not mandate 100% electrification.
industry_heat_pumps_active|Enable eligible industrial HP technologies and their shared applicability/source budgets. Independent of building HP switches.
industry_hp_profiles_dat|Useful-service profile source used for industrial HP applicability/demand checks.
complex_industry_sectors|Exact selected complex process branches. Only these replace corresponding legacy service demand; delivered default is Non_metallic_minerals.
industry_external_steam_efficiency|Conversion assumption used when externally supplied industry steam/heat is attributed to input energy and emissions. Do not treat imported heat as automatically emission-free.
'''

RUNTIME = r'''
dsm_availability_full_year|Calendar year at which the enabled linear DSM rollout reaches its target; based on the original global base year.
dsm_daily_energy_fraction|Daily-capable moved-energy pool including the weekly subset. It is a block-energy ceiling, not an hourly MW share.
dsm_weekly_energy_fraction|Weekly-capable subset of the daily pool when both classes are enabled. The two values must not be added as independent full potentials.
dsm_shift_fraction|Shared hourly absolute adjustment power cap as a fraction of baseline electricity load.
dsm_capacity_cost_eur_per_mw_year|Annual enabling resource cost per MW of available DSM adjustment, in EUR/MW/year.
dsm_shift_cost_eur_per_mwh|Real activation/discomfort cost per MWh moved, counted once, in EUR/MWh.
partial_foresight_representative_days|Number of future-year sampled blocks in ordinary partial foresight.
partial_foresight_day_hours|Hours per partial-foresight representative block; delivered 24.
partial_foresight_representative_day_start_hours|Explicit first-hour positions of future-year blocks. Keep them valid, nonoverlapping and compatible with the configured block count/length.
partial_foresight_lookahead_years|Calendar-year reach of each ordinary partial-foresight solve. None exposes the remaining horizon; 10 gives current year plus decision points no later than current+10.
representative_full_year_hours|Full-year hours used in representative annualization. The delivered 8760 convention is not automatically leap-year data support.
two_stage_stage1_export_timing|When stage-1 outputs are written. before_stage2 preserves capacity/history exports; off/skip/none can deprive later myopic chunks of expected investment CSVs.
representative_weeks_count|Number of representative capacity-stage blocks. Despite its historical name, interpret with representative_week_hours.
representative_week_hours|Length of each representative capacity block. Delivered 24, so four blocks are four days, not four weeks.
representative_week_start_hours|Start positions of representative capacity-stage blocks. Delivered aliases the four seasonal-day starts.
long_storage_guidance_default_band|Default allowed band for applicable long-duration storage guidance; zero requests the corresponding tight target band.
rolling_dispatch_granularity|day sets 48-hour lookahead/24-hour realization; week sets 336/168; custom uses the explicit window/step/realized settings.
rolling_window_size|Hours optimized per rolling solve when granularity does not overwrite it.
rolling_step_size|Hours by which the rolling origin advances; coordinate with the realized horizon.
rolling_realized_horizon|Hours committed/exported from each rolling solve. Later lookahead hours are guidance, not committed full-year results.
rolling_forecast_avg_dev_percent|Magnitude of the configured rolling forecast-deviation assumption; zero changes that forecast experiment, not perfect foresight automatically.
stage1_capacity_reserve_margin|Extra capacity margin in the applicable stage-1 sizing constraints; delivered zero. It is not a full reliability/N-1 reserve model.
rolling_unmet_industry_heat_cost|Penalty for supported rolling industrial-heat shortage. Review physical MWh and actual slack alongside its cost.
rolling_unmet_dh_heat_cost|Penalty for supported rolling district-heat shortage.
rolling_unmet_indv_heat_cost|Penalty for supported rolling individual-heat shortage.
data_read_cache_max_entries|Maximum retained local read-cache entries; separate from API/download caching and quota estimates.
solver_stage1_method|Primary Gurobi algorithm for capacity planning; delivered 2 (barrier). Method selection does not change physical constraints.
rolling_solver_method|Primary rolling dispatch algorithm; delivered 1 (dual simplex).
solver_stage1_numeric_focus|Numerical-care setting for the ordinary stage-1 solve. Larger values can increase numerical effort and runtime.
solver_diagnostic_method|Algorithm used to diagnose ambiguous/failing outcomes; separate from the normal method.
solver_diagnostic_time_limit_s|Diagnostic solve time limit in seconds. Nonpositive is treated as unlimited by the applicable wrapper.
solver_diagnostic_numeric_focus|Numerical focus for the independent diagnostic solve.
solver_diagnostic_aggregate|Presolve aggregation setting in the diagnostic solve.
solver_objective_scale|Positive multiplier applied to the assembled MEUR objective before optimization. The delivered value 1000 changes its numerical scale; restore native economic units when interpreting solver objectives and duals.
solver_stage1_scale_flag|Gurobi scaling choice for the primary solve, in addition to explicit model row/column scaling.
solver_stage1_aggregate|Primary presolve aggregation setting; delivered zero to preserve difficult transport equalities.
solver_stage1_annual_pf_retry_aggregate|Alternate presolve aggregation in the eligible annual retry; does not mean all future operations are modeled hourly.
annual_accounting_row_scale|Explicit scaling divisor for applicable annual accounting rows. Physical audits must restore the original units.
fuel_storage_balance_row_scale|Explicit scaling divisor for carrier-stock balances; not a physical storage efficiency.
fuel_storage_capacity_row_scale|Explicit scaling divisor for carrier-store capacity rows; not a capacity multiplier.
co2_storage_cost_row_scale|Explicit scaling for CO2 storage cost equations; not a change in the cost assumption.
solver_stage1_bar_homogeneous|Homogeneous barrier selection in the applicable ordinary stage-1 branch.
solver_stage1_annual_s_curve_bar_homogeneous|Annual S-curve branch override of the ordinary homogeneous barrier setting.
solver_stage1_homogeneous_recovery|Permit the independent homogeneous-barrier recovery path when applicable.
solver_stage1_bar_conv_tol|Barrier convergence tolerance for the ordinary applicable branch; dimensionless numerical criterion, not a physical MW tolerance.
solver_stage1_annual_cc_bar_conv_tol|Barrier tolerance override in eligible annual carbon-capture solves.
solver_stage1_crossover|Gurobi crossover choice after barrier; zero disables normal crossover in the delivered case.
solver_stage1_crossover_basis|Crossover basis-construction setting used when that path is active.
solver_stage1_bundle_feasibility_tol|Primal feasibility tolerance used in the applicable dispatch-bundle solve/export path.
solver_stage1_time_limit_s|Stage-1 time limit in seconds. Nonpositive is treated as unlimited by the wrapper.
solver_stage1_auto_extend_attempts|Number of optional automatic time-limit extensions. Zero disables extensions, not the primary solve.
solver_stage1_auto_extend_s|Seconds added per enabled time-limit extension.
solver_stage1_retry_numeric_focus|Numerical focus in the optional generic stage-1 retry.
solver_stage1_retry_scale_flag|Gurobi scaling selection for that retry.
solver_stage1_retry_bar_homogeneous|Homogeneous barrier setting for that retry.
solver_provisional_max_constr_vio|Maximum solver-scaled constraint violation considered by the provisional-acceptance path. Physical-unit audits are independent.
physical_energy_balance_abs_tolerance|Absolute physical-energy residual tolerance for audited families after undoing row/column scaling; delivered 0.1 in their MW/MWh basis.
solver_provisional_max_bound_vio|Maximum solver bound violation considered for provisional acceptance.
solver_provisional_max_dual_vio|Maximum dual violation considered for provisional acceptance.
solver_provisional_max_dual_residual|Dual-residual acceptance threshold in the provisional path.
solver_provisional_max_barrier_gap|Relative barrier-gap threshold used by provisional acceptance; it is not proof of certified optimality.
solver_provisional_max_returned_objective_deviation|Allowed objective deviation in the relevant provisional returned-point comparison.
solver_require_annual_cc_quality|Require the additional annual-capture numerical/physical quality checks even for a nominally optimal point.
amine_mass_balance_abs_tolerance_t|Absolute amine-associated CO2 mass residual tolerance in physical tonnes; delivered 0.001.
solver_stage1_bar_iter_limit|Maximum primary barrier iterations before applicable recovery logic; not an hourly simulation count.
solver_stage1_threads|Requested primary solver threads. More threads do not guarantee faster solves or more accurate inputs.
solver_stage1_bar_order|Barrier fill-reducing ordering setting; -1 is automatic in the supplied configuration.
solver_auto_iis_max_rows|Matrix-size threshold for automatic IIS computation. An IIS is a conflict diagnosis, not a feasible solution.
solver_bar_stall_time_s|Configured barrier-stall timeout control; inspect the callback's zero/off handling rather than treating zero as an immediate abort.
solver_bar_stall_min_runtime_s|Minimum runtime before the applicable stall logic considers intervention.
solver_bar_stall_rel_improve|Relative improvement criterion in barrier-stall detection.
solver_bar_stall_accept_gap|Gap threshold for considering an otherwise stalled barrier point acceptable for the relevant recovery path.
solver_bar_stall_accept_compl|Complementarity threshold in stall-point acceptance.
solver_bar_stall_accept_primal_inf|Primal infeasibility threshold in stall-point acceptance.
solver_bar_stall_accept_dual_inf|Dual infeasibility threshold in stall-point acceptance.
solver_stalled_barrier_finalize_time_s|Time budget for an enabled crossover/finalization attempt after an eligible stall.
solver_fallback_numeric_focus|Numerical focus in the simplex fallback.
solver_fallback_time_limit_s|Fallback time budget; nonpositive is treated as unlimited in the applicable wrapper.
solver_fallback_threads|Requested fallback thread count.
electricity_price_zero_threshold_eur_per_mwh|Small electricity-price sanitation threshold in EUR/MWh. It can affect near-zero trade incentives and must be disclosed.
fuel_trade_price_zero_threshold_eur_per_mwh|Small fuel-trade price sanitation threshold in EUR/MWh; does not authorize free feedstock generally.
transport_stock_variable_scale_by_sector|Physical vehicles per scaled solver stock unit by sector. Export and audit quantities must be converted back to vehicles.
transport_service_variable_scale|Default service-variable scaling; changes numerical coefficients, not demand in physical units.
transport_service_variable_scale_by_sector|Sector overrides of service-variable scaling.
numeric_abs_min|Generic lower numerical sanitation bound used by supported readers/helpers. It is not a universal physical minimum flow.
numeric_abs_max|Generic upper numerical sanitation bound; inspect the field-specific reader before treating it as a physical capacity limit.
price_abs_max|Upper absolute price sanitation bound in the applicable reader conventions.
var_cost_abs_max|Upper absolute variable-cost sanitation bound in applicable readers.
transmission_km_abs_max|Upper link-length sanitation bound in kilometres.
fuel_storage_eff_min|Minimum accepted/sanitized carrier storage efficiency.
fuel_storage_eff_max|Maximum accepted/sanitized carrier storage efficiency; default one.
cap_inv_limit_active_max|Reader threshold used in deciding whether large investment limits are treated as active bounds. It is not a national resource estimate.
transport_coeff_eps|Small coefficient threshold used in transport equations/data handling.
transport_co2_block_hours|Hours per transport-carbon aggregation block; affects numerical formulation, not annual vehicle demand.
transport_historical_stock_zero_epsilon|Small historical-stock cleanup threshold in the supported physical/scaled history path.
heating_stock_zero_epsilon_mw|MW threshold for negligible reconstructed heating stock.
heating_history_zero_epsilon_mwh|MWh threshold for negligible reconstructed heating history.
rolling_storage_state_roundoff_tolerance|Tolerance for small negative stock roundoff during rolling carryover. Materially negative inventory is not authorized.
rolling_h2_reserve_margin_mwh|Small MWh numerical headroom in the applicable H2 inventory reserve envelope.
transport_physical_bound_tolerance|Physical vehicle bound-audit tolerance; distinguish it from solver-scaled column tolerances.
levelized_cost_min_annual_output_mwh|Minimum annual output for meaningful reported levelized EUR/MWh costs. Below-threshold ratios are not interpreted as reliable costs.
transport_inherited_stock_zero_epsilon|Physical vehicle threshold for negligible inherited net/retrofit stock; delivered 0.1 vehicle.
INDUSTRY_SHARE_ROUNDING_TOLERANCE|Share-rounding allowance used by industry input checks; not a new annual adoption budget.
COMPLEX_INDUSTRY_DEMAND_AUDIT_REL_TOL|Relative complex useful-service demand reconciliation tolerance.
COMPLEX_INDUSTRY_DEMAND_AUDIT_ABS_TOL|Absolute complex-demand reconciliation tolerance, used alongside the relative allowance in native service units.
transport_fixed_stock_abs_tolerance|Absolute physical-vehicle tolerance around fixed stage-2 stock pins.
transport_stock_relative_tolerance|Relative band/headroom around supported fixed stocks and technology/share caps; delivered 0.001 means 0.1%.
'''

PATHWAYS = r'''
transport_marine_capex_multiplier|New marine methanol/ammonia equipment CAPEX multipliers relative to the supported baseline; not energy efficiencies.
transport_marine_pilot_energy_share|Pilot-fuel energy fraction in supported marine conversion recipes. Include both pilot and main-fuel emissions/costs.
transport_marine_retrofit_capex_fraction|Cost fractions for supported marine methanol/ammonia retrofits. Retrofitting consumes eligible incumbent stock.
transport_marine_retrofit_remaining_years|Remaining service life assigned to supported marine retrofits.
transport_physical_upgrade_capex_fraction|Baseline-CAPEX fractions for supported physical fuel upgrades by fuel family.
transport_physical_upgrade_remaining_years_by_sector|Remaining life of paid physical upgrades by transport sector.
transport_physical_upgrade_capex_meur_per_vehicle|Optional explicit per-vehicle upgrade CAPEX overrides. Empty uses the implemented fraction-based treatment.
transport_upgraded_max_volume_share|Maximum supported upgraded-fuel blend volume share. Volume shares require the model's energy-conversion treatment before use in energy balances.
transport_drop_in_fuels|Fuel labels treated as compatible drop-in pathways in the supported equipment representation. This is a model compatibility assumption, not universal real-engine certification.
transport_fame_max_volume_share|Unmodified-equipment FAME volume-blending ceiling, default 7%.
transport_ethanol_max_volume_share|Unmodified-equipment ethanol volume-blending ceiling, default 10%.
transport_methanol_max_volume_share|Unmodified-equipment methanol volume-blending ceiling, default 3%.
transport_synthetic_jet_max_volume_share|Synthetic jet volume-blending ceiling in the supported scenario; default one. Treat certification and real fleet applicability separately.
'''


def mappings():
    output={}
    for filename,text in [('main.py',MAIN),('policy/model_policy.py',POLICY),
                          ('policy/runtime_policy.py',RUNTIME),('policy/transport_pathways.py',PATHWAYS)]:
        for line in text.strip().splitlines():
            name,explanation=line.split('|',1)
            key=(filename,name)
            assert key not in output, key
            output[key]=explanation
    return output
