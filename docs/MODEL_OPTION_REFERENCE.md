# Complete configuration option reference

**Scope:** every assignment in the inspected top-level `main.py` and its three policy modules. This reference covers all 381 recorded assignments, including repeated/derived declarations and internal cache objects; the coverage report is generated from the actual configuration inventory. Function-local solver implementation variables are not additional user switches.

Each row gives the entered expression, its source line and its operational meaning. The entered default is not always the effective value: normalization, parent modules, workbook eligibility and execution-stage overrides still apply. Consult the [configuration guide](MAIN_CONFIGURATION_GUIDE.md) for dependencies and complete workflows, and the [equation chapter](MATHEMATICAL_FORMULATION.md) for physical/economic interpretation.

Boolean controls accept Python `True` or `False`. Dictionary keys, exact unit labels, native units and supported string values matter. An empty mapping supplies no extra overrides for that mapping; it does not necessarily disable other model constraints. A setting marked diagnostic, internal, incomplete or test-only is not a supported physical scenario selector.

## main.py

| Setting and source | Entered value / expression | Meaning and effect |
|---|---|---|
| `scen` (`main.py:20`) | `'industry_CC_5y'` | Scenario and results/history identifier. Change it for a new experiment; the text does not select years, sectors or policies. |
| `model_policy_dat` (`main.py:25`) | `'./policy/model_policy.py'` | Physical/economic policy module executed before most main switches. Its values are visible in the shared model namespace. |
| `runtime_policy_dat` (`main.py:26`) | `'./policy/runtime_policy.py'` | Temporal and numerical policy module. Change sampling, rolling windows and solver parameters here, not in an unrelated workbook. |
| `rps_inv` (`main.py:37`) | `True` | Add the native renewable-electricity generation-share constraint using the selected policy workbook. False removes this constraint; it does not remove renewable technologies or carbon prices. |
| `carbonLimit` (`main.py:38`) | `True` | Apply the planning emissions cap or applicable rolling budget. False removes this budget, while ETS/CBAM costs and technical capture constraints may remain. |
| `lulucf_removals_active` (`main.py:39`) | `False` | Include the configured land-use removals allowance in carbon accounting. It offsets the permitted net budget and is not a CO2 capture, transport or storage technology. |
| `lulucf_removals_dat` (`main.py:40`) | `'./data/lulucf_removals.csv'` | Optional System/year removal trajectory. Check tCO2-equivalent/year and its interaction with the fixed removal setting. |
| `res_inv` (`main.py:41`) | `True` | Select renewable-investment reporting/plot branches. This is not the RPS switch and does not independently permit or forbid renewable investment. |
| `hydro_storage` (`main.py:42`) | `True` | Construct reservoir/pumped-storage operating equations for eligible hydro units. Turning it off is a different hydro formulation, not proof that hydro can meet the same chronology. |
| `save_csv` (`main.py:43`) | `True` | Request applicable CSV result exports. Preserve these for history handoffs and audits; plots alone do not replace the required histories. |
| `ceep_limit` (`main.py:44`) | `False` | Add the surplus-electricity cap relative to the modeled demand boundary. The surplus penalty can remain in the objective when this cap is off. |
| `Myopic` (`main.py:45`) | `True` | True selects sequential planning with accepted historical decisions. False selects joint foresight unless a higher-priority automatic or fixed-dispatch workflow applies. Electricity CBAM Options 1–4 require True. |
| `partial_perfect_foresight` (`main.py:46`) | `False` | In ordinary myopic planning, retain full-hour current-year operation and sampled future years within the configured lookahead. It does not mean all those future years have been validated hourly. |
| `simple_curves` (`main.py:47`) | `True` | True reads reusable period-based inflow/availability curves. False expects the supported year/period schema. It is an input-layout choice, not a representative-time or spatial-resolution selector. |
| `outside_system_availability` (`main.py:48`) | `True` | Apply additional hourly outside-grid import/export availability from the supplied shares and normalized curves. Turning it off does not remove every transfer-capacity or annual-trade limit. |
| `outside_system_supply_shares_dat` (`main.py:49`) | `'./data/outside_system_supply_shares.csv'` | Outside-system supply composition used to construct available trade. Keep System and technology mappings consistent. |
| `outside_system_normalized_curves_dat` (`main.py:50`) | `'./data/outside_system_normalized_curves.csv'` | Hourly normalized availability by outside supply type. Values constrain trade rather than create domestic generator stock. |
| `generation_source_calibration_active` (`main.py:54`) | `True` | Apply supplied source/fuel generation calibration targets in their scoped years. Removing calibration frees that restriction but does not alter the generator inventory. |
| `hydro_generation_cap_active` (`main.py:55`) | `True` | Apply the extra hydro generation cap from policy. Reservoir energy and turbine limits still have their own equations. |
| `outside_trade_calibration_active` (`main.py:56`) | `True` | Apply configured annual outside-trade calibration targets. Distinguish these targets from hourly availability and network capacity. |
| `dh_chp_base_year_heat_calibration_active` (`main.py:57`) | `True` | Match scoped district-CHP base-year heat to entered plant targets. Requires matching generator IDs and active heat demand. |
| `dh_chp_heat_yoy_limit_active` (`main.py:58`) | `True` | Constrain annual changes in CHP heat according to the model-policy rate, historical tolerance and reduction-limit horizon. |
| `model_heating` (`main.py:61`) | `True` | Enable heating demand, technologies and balances. Several legacy industry cost definitions are nested within heating in this source, so an industry run with heating disabled is not a documented fully costed preset. |
| `ratio_heat_indv` (`main.py:62`) | `True` | Enable the legacy individual-boiler production/capacity constraint branch. Do not interpret this as a simple population-allocation or fixed fuel-share option. |
| `heating_shares_regulate` (`main.py:63`) | `False` | Add links between heating technology shares, installed capacity and scaled peak demand. This is additional to annual energy balances. |
| `individual_heat_pump_storage` (`main.py:64`) | `False` | Enable local heat storage in the individual-HP branch. Requires heating and eligible individual HPs; it is separate from district or industrial thermal storage. |
| `DH_Storage` (`main.py:65`) | `False` | Enable the applicable district heat/cooling storage branch. Storage requires its own energy/power parameters and boundary conditions; it is not the industrial category store. |
| `NoResToHeatInv` (`main.py:66`) | `False` | Legacy inverted gate: False permits the normal individual-HP electricity/capacity equations; True skips those gated equations. Do not use True as a general ban on renewable electricity feeding heat or as a safe freeze-investment option. |
| `model_Thermal_units` (`main.py:67`) | `True` | Include eligible individual fuel-boiler technologies when heating is enabled. Existing/retirement and investment tables still determine available capacity. |
| `model_Thermal_units_DH` (`main.py:68`) | `True` | Include eligible district fuel-boiler technologies when heating is enabled. CHP and district heat pumps remain separately controlled. |
| `model_HP_units` (`main.py:69`) | `True` | Include individual heating HP technologies and their COP/electricity links. Requires coherent thermal demand, costs and COP data. |
| `model_HP_units_DH` (`main.py:70`) | `True` | Include district-heating HP technologies. Industrial HPs have an independent policy switch. |
| `model_Solar_indv_heating` (`main.py:71`) | `False` | Include individual solar-thermal supply when heating is enabled. This is solar heat, not PV generation. |
| `model_Solar_DH` (`main.py:72`) | `False` | Include district solar-thermal supply when heating is enabled. Availability, conversion and storage inputs must exist. |
| `model_cooling` (`main.py:73`) | `False` | Request the legacy cooling block and cooling inputs. It is off in the delivered case and was not validated by this documentation exercise. |
| `electric_heating_yoy_limit_active` (`main.py:74`) | `True` | Apply annual increase/decrease limits to the configured individual electric-heating technologies. These restrict transition rates, not each hour's dispatch directly. |
| `individual_gas_heat_yoy_limit_active` (`main.py:75`) | `True` | Apply the entered annual gas-heating transition limits and reduction horizon to individual boilers. |
| `fossil_heating_nonincrease_active` (`main.py:76`) | `True` | Prevent annual fossil heat from increasing in the applicable individual/DH scopes. Disabling it does not automatically cancel the boiler phaseout. |
| `fossil_boiler_phaseout_active` (`main.py:77`) | `True` | Apply fuel-specific boiler retirement/zero-output deadlines. CHP is excluded from this boiler-specific rule; carbon policy remains separate. |
| `Option_1` (`main.py:80`) | `False` | Electricity CBAM at the border only. Select at most one electricity option and use Myopic=True; supply membership, prices, transfers and valid carbon-intensity history. |
| `Option_2` (`main.py:81`) | `False` | Electricity CBAM with a national carbon tax/ETS representation. Review domestic-versus-border accounting, membership and price trajectories; do not enable alongside another electricity option. |
| `Option_3` (`main.py:82`) | `False` | Electricity national ETS representation with the applicable EU-price/border relationship. It is a distinct scenario branch, not an automatic calibration to current law. |
| `Option_4` (`main.py:83`) | `False` | Mixed electricity national/border carbon-tax branch. Inspect the national-cost auxiliary and equations before use: the supplied structural notes flag an auxiliary without its own nonzero defining equation. Do not present this as an independently validated policy preset. |
| `include_secc_links` (`main.py:84`) | `False` | Include eligible secondary electricity transfer routes through intermediate zones. Requires complete secondary route mappings and compatible capacities/losses. |
| `model_simple_industry` (`main.py:90`) | `False` | Enable the separate fixed-recipe product-industry module. Its configure step disables overlapping legacy industry/transport, e-fuels, H2 and capture blocks and changes active example systems. It is not the pooled flex-tech worksheet. |
| `industry_cbam_active` (`main.py:91`) | `False` | Apply industrial product CBAM in simple-industry mode, using supplier origin, final destination and embedded footprint. It is separate from electricity Options 1–4. |
| `industry_carbon_pricing_active` (`main.py:92`) | `False` | Apply the simple-industry domestic carbon-price policy. Independent of industrial CBAM; requires the product module and complete plant/year policy rows. |
| `industry_external_imports_active` (`main.py:93`) | `False` | Allow eligible additional outside product suppliers in simple-industry mode. Their annual/hourly budgets remain binding. Europe background supply retains its restricted Europe-market treatment. |
| `industry_external_exports_active` (`main.py:94`) | `False` | Allow optional non-EU product sales in simple-industry mode. Mandatory domestic/Europe demand is not disabled by turning this off. |
| `steel_flexible_operation` (`main.py:95`) | `True` | Permit hourly operation of product plants marked flexible. False uses the applicable within-day constant-operation formulation, not mandatory full-load production. |
| `simple_industry_dat` (`main.py:96`) | `'./data/simple_industry.xlsx'` | Separate product-industry workbook with plants, recipes, markets, suppliers, prices, carbon policy and baseline load removals. |
| `model_transport_and_industry` (`main.py:99`) | `True` | Enable legacy transport/industry data, equipment and associated carrier blocks. E-fuel recipes and industry CAPEX have additional dependencies; turning this off is not a supported way to retain the same integrated e-fuel case. |
| `industry_single_sector` (`main.py:100`) | `False` | Legacy single-sector branch. Keep False for the documented e-fuel, category and complex-industry cases. Pooled Industry_data rows are a separate mechanism. |
| `model_industry_categories` (`main.py:101`) | `True` | Use temperature/service categories for detailed legacy industry and select the category technology/profile layout. Mutually exclusive with complex industry. |
| `industry_category_electricity_case` (`main.py:102`) | `'conservative'` | Choose conservative or technical_2050. In the e-fuel category case, technical_2050 selects the nested technology workbook; it is an applicability sensitivity, not a target year selector. |
| `industry_complex_electricity_case` (`main.py:103`) | `'conservative'` | Choose conservative or technical_2050 for the complex companion process workbook. Selects the corresponding process electricity-assumption file. |
| `industry_storage` (`main.py:104`) | `True` | Enable category-specific industrial thermal storage. Requires transport/industry, categories and multi-sector operation; turn it off for regular or complex recipes. |
| `industry_fuel_share_ramp_active` (`main.py:106`) | `True` | Enable general industrial transition envelopes in planning. They constrain annual adoption; hourly dispatch can still respond to prices and availability. |
| `industry_fuel_share_s_curve_active` (`main.py:107`) | `True` | Permit the configured endogenous S-curve mode when general ramps are active. False forces the applicable flat-ramp interpretation; the independent annual electric-share control can remain active. |
| `industry_electric_share_yoy_limit_active` (`main.py:108`) | `True` | Apply the combined direct-electric plus industrial-HP delivered-service share policy. This is a useful-service share, not an electricity-input fraction. |
| `model_complex_industry` (`main.py:116`) | `False` | Select process-based replacement for configured industrial sectors. Categories must be False and legacy multi-sector industry must remain enabled. Non-metallic minerals is the author's tested scope; other sectors are not equally evidenced. |
| `model_complex_non_metallic_minerals` (`main.py:118`) | `False` | Backward-compatible alias normalized together with model_complex_industry. Set both consistently when switching recipes so an old True alias cannot reactivate complex mode. |
| `model_complex_industry` (`main.py:119`) | `bool(model_complex_industry or model_complex_non_metallic_minerals)` | Select process-based replacement for configured industrial sectors. Categories must be False and legacy multi-sector industry must remain enabled. Non-metallic minerals is the author's tested scope; other sectors are not equally evidenced. |
| `model_complex_non_metallic_minerals` (`main.py:120`) | `model_complex_industry` | Backward-compatible alias normalized together with model_complex_industry. Set both consistently when switching recipes so an old True alias cannot reactivate complex mode. |
| `complex_industry_dat_efuel` (`main.py:127`) | `'./data/industry_complex_efuel.xlsx'` | Base companion process workbook for complex industry with e-fuels. The electricity-case selector can choose its technical_2050 variant. |
| `complex_industry_dat_no_efuel` (`main.py:128`) | `'./data/industry_complex.xlsx'` | Base companion process workbook for complex industry without e-fuels. It must match the no-e-fuel technology and carrier representation. |
| `two_stage_auto_mode` (`main.py:132`) | `False` | Run representative capacity planning followed by fixed-capacity rolling dispatch. The controller sets internal stage flags; supports sequential or joint capacity planning through Myopic. |
| `lightweight_representative_weeks_mode` (`main.py:136`) | `False` | Run the automatic controller's representative capacity stage only and skip rolling dispatch. It enables automatic mode and is a screening workflow, not an hourly feasibility certificate. |
| `two_stage_skip_stage1_shadow_exports` (`main.py:137`) | `True` | Skip the expensive stage-1 shadow-price export path in automatic mode. Ordinary investment/history outputs still need to be retained. |
| `two_stage_resume_skip_completed_chunks` (`main.py:138`) | `True` | Skip chunks whose required stage-2 completion outputs are found. This is a resume convenience, not proof that changed inputs are compatible with old results. |
| `two_stage_resume_reuse_stage1_bundle` (`main.py:139`) | `False` | Allow reuse of an existing stage-1 capacity bundle where its checks permit. Keep False after structural changes unless bundle identity and chronology are established. |
| `myopic_resume_from_results` (`main.py:142`) | `True` | Resume ordinary myopic planning after the contiguous accepted completed prefix. False starts at the base year; a new scenario is safer than overwriting a prior experiment. |
| `validate_completed_heating_policy_history` (`main.py:143`) | `False` | Request validation of completed heating histories against current rules. False does not certify old policies; it lets existing accepted years remain while unsolved years use current rules. |
| `two_stage_timing_logs` (`main.py:144`) | `True` | Emit timing information for the automatic stage sequence. It changes diagnostics rather than the physical feasible set. |
| `representative_capacity_mode` (`main.py:145`) | `False` | Internal/manual capacity-planning time-sampling selection. Automatic mode controls it itself. The legacy week-named parameters currently describe four 24-hour blocks. |
| `fixed_capacity_mode` (`main.py:146`) | `False` | Freeze capacity from the dispatch bundle in the dedicated rolling path. Without rolling_dispatch_mode, main normalizes it back to False. |
| `dispatch_stage_data_path` (`main.py:147`) | `'./results/' + scen + '/stage2_dispatch_bundle.pkl'` | Path to the stage-2 pickle capacity bundle. Use a trusted bundle from the same model/data conventions; it is not an Excel input file. |
| `export_stage2_dispatch_bundle` (`main.py:148`) | `False` | Export a capacity/state/metadata bundle after planning for later fixed dispatch. Automatic mode sets this during stage 1. |
| `rolling_dispatch_mode` (`main.py:149`) | `False` | Select rolling-operation behavior. The standalone runner requires fixed_capacity_mode=True; True alone does not select that execution branch. |
| `rolling_write_solution_quality` (`main.py:150`) | `False` | Write additional rolling solution-quality artifacts. Their presence is diagnostic; inspect whether the solve was provisional or warnings were allowed. |
| `rolling_write_window_files` (`main.py:151`) | `True` | Save individual rolling-window outputs/checkpoints. Needed for an auditable interruption/resume workflow. |
| `rolling_keep_results_in_memory` (`main.py:152`) | `False` | Retain rolling results in memory instead of relying exclusively on streamed/window files. Consider RAM use for many zones, carriers and hours. |
| `data_read_cache_enabled` (`main.py:153`) | `True` | Cache repeated CSV/Excel reads inside a run using path, modification time, size and reader arguments. This is separate from internet/weather download caching. |
| `data_read_cache_copy_deep` (`main.py:154`) | `True` | Return deep copies of cached frames to prevent later mutations from contaminating reused inputs. False changes memory/copy behavior and requires care with shared dataframes. |
| `transport_investment_limits_active` (`main.py:155`) | `False` | Activate the applicable extra transport investment-limit policy. Vehicle service shares, stock turnover and electrification targets are independent restrictions. |
| `transport_pathway_corrections_active` (`main.py:156`) | `True` | Apply fuel compatibility, paid physical conversions and supported drop-in fuel rules. Turning this off is not a calibrated unrestricted-conversion scenario. |
| `transport_passenger_car_zero_fossil_2050_sensitivity` (`main.py:157`) | `True` | Apply the named zero-fossil passenger-car sensitivity. This is not automatically zero fossil use in every transport sector. |
| `transport_allow_unconstrained_paid_upgrades_for_test` (`main.py:160`) | `False` | Test-only bypass for persisted paid-upgrade rows when pathway constraints are disabled. Do not use it for a reported policy case without establishing the missing stock/fuel constraints. |
| `transport_no_base_year_vehicle_investment` (`main.py:161`) | `False` | Prevent base-year fleet additions in the applicable ordinary case. E-fuel mode overrides this to False to allow its nonzero initial electrification floors. |
| `transport_max_share_limits_active` (`main.py:164`) | `True` | Enforce annual service ceilings from transport_all.max_share. A service-share ceiling is different from a vehicle-stock share. |
| `transport_ice_hybrid_stock_share_non_increasing_active` (`main.py:169`) | `False` | Add per-family ICE/hybrid stock-share nonincrease. The delivered case leaves this off because aggregate electrification/history constraints already restrict transition and tiny redundant anchors can harm conditioning. |
| `transport_electrification_limits_active` (`main.py:170`) | `True` | Apply selected electrification target paths. Requires the applicable sector/technology mapping and workbook targets. |
| `transport_rail_electrification_link_active` (`main.py:171`) | `False` | Apply the optional linkage between rail electrification representations. Independent of the direct-electric share ceiling and battery-rail specifications. |
| `transport_rail_direct_electric_share_limit_active` (`main.py:172`) | `True` | Cap direct-electric service for passenger and freight rail under the configured maximum share. It does not impose that share as a minimum. |
| `rolling_auto_carbon_budget_slack` (`main.py:173`) | `True` | Allow the configured penalized automatic rolling carbon-budget recovery. Nonzero slack means the strict carbon allocation was relaxed and must be reported. |
| `rolling_terminal_fuel_soc` (`main.py:174`) | `True` | Apply terminal/end-of-horizon fuel-inventory guidance or targets. This refers to end conditions, not only physical maritime terminals. |
| `rolling_terminal_fuel_soc_hard_balance` (`main.py:175`) | `False` | Use hard end-inventory constraints in the applicable rolling branch. False permits the configured soft treatment; check actual slack use. |
| `rolling_terminal_fuel_soc_link_sequential_years` (`main.py:176`) | `True` | Carry/coordinate terminal fuel-inventory targets across sequential years in the rolling workflow. Distinguish this from independent cyclic annual storage. |
| `rolling_terminal_fuel_soc_ramp_targets` (`main.py:177`) | `True` | Ramp toward terminal inventory targets over the configured lead interval. Controls guidance timing rather than physical storage capacity. |
| `rolling_resume_from_window_files` (`main.py:178`) | `False` | Reuse compatible solved rolling windows after interruption. Requires saved files, consistent metadata and coherent incoming stocks/budgets. |
| `rolling_zero_stage1_fuel_soc0` (`main.py:179`) | `True` | Prevent representative planning storage capacity from receiving free initial fuel inventory. This is an energy-accounting boundary condition. |
| `rolling_fuel_soc_stage1_floor` (`main.py:180`) | `False` | Permit the applicable stage-1 SOC floor guidance in rolling operation. Leaving it off avoids lifting chronological carryover to an unearned representative-week stock. |
| `stage2_quantity_guidance_active` (`main.py:181`) | `True` | Guide stage-2 annual/rolling quantities toward stage-1 results with configured tolerance and penalties. Guidance is not identical to an unconstrained chronological reoptimization. |
| `oil_refinery_product_generation_decline_active` (`main.py:182`) | `False` | Apply the extra refinery-product output-decline policy. Separate from product reserves, carbon limits and outside export permission. |
| `transport_ice_hybrid_fossil_share_decline_active` (`main.py:183`) | `False` | Apply the extra ICE/hybrid fossil-fuel share-decline policy in its configured scope. Compatible non-fossil fuel operation can differ from retiring the entire vehicle. |
| `transport_ice_fuel_share_ramp_active` (`main.py:184`) | `True` | Limit changes in ICE fuel composition using the entered change limit. This acts alongside conversion/blend compatibility. |
| `biomass_heating_nonincrease_active` (`main.py:185`) | `True` | Prevent applicable annual biomass-heating expansion. It is a scenario restriction, not a statement that biomass cannot serve existing demand. |
| `biomass_feedstock_limit_active` (`main.py:186`) | `True` | Apply the scoped biomass feedstock/resource limits. Do not equate carbon-neutral bookkeeping with unlimited sustainable supply. |
| `model_efuel` (`main.py:189`) | `True` | Enable the e-fuel carrier, conversion/feedstock, storage and trade representation and select e-fuel input families. Use the author's integrated recipe with explicit Oil/Gas supply and matching CO2 handling; production remains an economic decision. |
| `complex_industry_dat` (`main.py:196`) | `complex_industry_dat_efuel if model_efuel else complex_industry_dat_no_efuel` | Derived active companion process path after e-fuel and electricity-case selection. Do not edit this while leaving conflicting selectors unchanged. |
| `use_HVDC` (`main.py:206`) | `False` | Include eligible HVDC electricity links and converter requirements. HVDC is a network technology under transmission, not a separate energy sector or a switch for all cross-border trade. |
| `model_terminals` (`main.py:207`) | `False` | Enable terminals. With e-fuels, use the product-terminal/route tables; without e-fuels, use the standalone H2 terminal workbook and H2 balance. Activate individual assets and permitted flow directions in the applicable tables. |
| `h2_terminal_dat` (`main.py:208`) | `'./data/h2_terminals.xlsx'` | Standalone no-e-fuel H2 terminal workbook. Requires its terminals/routes schema, eligible active geography and H2_terminal cost years. |
| `model_H2_transmission` (`main.py:209`) | `False` | Enable standalone H2 pipelines/compressors when e-fuels are off. Main disables this flag with e-fuels because carrier transmission already handles H2 there. |
| `model_oil_and_gas_products_supply` (`main.py:210`) | `True` | Enable explicit Oil/Gas/refinery-product supply in the e-fuel representation. Main disables it without e-fuels. Enable it for the author's supplied integrated e-fuel recipe; review reserves, imports, storage and processing inputs. |
| `allow_fossil_fuel_exports` (`main.py:214`) | `True` | Allow eligible fossil refinery products to leave the modeled systems. False prevents that outside revenue channel while retaining applicable internal deliveries. |
| `exogeneous_NH3_demand` (`main.py:215`) | `False` | Add prescribed ammonia demand in e-fuel mode. Requires matching nh3_demand.csv and year/geography policy; endogenous ammonia feedstock demand is distinct. |
| `non_CO2_polutants` (`main.py:217`) | `False` | Request an explicitly incomplete legacy pollutant branch. It is not a complete non-CO2 or lifecycle environmental assessment. |
| `model_H2_supply_demand_balance` (`main.py:218`) | `True` | Request the standalone H2 supply-demand balance used by eligible non-e-fuel configurations. Other integrated flags can also build H2 balances; False does not necessarily erase every H2 term. |
| `model_CC` (`main.py:245`) | `True` | Enable eligible industrial capture/stripper/reboiler equipment and constraints. Capture capacity, active rows, energy inputs and a CO2 destination are still required. DAC in e-fuel mode is a distinct source. |
| `model_CO2_ammine_storeage` (`main.py:246`) | `True` | Enable capture-linked rich/lean-amine inventory flexibility. The historical misspelling is the actual configuration name. Capture off normalizes this option off. |
| `model_CO2_post_gen_storeage` (`main.py:247`) | `True` | Enable post-capture CO2 capacity/inventory handling where capture/e-fuels permit it. Geological storage additionally requires eligible active storage rows, capacity/build limits and allowed provenance. |
| `complex_industry_process_capture_required` (`main.py:248`) | `False` | Require the capturable share from eligible complex process sources to be captured. False lets budgets/economics decide; True does not remove uncapturable residual emissions. |
| `separate_industry_process_carbon_balances` (`main.py:249`) | `True` | Track process and other carbon separately and restrict geological injections to eligible captured process carbon. DAC/combustion/imported CO2 cannot acquire process provenance merely by entering a common buffer. |
| `DSM_day` (`main.py:259`) | `False` | Enable the daily basic-load shifting class. Combine with budget/rollout controls for the new constrained DSM formulation; does not automatically shift all sector-specific loads. |
| `DSM_week` (`main.py:260`) | `False` | Enable weekly basic-load shifting. With both classes and budgets enabled, the weekly pool is a subset of the daily-capable potential, not an additional unrestricted allowance. |
| `dsm_energy_budget_active` (`main.py:261`) | `False` | Apply moved-MWh budgets per daily/weekly block, counted once by half the absolute adjustment. These are separate from hourly power limits. |
| `dsm_availability_ramp_active` (`main.py:262`) | `False` | Scale DSM energy availability from the global base year toward its configured full-availability year. Turning it off removes that rollout restriction, not every DSM bound. |
| `shadow_prices` (`main.py:265`) | `False` | Request the applicable marginal/shadow-price export workflow. An LP solution without an accepted basis/dual treatment is not automatically an interpretable market-price forecast. |
| `solver_stage1_auto_retry_suboptimal` (`main.py:275`) | `False` | Allow the optional stronger generic retry for problematic stage-1 outcomes. Off in the delivered case; the separately enabled annual aggregation retry can still operate. |
| `solver_stage1_annual_pf_aggregation_retry` (`main.py:276`) | `True` | Retry eligible annual-myopic problems using the configured alternate aggregation setting. Despite its name it applies with or without partial foresight in this snapshot. |
| `solver_allow_provisional_solution` (`main.py:277`) | `True` | Permit acceptance of an eligible non-certified/provisional point within configured checks. True does not convert SUBOPTIMAL or TIME_LIMIT into OPTIMAL. |
| `solver_postoptimal_checks_warn_only` (`main.py:278`) | `True` | Let applicable postoptimal balance/bound/diagnostic checks warn instead of abort. For a stricter study set False and inspect the independent annual-CC gate and all remaining slack mechanisms. |
| `solver_enable_dual_simplex_fallback` (`main.py:279`) | `True` | Permit Method=1 recovery after the applicable failed/poor barrier outcome. Recovery can have its own focus, threads and unlimited time limit. |
| `solver_finalize_stalled_barrier_with_crossover` (`main.py:280`) | `False` | Attempt crossover finalization after an eligible barrier stall. It changes recovery behavior, not the physical model. |
| `solver_skip_dual_simplex_after_acceptable_stall` (`main.py:281`) | `False` | Skip the simplex recovery after an accepted stall in the applicable path. Leaving False preserves the fallback attempt. |
| `write_solver_diagnostics` (`main.py:282`) | `True` | Write available scale/quality diagnostic artifacts. This does not itself enforce strict acceptance. |
| `solver_diagnostics_on_problem_only` (`main.py:283`) | `True` | Restrict expensive diagnostics to problematic cases. False can substantially increase time and files on otherwise clean runs. |
| `solver_diagnostics_compute_kappa_exact` (`main.py:284`) | `False` | Opt into exact conditioning calculations. These can be very expensive and are not a prerequisite for an ordinary run. |
| `disable_transport_infrastructure` (`main.py:285`) | `False` | Inverted debug control: False retains fleet-linked EV charging/H2 refueling stock and cost constraints; True suppresses them and changes the study boundary. |
| `transport_infrastructure_dat` (`main.py:286`) | `'./data/transport_infrastructure.csv'` | Technology/cost/connection requirements for fleet-linked transport infrastructure. |
| `transport_infrastructure_existing_dat` (`main.py:287`) | `'./data/transport_infrastructure_existing.csv'` | Existing infrastructure stock by active geography. Keep it consistent with the fleet and technology input conventions. |
| `fuel_price_dat` (`main.py:291`) | `'./data/fuel_prices.csv'` | Primary fuel-price input; distinguish it from e-fuel policy carrier prices and electricity trade prices. |
| `inflows_dat` (`main.py:292`) | `'./data/hydro_inflows.csv'` | Hydro inflow profiles using exact reservoir/pumped-hydro IDs and the selected simple_curves schema. |
| `heat_demand_dat_indv` (`main.py:293`) | `'./data/heating_individual.csv'` | Individual heating service profiles. Annual growth is applied through the applicable policy paths. |
| `cool_demand_dat_indv` (`main.py:294`) | `'./data/cooling_individual.csv'` | Individual cooling profiles for the optional cooling representation. |
| `heat_demand_dat_DH` (`main.py:295`) | `'./data/heating_district.csv'` | District-heating service profiles; use the expected delivered/network-loss boundary. |
| `cool_demand_dat_DH` (`main.py:296`) | `'./data/cooling_district.csv'` | District cooling service profiles for the optional cooling block. |
| `ev_transpload_dat` (`main.py:297`) | `'./data/transport_profiles.csv'` | Transport activity, plug-in and V2G timing input. These are not interchangeable with annual service quantities. |
| `transploaddemand_dat` (`main.py:298`) | `'./data/transport_demand.csv'` | Annual transport-service demand by the native sector/geography keys. |
| `importcost_dat` (`main.py:299`) | `'./data/import_prices.csv'` | Electricity import-price input for the selected trade formulation. Fuel purchases have separate prices. |
| `heat_dem_industry_dat` (`main.py:300`) | `'./data/industry_heat.csv'` | Industry useful-service timing path. Later assignment selects category profiles when categories are enabled, otherwise industry_heat.csv. |
| `genco_dat` (`main.py:301`) | `'./data/generators.csv'` | Generator inventory with exact asset names, stock, location, efficiency, retirement, CHP and storage parameters. |
| `policy_dat` (`main.py:302`) | `'./data/policy_efuel.xlsx' if model_efuel else './data/policy.xlsx'` | Derived choice of policy_efuel.xlsx or policy.xlsx. The workbook horizon and trajectories must match the selected technology representation. |
| `demand_dat` (`main.py:307`) | `'./data/electricity_demand.csv'` | Basic electricity demand by period/System/Zone. Sector-accounting adjustments must avoid double counting. |
| `demand_industry_el` (`main.py:308`) | `'./data/industry_electricity.csv'` | Industry electricity baseline/accounting input used by the reader's sector decomposition. |
| `demand_heating_el` (`main.py:309`) | `'./data/heating_electricity.csv'` | Heating electricity baseline/accounting input used by the reader's sector decomposition. |
| `solar_thermal_aval` (`main.py:310`) | `'./data/solar_thermal_availability.csv'` | Solar-thermal availability input. It is separate from renewable generator/PV availability. |
| `flex_tech_name` (`main.py:315`) | `'flex_tech'` | Initial basename used to construct the technology workbook. Flags append e-fuel/category/complex suffixes before reading. |
| `flex_tech_directory` (`main.py:316`) | `'./data'` | Technology directory; the e-fuel category technical case changes it to the nested variants/technical_2050 folder. |
| `flex_tech_dat` (`main.py:329`) | `flex_tech_directory + '/' + flex_tech_name + '.xlsx'` | Derived final technology-workbook path. Check the reader's selected path rather than assuming the open Excel tab is active. |
| `heat_dem_industry_dat` (`main.py:331`) | `'./data/industry_category_profiles.csv' if model_industry_categories else './data/industry_heat.csv'` | Industry useful-service timing path. Later assignment selects category profiles when categories are enabled, otherwise industry_heat.csv. |
| `el_hourly_cost_dat` (`main.py:343`) | `'./data/electricity_prices.csv'` | Hourly electricity price input for applicable cost/trade operations; keep its period and geography schema consistent. |
| `_data_read_cache` (`main.py:370`) | `globals().setdefault('_data_read_cache', OrderedDict())` | Internal ordered cache created at runtime. Do not use it as a user-facing scenario parameter. |
| `_excel_file_cache` (`main.py:374`) | `globals().setdefault('_excel_file_cache', OrderedDict())` | Internal cached Excel reader handles. Do not change it to select another workbook. |
| `_data_read_cache_stats` (`main.py:378`) | `globals().setdefault('_data_read_cache_stats', {'hits': 0, 'misses': 0, 'read_time': 0.0})` | Internal hit/miss/read-time counters. They describe local file-reading performance, not API requests or model feasibility. |

## policy/model_policy.py

| Setting and source | Entered value / expression | Meaning and effect |
|---|---|---|
| `generation_annual_build_limit_multipliers` (`policy/model_policy.py:11`) | `{'HR_Wind': 2.0, 'HR_Wind_1': 2.0, 'HR_PV': 2.0, 'HR_PV_1': 2.0}` | Multiply scoped generator annual build allowances by exact unit ID. Values above one permit faster additions, not higher weather availability or free capacity. |
| `dh_chp_heat_max_annual_change` (`policy/model_policy.py:19`) | `0.25` | Relative annual CHP heat-change allowance; 0.25 denotes 25% under the implemented historical/interval rule. |
| `dh_chp_heat_reduction_limit_years` (`policy/model_policy.py:20`) | `10` | Number of years over which the extra CHP heat-reduction restriction is applied; separate from plant technical lifetime. |
| `dh_chp_heat_history_tolerance_mwh` (`policy/model_policy.py:21`) | `1.0` | MWh numerical allowance when comparing saved/current annual CHP heat. Do not use it as an intended heat-supply slack. |
| `individual_gas_heat_max_annual_change` (`policy/model_policy.py:22`) | `0.25` | Relative annual individual gas-boiler heat-change allowance. |
| `individual_gas_heat_reduction_limit_years` (`policy/model_policy.py:23`) | `5` | Duration of the extra individual-gas heat reduction restriction. |
| `fossil_heating_history_tolerance_mwh` (`policy/model_policy.py:24`) | `1.0` | MWh tolerance on historical fossil-heating comparisons, not a policy exemption. |
| `fossil_boiler_phaseout_years` (`policy/model_policy.py:25`) | `{'coal': 2030, 'gas': 2035, 'oil': 2035}` | Fuel-to-calendar-year boiler phaseout mapping. The delivered coal/gas/oil years are scenario choices; CHP is handled separately. |
| `dh_chp_base_year_heat_targets_twh` (`policy/model_policy.py:26`) | `{('TE-TO_Zagreb', 'HR1', 'HR'): 0.9, ('EL-TO_Zagreb', 'HR1', 'HR'): 0.55, ('TE_-TO_Osijek', 'HR1', 'HR'): 0.232}` | Exact CHP asset/zone/System base-year heat targets in TWh. Requires matching identifiers and calibration enabled. |
| `lulucf_removals_fixed_tco2e_per_year` (`policy/model_policy.py:32`) | `0.0` | Fixed annual removal allowance in tCO2-equivalent for the supported accounting path. Default zero; inspect its relationship to CSV/scoped removals before changing it. |
| `electric_heating_max_annual_decrease` (`policy/model_policy.py:33`) | `0.1` | Relative annual reduction allowance on the configured individual electric-heating service scope. |
| `electric_heating_max_annual_increase` (`policy/model_policy.py:34`) | `0.1` | Relative annual increase allowance on the configured individual electric-heating scope. |
| `electric_heating_week_hours` (`policy/model_policy.py:35`) | `24 * 7` | Block length for applicable electric-heating history comparisons; 168 hours is a week, not a representative sample count. |
| `electric_heating_individual_units` (`policy/model_policy.py:36`) | `('Air_to_water_HP', 'Ground_to_water_HP', 'Electric_heater', 'Water_to_water_HP')` | Exact technologies included in the individual electric-heating transition policy. |
| `industry_fuel_share_max_change_per_year` (`policy/model_policy.py:44`) | `0.1` | General fuel/service share-change allowance in the selected ramp formulation. Its interpretation differs from an equipment MW build limit. |
| `industry_fuel_share_ramp_mode` (`policy/model_policy.py:45`) | `'endogenous_s_curve'` | Select the supported flat/endogenous_s_curve transition interpretation, subject to main switches. This is a scenario adoption rule. |
| `industry_fuel_share_s_curve_initial_fraction` (`policy/model_policy.py:46`) | `0.02` | Seed fraction for adoption envelopes; not an additional physical service demand or measured adoption rate. |
| `industry_fuel_share_s_curve_growth_rate` (`policy/model_policy.py:47`) | `0.5` | Growth parameter in the adoption envelope. Increasing it relaxes the permitted transition speed under that formula. |
| `industry_fuel_share_s_curve_reference_years` (`policy/model_policy.py:51`) | `5` | Reference interval used so annual versus sparse decisions do not repeatedly restart seeds/tolerances. Must meet the helper's integer/grid compatibility checks. |
| `industry_fuel_share_s_curve_completion_year` (`policy/model_policy.py:55`) | `2045` | Finite transition deadline. Default 2045 completes the applicable fossil-combustion phaseout envelope; None retains the historical open-ended treatment. |
| `industry_fuel_share_s_curve_directions` (`policy/model_policy.py:59`) | `{'Gas': 'decrease', 'Coal': 'decrease', 'Lignite': 'decrease', 'Oil': 'decrease', 'fuel_oil': 'decrease', 'diesel': 'decrease', 'petrol': 'decrease', 'kerosene': 'decrease', 'LPG': 'decrease', 'Biomass': 'decrease', 'lignin': 'increase'}` | Explicit increase/decrease/auto directions by asset tuple, unit or fuel. Applicability ceilings remain separate; asset/unit overrides take precedence. |
| `industry_electric_share_max_annual_decrease` (`policy/model_policy.py:66`) | `0.1` | Relative maximum decrease of combined direct-electric/HP useful-service share; 10% of a 40% share gives 36%, not 30%. |
| `industry_electric_share_history_tolerance` (`policy/model_policy.py:67`) | `1e-06` | Small share-unit comparison allowance. It is not a percentage-point adoption budget. |
| `transport_decom_max_share` (`policy/model_policy.py:70`) | `None` | Optional additional transport decommissioning-share parameter. None leaves the implemented default treatment; do not infer unlimited vehicle replacement without the other turnover constraints. |
| `transport_turnover_years` (`policy/model_policy.py:71`) | `25` | Reference fleet turnover life used for the selected vehicle groups. |
| `transport_turnover_units` (`policy/model_policy.py:72`) | `('EV_car', 'FCEV_car', 'HYBRID_car', 'ICE_car', 'EV_truck', 'FCEV_truck', 'HYBRID_truck', 'ICE_truck', 'EV_MARINE_SHORT', 'FCEV_MARINE_SHORT', 'ICE_MARINE_SHORT')` | Exact vehicle/transport units included in the extra turnover policy. |
| `transport_turnover_ramp_start_year` (`policy/model_policy.py:85`) | `2025` | Start calendar year for the turnover-policy ramp. |
| `transport_turnover_ramp_full_year` (`policy/model_policy.py:86`) | `2030` | Calendar year when the turnover ramp reaches its full setting. |
| `transport_turnover_ramp_initial_share` (`policy/model_policy.py:87`) | `1.5` | Initial multiplier/share used by the turnover ramp; inspect its formula before interpreting a value above one. |
| `TRANSPORT_TURNOVER_MAX_SHARE` (`policy/model_policy.py:88`) | `0.3` | Upper turnover-policy share in the applicable implementation; separate from a vehicle's transport_all service ceiling. |
| `transport_existing_fleet_age_spread_years` (`policy/model_policy.py:89`) | `10` | Age-spread assumption for distributing retirement of inherited fleet stock. |
| `transport_forbidden_investment_units` (`policy/model_policy.py:90`) | `()` | Exact units prohibited from receiving new investment by the applicable transport policy. An empty tuple imposes no exclusions here. |
| `transport_inv_max_share_by_unit` (`policy/model_policy.py:91`) | `{'all': 0.2, 'EV_car': 0.42, 'FCEV_car': 0.25, 'ICE_AVIO_SHORT': 0.4, 'ICE_AVIO_LONG': 0.4, 'EL_RAIL': 0.4, 'EL_RAIL_CARGO': 0.4, 'ICE_MARINE_LONG': 0.4, 'ICE_MARINE_SHORT': 0.2}` | Unit-specific new-investment share ceilings, with the supported all fallback. Does not directly set final service shares. |
| `transport_inv_total_max_by_sector` (`policy/model_policy.py:102`) | `{}` | Absolute new-fleet investment caps by sector. An empty mapping supplies no extra sector-specific caps here. |
| `transport_inv_max_ramp_start_year` (`policy/model_policy.py:103`) | `2025` | Start year for investment-share ceiling rollout. |
| `transport_inv_max_ramp_full_year` (`policy/model_policy.py:104`) | `2028` | Year when investment-share ceilings reach their full configured values. |
| `transport_inv_max_ramp_initial_share` (`policy/model_policy.py:105`) | `0.5` | Initial rollout fraction for the applicable investment ceilings. |
| `transport_inv_declining_max_share_by_unit` (`policy/model_policy.py:106`) | `{}` | Optional units whose investment ceilings decline along the configured path. |
| `transport_inv_decline_start_year` (`policy/model_policy.py:107`) | `2025` | Start year of optional declining transport investment ceilings. |
| `transport_inv_decline_end_year` (`policy/model_policy.py:108`) | `2050` | Final year of optional declining investment ceilings. |
| `transport_inv_decline_final_share` (`policy/model_policy.py:109`) | `0.1` | Endpoint fraction for the configured declining investment ceiling, not an automatic zero-fossil rule. |
| `transport_stock_max_share_year` (`policy/model_policy.py:110`) | `2050` | Reference year for optional stock-share ceilings. |
| `transport_stock_max_share_by_unit` (`policy/model_policy.py:116`) | `{}` | Optional final/target stock-share caps by unit. Empty supplies no additional caps in this mapping. |
| `transport_electrification_target_sectors` (`policy/model_policy.py:117`) | `('Passenger_cars', 'commercial_vehicles', 'Motor_coaches_buses_and_trolley_buses', 'Rail_transport', 'Rail_metro_and_tram', 'Domestic_shipping', 'Domestic_aviation', 'International_aviation')` | Sectors to which the selected electrification target policy applies. International shipping is not automatically included because aviation is listed. |
| `transport_non_decreasing_stock_units` (`policy/model_policy.py:127`) | `('EL_RAIL', 'EL_RAIL_CARGO')` | Exact transport units with the extra nondecreasing-stock requirement. |
| `transport_rail_direct_electric_max_share` (`policy/model_policy.py:133`) | `0.9` | Maximum direct-electric rail service share in the separate passenger/freight cap; default 0.9 means a ceiling of 90%. |
| `transport_rail_battery_specs` (`policy/model_policy.py:136`) | `{'BAT_RAIL': {'average_stor': 700, 'average_ch_rate': 1000}, 'BAT_RAIL_CARGO': {'average_stor': 1400, 'average_ch_rate': 2000}}` | Battery-rail storage/charging specifications by unit, using native equipment units. Distinct from overhead/direct electric rail. |
| `stage2_carbon_budget_mode` (`policy/model_policy.py:142`) | `'cumulative_weighted'` | Rule for allocating carbon across rolling operation. The supplied cumulative_weighted mode uses cumulative budgets with configured weights, not independent unconstrained hourly caps. |
| `stage2_carbon_hour_weight` (`policy/model_policy.py:143`) | `0.25` | Contribution of uniform time to the applicable rolling carbon-allocation weights. |
| `stage2_carbon_heat_weight` (`policy/model_policy.py:144`) | `0.75` | Contribution of heat activity to rolling carbon-allocation weights. |
| `stage2_carbon_el_weight` (`policy/model_policy.py:145`) | `0.0` | Contribution of electricity activity to rolling carbon-allocation weights. Zero removes this weighting component, not electricity emissions. |
| `stage2_carbon_auto_slack_cost` (`policy/model_policy.py:146`) | `1000000.0` | Penalty for automatically introduced rolling carbon-budget slack. The native cost scale must be preserved when reporting it. |
| `stage2_carbon_slack_cost` (`policy/model_policy.py:147`) | `0.0` | Additional configured rolling carbon-slack cost. Zero here does not imply the auto-slack mechanism is cost-free. |
| `rolling_refinery_hourly_cap_multiplier` (`policy/model_policy.py:148`) | `1.0` | Scale the applicable stage-2 refinery hourly capacity allowance. It is a dispatch restriction, not a change in resource reserves. |
| `rolling_h2_balance_shortage_cost` (`policy/model_policy.py:149`) | `10000000.0` | Penalty on supported rolling H2 shortage variables. Nonzero shortage indicates relaxed service/balance requirements. |
| `rolling_industry_cap_shortage_cost` (`policy/model_policy.py:150`) | `10000000.0` | Penalty for supported rolling industry-capacity shortfalls. Report the slack rather than treating it as physical capacity. |
| `rolling_terminal_fuel_soc_tolerance` (`policy/model_policy.py:151`) | `0.0` | Allowed end-inventory target deviation in the applicable fuel-stock guidance rule. |
| `rolling_terminal_fuel_soc_slack_cost` (`policy/model_policy.py:152`) | `10000000.0` | Penalty for fuel terminal/end-stock slack. Inspect native stock and objective units before changing it. |
| `rolling_terminal_fuel_soc_lead_hours` (`policy/model_policy.py:153`) | `8760` | Lead time over which terminal fuel-stock targets begin influencing dispatch. |
| `rolling_terminal_fuel_soc_ramp_exponent` (`policy/model_policy.py:154`) | `1.0` | Shape exponent of the terminal-stock target ramp; does not change the underlying stock balance. |
| `storage_year_continuity_mode` (`policy/model_policy.py:155`) | `'cyclic'` | Select the supported annual storage boundary convention. The delivered cyclic setting should not be described as unrestricted interannual stock carryover. |
| `efuel_dh_heat_feedstock_aliases` (`policy/model_policy.py:156`) | `('heat', 'dh_heat', 'district_heat', 'district heating')` | Labels recognized as district-heat feedstock to e-fuel conversion. Such feedstock is served by the heat balance, not a free exogenous input. |
| `stage2_quantity_guidance_tolerance` (`policy/model_policy.py:157`) | `0.15` | Relative band around stage-1 quantity guidance in stage 2. |
| `stage2_quantity_guidance_abs_tolerance` (`policy/model_policy.py:158`) | `1e-06` | Absolute comparison allowance accompanying the relative guidance band. |
| `stage2_quantity_guidance_slack_cost` (`policy/model_policy.py:159`) | `1000000.0` | Penalty on allowed quantity-guidance deviations. Guidance compliance and physical feasibility are different checks. |
| `oil_refinery_product_generation_change_limit` (`policy/model_policy.py:160`) | `0.1` | Rate limit used when the extra refinery output-decline control is enabled. |
| `refinery_process_fuel_share` (`policy/model_policy.py:161`) | `0.08` | Refinery process-energy fraction, default 0.08. This is additional process demand, not product output efficiency by itself. |
| `refinery_process_fuel_co2_key` (`policy/model_policy.py:162`) | `'Oil'` | Fuel/emission-factor key used for refinery process combustion. |
| `transport_ice_hybrid_fossil_share_decline_scope` (`policy/model_policy.py:163`) | `'annual'` | Scope of the optional ICE/hybrid fossil-share decline rule; annual is the delivered setting. |
| `transport_ice_fuel_share_change_limit` (`policy/model_policy.py:165`) | `0.2` | Change allowance for ICE fuel composition when the corresponding main ramp is enabled. |
| `biomass_heating_fuel_aliases` (`policy/model_policy.py:166`) | `('biomass',)` | Fuel labels recognized by biomass-heating restrictions. |
| `h2_transmission_cost_aliases` (`policy/model_policy.py:169`) | `{'H2_pipe': 'H2CH'}` | Map standalone H2 pipeline technologies to supported cost keys. Does not add missing technical or geographic assets. |
| `transmission_transformer_units` (`policy/model_policy.py:170`) | `{'400kV_AC': 'transformer_AC', 'HVDC': 'transformer_HVDC'}` | Map electricity link technologies to converter/transformer cost and equipment keys, including HVDC. |
| `h2_pipeline_compressor_unit` (`policy/model_policy.py:174`) | `'comp_station'` | Technology name for standalone H2 compressor requirements. |
| `transmission_duplicate_policy` (`policy/model_policy.py:175`) | `'first'` | How duplicate link records are reconciled. Delivered first keeps the first applicable record; deterministic selection is not proof conflicting inputs are correct. |
| `active_zone_overrides` (`policy/model_policy.py:177`) | `None` | Optional explicit active-geography override. None retains normal workbook/configuration scoping; demands and links must still cover any new active zones. |
| `simple_industry_active_zones` (`policy/model_policy.py:180`) | `(('HR1', 'HR'), ('RS1', 'RS'), ('BA1', 'BA'))` | Active zone/System pairs when the separate product module is configured. The delivered HR1/RS1/BA1 example is different from an arbitrary NUTS3 case. |
| `simple_industry_grid_fallback_tco2_per_mwh` (`policy/model_policy.py:183`) | `0.6` | Fallback electricity intensity used by applicable product-industry reporting. Distinguish fallback reporting factors from physical modeled territorial generation emissions. |
| `electricity_cbam_future_intensity_tco2_per_mwh` (`policy/model_policy.py:186`) | `{}` | Optional exogenous future zone/year factors for electricity CBAM lookahead. Missing required realized history must not be silently replaced by zero. |
| `co2_storage_capex_input_unit` (`policy/model_policy.py:189`) | `'MEUR/t'` | Declared geological/buffer storage cost basis. MEUR/t is a stock-capacity cost, not MEUR per tonne/hour of injection. |
| `co2_amine_tank_capex_input_unit` (`policy/model_policy.py:190`) | `'MEUR/t'` | Declared amine inventory-capacity cost basis. Keep tonne-stock and hourly capture equipment costs separate. |
| `stat_grid_eff` (`policy/model_policy.py:191`) | `0.9` | Generic stationary electricity-storage/grid delivery-efficiency parameter in its reader/balance convention. Do not apply it twice to stock and delivered output. |
| `ceep_price` (`policy/model_policy.py:192`) | `1000` | Penalty for surplus electricity in the implemented objective. It can remain active when ceep_limit=False. |
| `noload_el_cost` (`policy/model_policy.py:195`) | `100000` | Penalty for unserved electricity. It is an entered scarcity parameter, not a measured national value of lost load. |
| `discount_rate` (`policy/model_policy.py:196`) | `0.05` | Economic discount rate for cross-year objective weighting. Different from capital financing and numerical objective scaling. |
| `discount_base_year` (`policy/model_policy.py:197`) | `2025` | Reference year for discount factors. Changing it changes the reported present-value basis. |
| `capital_finance_rate` (`policy/model_policy.py:198`) | `0.05` | Finance rate for annual capital-service payments over equipment life. |
| `fuel_storage_capex_aliases` (`policy/model_policy.py:204`) | `{'N2_stor': 'Gas_stor'}` | Explicit cost-key fallbacks for carrier stores; default N2_stor uses Gas_stor costs as an inherited assumption. |
| `fuel_storage_fixed_opex_fraction` (`policy/model_policy.py:205`) | `0.01` | Annual fixed-cost fraction for supported fuel storage equipment, relative to its configured capital basis. |
| `oil_gas_initial_soc_fraction` (`policy/model_policy.py:211`) | `{'Oil': 0.5, 'Gas': 0.5}` | Initial Oil/Gas inventory fractions under the supported supply boundary. Check zero-initial-stage-1 and rolling-stock rules before assuming the fraction is always applied. |
| `industry_electrification_full_applicability` (`policy/model_policy.py:215`) | `True` | Use the supported full-electrification applicability setting while retaining other process, transition, resource and capacity limits. It does not mandate 100% electrification. |
| `industry_heat_pumps_active` (`policy/model_policy.py:216`) | `True` | Enable eligible industrial HP technologies and their shared applicability/source budgets. Independent of building HP switches. |
| `industry_hp_profiles_dat` (`policy/model_policy.py:217`) | `'./data/industry_category_profiles.csv'` | Useful-service profile source used for industrial HP applicability/demand checks. |
| `complex_industry_sectors` (`policy/model_policy.py:223`) | `('Non_metallic_minerals',)` | Exact selected complex process branches. Only these replace corresponding legacy service demand; delivered default is Non_metallic_minerals. |
| `industry_external_steam_efficiency` (`policy/model_policy.py:226`) | `0.9` | Conversion assumption used when externally supplied industry steam/heat is attributed to input energy and emissions. Do not treat imported heat as automatically emission-free. |

## policy/runtime_policy.py

| Setting and source | Entered value / expression | Meaning and effect |
|---|---|---|
| `dsm_availability_full_year` (`policy/runtime_policy.py:5`) | `2030` | Calendar year at which the enabled linear DSM rollout reaches its target; based on the original global base year. |
| `dsm_daily_energy_fraction` (`policy/runtime_policy.py:6`) | `0.07` | Daily-capable moved-energy pool including the weekly subset. It is a block-energy ceiling, not an hourly MW share. |
| `dsm_weekly_energy_fraction` (`policy/runtime_policy.py:7`) | `0.015` | Weekly-capable subset of the daily pool when both classes are enabled. The two values must not be added as independent full potentials. |
| `dsm_shift_fraction` (`policy/runtime_policy.py:8`) | `0.1` | Shared hourly absolute adjustment power cap as a fraction of baseline electricity load. |
| `dsm_capacity_cost_eur_per_mw_year` (`policy/runtime_policy.py:9`) | `10000.0` | Annual enabling resource cost per MW of available DSM adjustment, in EUR/MW/year. |
| `dsm_shift_cost_eur_per_mwh` (`policy/runtime_policy.py:10`) | `5.0` | Real activation/discomfort cost per MWh moved, counted once, in EUR/MWh. |
| `partial_foresight_representative_days` (`policy/runtime_policy.py:15`) | `4` | Number of future-year sampled blocks in ordinary partial foresight. |
| `partial_foresight_day_hours` (`policy/runtime_policy.py:16`) | `24` | Hours per partial-foresight representative block; delivered 24. |
| `partial_foresight_representative_day_start_hours` (`policy/runtime_policy.py:17`) | `(337, 2521, 4705, 6889)` | Explicit first-hour positions of future-year blocks. Keep them valid, nonoverlapping and compatible with the configured block count/length. |
| `partial_foresight_lookahead_years` (`policy/runtime_policy.py:20`) | `10` | Calendar-year reach of each ordinary partial-foresight solve. None exposes the remaining horizon; 10 gives current year plus decision points no later than current+10. |
| `representative_full_year_hours` (`policy/runtime_policy.py:21`) | `8760` | Full-year hours used in representative annualization. The delivered 8760 convention is not automatically leap-year data support. |
| `two_stage_stage1_export_timing` (`policy/runtime_policy.py:22`) | `'before_stage2'` | When stage-1 outputs are written. before_stage2 preserves capacity/history exports; off/skip/none can deprive later myopic chunks of expected investment CSVs. |
| `representative_weeks_count` (`policy/runtime_policy.py:23`) | `4` | Number of representative capacity-stage blocks. Despite its historical name, interpret with representative_week_hours. |
| `representative_week_hours` (`policy/runtime_policy.py:25`) | `24` | Length of each representative capacity block. Delivered 24, so four blocks are four days, not four weeks. |
| `representative_week_start_hours` (`policy/runtime_policy.py:26`) | `partial_foresight_representative_day_start_hours` | Start positions of representative capacity-stage blocks. Delivered aliases the four seasonal-day starts. |
| `long_storage_guidance_default_band` (`policy/runtime_policy.py:27`) | `0.0` | Default allowed band for applicable long-duration storage guidance; zero requests the corresponding tight target band. |
| `rolling_dispatch_granularity` (`policy/runtime_policy.py:28`) | `'day'` | day sets 48-hour lookahead/24-hour realization; week sets 336/168; custom uses the explicit window/step/realized settings. |
| `rolling_window_size` (`policy/runtime_policy.py:30`) | `48` | Hours optimized per rolling solve when granularity does not overwrite it. |
| `rolling_step_size` (`policy/runtime_policy.py:31`) | `24` | Hours by which the rolling origin advances; coordinate with the realized horizon. |
| `rolling_realized_horizon` (`policy/runtime_policy.py:32`) | `24` | Hours committed/exported from each rolling solve. Later lookahead hours are guidance, not committed full-year results. |
| `rolling_forecast_avg_dev_percent` (`policy/runtime_policy.py:33`) | `5.0` | Magnitude of the configured rolling forecast-deviation assumption; zero changes that forecast experiment, not perfect foresight automatically. |
| `stage1_capacity_reserve_margin` (`policy/runtime_policy.py:34`) | `0.0` | Extra capacity margin in the applicable stage-1 sizing constraints; delivered zero. It is not a full reliability/N-1 reserve model. |
| `rolling_unmet_industry_heat_cost` (`policy/runtime_policy.py:35`) | `1000000000.0` | Penalty for supported rolling industrial-heat shortage. Review physical MWh and actual slack alongside its cost. |
| `rolling_unmet_dh_heat_cost` (`policy/runtime_policy.py:36`) | `1000000000.0` | Penalty for supported rolling district-heat shortage. |
| `rolling_unmet_indv_heat_cost` (`policy/runtime_policy.py:37`) | `1000000000.0` | Penalty for supported rolling individual-heat shortage. |
| `data_read_cache_max_entries` (`policy/runtime_policy.py:38`) | `256` | Maximum retained local read-cache entries; separate from API/download caching and quota estimates. |
| `solver_stage1_method` (`policy/runtime_policy.py:41`) | `2` | Primary Gurobi algorithm for capacity planning; delivered 2 (barrier). Method selection does not change physical constraints. |
| `rolling_solver_method` (`policy/runtime_policy.py:42`) | `1` | Primary rolling dispatch algorithm; delivered 1 (dual simplex). |
| `solver_stage1_numeric_focus` (`policy/runtime_policy.py:45`) | `1` | Numerical-care setting for the ordinary stage-1 solve. Larger values can increase numerical effort and runtime. |
| `solver_diagnostic_method` (`policy/runtime_policy.py:49`) | `1` | Algorithm used to diagnose ambiguous/failing outcomes; separate from the normal method. |
| `solver_diagnostic_time_limit_s` (`policy/runtime_policy.py:53`) | `0` | Diagnostic solve time limit in seconds. Nonpositive is treated as unlimited by the applicable wrapper. |
| `solver_diagnostic_numeric_focus` (`policy/runtime_policy.py:54`) | `3` | Numerical focus for the independent diagnostic solve. |
| `solver_diagnostic_aggregate` (`policy/runtime_policy.py:55`) | `0` | Presolve aggregation setting in the diagnostic solve. |
| `solver_objective_scale` (`policy/runtime_policy.py:56`) | `1000.0` | Positive multiplier applied to the assembled MEUR objective before optimization. The delivered value 1000 changes its numerical scale; restore native economic units when interpreting solver objectives and duals. |
| `solver_stage1_scale_flag` (`policy/runtime_policy.py:57`) | `2` | Gurobi scaling choice for the primary solve, in addition to explicit model row/column scaling. |
| `solver_stage1_aggregate` (`policy/runtime_policy.py:61`) | `0` | Primary presolve aggregation setting; delivered zero to preserve difficult transport equalities. |
| `solver_stage1_annual_pf_retry_aggregate` (`policy/runtime_policy.py:64`) | `1` | Alternate presolve aggregation in the eligible annual retry; does not mean all future operations are modeled hourly. |
| `annual_accounting_row_scale` (`policy/runtime_policy.py:65`) | `1000.0` | Explicit scaling divisor for applicable annual accounting rows. Physical audits must restore the original units. |
| `fuel_storage_balance_row_scale` (`policy/runtime_policy.py:66`) | `1000.0` | Explicit scaling divisor for carrier-stock balances; not a physical storage efficiency. |
| `fuel_storage_capacity_row_scale` (`policy/runtime_policy.py:67`) | `1000.0` | Explicit scaling divisor for carrier-store capacity rows; not a capacity multiplier. |
| `co2_storage_cost_row_scale` (`policy/runtime_policy.py:68`) | `1000.0` | Explicit scaling for CO2 storage cost equations; not a change in the cost assumption. |
| `solver_stage1_bar_homogeneous` (`policy/runtime_policy.py:69`) | `1` | Homogeneous barrier selection in the applicable ordinary stage-1 branch. |
| `solver_stage1_annual_s_curve_bar_homogeneous` (`policy/runtime_policy.py:72`) | `0` | Annual S-curve branch override of the ordinary homogeneous barrier setting. |
| `solver_stage1_homogeneous_recovery` (`policy/runtime_policy.py:73`) | `True` | Permit the independent homogeneous-barrier recovery path when applicable. |
| `solver_stage1_bar_conv_tol` (`policy/runtime_policy.py:74`) | `1e-08` | Barrier convergence tolerance for the ordinary applicable branch; dimensionless numerical criterion, not a physical MW tolerance. |
| `solver_stage1_annual_cc_bar_conv_tol` (`policy/runtime_policy.py:77`) | `1e-06` | Barrier tolerance override in eligible annual carbon-capture solves. |
| `solver_stage1_crossover` (`policy/runtime_policy.py:78`) | `0` | Gurobi crossover choice after barrier; zero disables normal crossover in the delivered case. |
| `solver_stage1_crossover_basis` (`policy/runtime_policy.py:79`) | `-1` | Crossover basis-construction setting used when that path is active. |
| `solver_stage1_bundle_feasibility_tol` (`policy/runtime_policy.py:80`) | `1e-09` | Primal feasibility tolerance used in the applicable dispatch-bundle solve/export path. |
| `solver_stage1_time_limit_s` (`policy/runtime_policy.py:81`) | `0` | Stage-1 time limit in seconds. Nonpositive is treated as unlimited by the wrapper. |
| `solver_stage1_auto_extend_attempts` (`policy/runtime_policy.py:82`) | `0` | Number of optional automatic time-limit extensions. Zero disables extensions, not the primary solve. |
| `solver_stage1_auto_extend_s` (`policy/runtime_policy.py:83`) | `3600` | Seconds added per enabled time-limit extension. |
| `solver_stage1_retry_numeric_focus` (`policy/runtime_policy.py:84`) | `3` | Numerical focus in the optional generic stage-1 retry. |
| `solver_stage1_retry_scale_flag` (`policy/runtime_policy.py:85`) | `1` | Gurobi scaling selection for that retry. |
| `solver_stage1_retry_bar_homogeneous` (`policy/runtime_policy.py:86`) | `1` | Homogeneous barrier setting for that retry. |
| `solver_provisional_max_constr_vio` (`policy/runtime_policy.py:87`) | `0.2` | Maximum solver-scaled constraint violation considered by the provisional-acceptance path. Physical-unit audits are independent. |
| `physical_energy_balance_abs_tolerance` (`policy/runtime_policy.py:92`) | `0.1` | Absolute physical-energy residual tolerance for audited families after undoing row/column scaling; delivered 0.1 in their MW/MWh basis. |
| `solver_provisional_max_bound_vio` (`policy/runtime_policy.py:93`) | `0.0001` | Maximum solver bound violation considered for provisional acceptance. |
| `solver_provisional_max_dual_vio` (`policy/runtime_policy.py:94`) | `0.0001` | Maximum dual violation considered for provisional acceptance. |
| `solver_provisional_max_dual_residual` (`policy/runtime_policy.py:95`) | `3.0` | Dual-residual acceptance threshold in the provisional path. |
| `solver_provisional_max_barrier_gap` (`policy/runtime_policy.py:96`) | `0.03` | Relative barrier-gap threshold used by provisional acceptance; it is not proof of certified optimality. |
| `solver_provisional_max_returned_objective_deviation` (`policy/runtime_policy.py:97`) | `0.02` | Allowed objective deviation in the relevant provisional returned-point comparison. |
| `solver_require_annual_cc_quality` (`policy/runtime_policy.py:100`) | `True` | Require the additional annual-capture numerical/physical quality checks even for a nominally optimal point. |
| `amine_mass_balance_abs_tolerance_t` (`policy/runtime_policy.py:101`) | `0.001` | Absolute amine-associated CO2 mass residual tolerance in physical tonnes; delivered 0.001. |
| `solver_stage1_bar_iter_limit` (`policy/runtime_policy.py:105`) | `1000` | Maximum primary barrier iterations before applicable recovery logic; not an hourly simulation count. |
| `solver_stage1_threads` (`policy/runtime_policy.py:107`) | `32` | Requested primary solver threads. More threads do not guarantee faster solves or more accurate inputs. |
| `solver_stage1_bar_order` (`policy/runtime_policy.py:108`) | `-1` | Barrier fill-reducing ordering setting; -1 is automatic in the supplied configuration. |
| `solver_auto_iis_max_rows` (`policy/runtime_policy.py:109`) | `2000000` | Matrix-size threshold for automatic IIS computation. An IIS is a conflict diagnosis, not a feasible solution. |
| `solver_bar_stall_time_s` (`policy/runtime_policy.py:110`) | `0` | Configured barrier-stall timeout control; inspect the callback's zero/off handling rather than treating zero as an immediate abort. |
| `solver_bar_stall_min_runtime_s` (`policy/runtime_policy.py:111`) | `2400` | Minimum runtime before the applicable stall logic considers intervention. |
| `solver_bar_stall_rel_improve` (`policy/runtime_policy.py:112`) | `0.05` | Relative improvement criterion in barrier-stall detection. |
| `solver_bar_stall_accept_gap` (`policy/runtime_policy.py:113`) | `0.002` | Gap threshold for considering an otherwise stalled barrier point acceptable for the relevant recovery path. |
| `solver_bar_stall_accept_compl` (`policy/runtime_policy.py:114`) | `1e-05` | Complementarity threshold in stall-point acceptance. |
| `solver_bar_stall_accept_primal_inf` (`policy/runtime_policy.py:115`) | `0.001` | Primal infeasibility threshold in stall-point acceptance. |
| `solver_bar_stall_accept_dual_inf` (`policy/runtime_policy.py:116`) | `0.0001` | Dual infeasibility threshold in stall-point acceptance. |
| `solver_stalled_barrier_finalize_time_s` (`policy/runtime_policy.py:117`) | `3600` | Time budget for an enabled crossover/finalization attempt after an eligible stall. |
| `solver_fallback_numeric_focus` (`policy/runtime_policy.py:118`) | `3` | Numerical focus in the simplex fallback. |
| `solver_fallback_time_limit_s` (`policy/runtime_policy.py:119`) | `0` | Fallback time budget; nonpositive is treated as unlimited in the applicable wrapper. |
| `solver_fallback_threads` (`policy/runtime_policy.py:120`) | `32` | Requested fallback thread count. |
| `electricity_price_zero_threshold_eur_per_mwh` (`policy/runtime_policy.py:123`) | `1.0` | Small electricity-price sanitation threshold in EUR/MWh. It can affect near-zero trade incentives and must be disclosed. |
| `fuel_trade_price_zero_threshold_eur_per_mwh` (`policy/runtime_policy.py:124`) | `1.0` | Small fuel-trade price sanitation threshold in EUR/MWh; does not authorize free feedstock generally. |
| `transport_stock_variable_scale_by_sector` (`policy/runtime_policy.py:126`) | `{'Passenger_cars': 1000.0, 'commercial_vehicles': 1000.0, 'Motor_coaches_buses_and_trolley_buses': 10.0, 'Domestic_shipping': 1000.0, 'Domestic_aviation': 100.0}` | Physical vehicles per scaled solver stock unit by sector. Export and audit quantities must be converted back to vehicles. |
| `transport_service_variable_scale` (`policy/runtime_policy.py:135`) | `1000.0` | Default service-variable scaling; changes numerical coefficients, not demand in physical units. |
| `transport_service_variable_scale_by_sector` (`policy/runtime_policy.py:136`) | `{'Passenger_cars': 1.0, 'commercial_vehicles': 10.0, 'Motor_coaches_buses_and_trolley_buses': 10.0, 'Domestic_aviation': 1.0}` | Sector overrides of service-variable scaling. |
| `numeric_abs_min` (`policy/runtime_policy.py:142`) | `1e-09` | Generic lower numerical sanitation bound used by supported readers/helpers. It is not a universal physical minimum flow. |
| `numeric_abs_max` (`policy/runtime_policy.py:143`) | `100000000.0` | Generic upper numerical sanitation bound; inspect the field-specific reader before treating it as a physical capacity limit. |
| `price_abs_max` (`policy/runtime_policy.py:144`) | `10000.0` | Upper absolute price sanitation bound in the applicable reader conventions. |
| `var_cost_abs_max` (`policy/runtime_policy.py:145`) | `100000.0` | Upper absolute variable-cost sanitation bound in applicable readers. |
| `transmission_km_abs_max` (`policy/runtime_policy.py:146`) | `100000.0` | Upper link-length sanitation bound in kilometres. |
| `fuel_storage_eff_min` (`policy/runtime_policy.py:147`) | `0.0001` | Minimum accepted/sanitized carrier storage efficiency. |
| `fuel_storage_eff_max` (`policy/runtime_policy.py:148`) | `1.0` | Maximum accepted/sanitized carrier storage efficiency; default one. |
| `cap_inv_limit_active_max` (`policy/runtime_policy.py:149`) | `500000.0` | Reader threshold used in deciding whether large investment limits are treated as active bounds. It is not a national resource estimate. |
| `transport_coeff_eps` (`policy/runtime_policy.py:150`) | `1e-05` | Small coefficient threshold used in transport equations/data handling. |
| `transport_co2_block_hours` (`policy/runtime_policy.py:151`) | `168` | Hours per transport-carbon aggregation block; affects numerical formulation, not annual vehicle demand. |
| `transport_historical_stock_zero_epsilon` (`policy/runtime_policy.py:152`) | `1e-06` | Small historical-stock cleanup threshold in the supported physical/scaled history path. |
| `heating_stock_zero_epsilon_mw` (`policy/runtime_policy.py:154`) | `1e-06` | MW threshold for negligible reconstructed heating stock. |
| `heating_history_zero_epsilon_mwh` (`policy/runtime_policy.py:155`) | `0.001` | MWh threshold for negligible reconstructed heating history. |
| `rolling_storage_state_roundoff_tolerance` (`policy/runtime_policy.py:158`) | `1e-06` | Tolerance for small negative stock roundoff during rolling carryover. Materially negative inventory is not authorized. |
| `rolling_h2_reserve_margin_mwh` (`policy/runtime_policy.py:160`) | `0.001` | Small MWh numerical headroom in the applicable H2 inventory reserve envelope. |
| `transport_physical_bound_tolerance` (`policy/runtime_policy.py:162`) | `1e-06` | Physical vehicle bound-audit tolerance; distinguish it from solver-scaled column tolerances. |
| `levelized_cost_min_annual_output_mwh` (`policy/runtime_policy.py:164`) | `1.0` | Minimum annual output for meaningful reported levelized EUR/MWh costs. Below-threshold ratios are not interpreted as reliable costs. |
| `transport_inherited_stock_zero_epsilon` (`policy/runtime_policy.py:167`) | `0.1` | Physical vehicle threshold for negligible inherited net/retrofit stock; delivered 0.1 vehicle. |
| `INDUSTRY_SHARE_ROUNDING_TOLERANCE` (`policy/runtime_policy.py:168`) | `0.01` | Share-rounding allowance used by industry input checks; not a new annual adoption budget. |
| `COMPLEX_INDUSTRY_DEMAND_AUDIT_REL_TOL` (`policy/runtime_policy.py:169`) | `0.01` | Relative complex useful-service demand reconciliation tolerance. |
| `COMPLEX_INDUSTRY_DEMAND_AUDIT_ABS_TOL` (`policy/runtime_policy.py:170`) | `0.001` | Absolute complex-demand reconciliation tolerance, used alongside the relative allowance in native service units. |
| `transport_fixed_stock_abs_tolerance` (`policy/runtime_policy.py:172`) | `0.1` | Absolute physical-vehicle tolerance around fixed stage-2 stock pins. |
| `transport_stock_relative_tolerance` (`policy/runtime_policy.py:175`) | `0.001` | Relative band/headroom around supported fixed stocks and technology/share caps; delivered 0.001 means 0.1%. |

## policy/transport_pathways.py

| Setting and source | Entered value / expression | Meaning and effect |
|---|---|---|
| `transport_marine_capex_multiplier` (`policy/transport_pathways.py:9`) | `{'methanol': 1.09, 'ammonia': 1.1}` | New marine methanol/ammonia equipment CAPEX multipliers relative to the supported baseline; not energy efficiencies. |
| `transport_marine_pilot_energy_share` (`policy/transport_pathways.py:10`) | `0.05` | Pilot-fuel energy fraction in supported marine conversion recipes. Include both pilot and main-fuel emissions/costs. |
| `transport_marine_retrofit_capex_fraction` (`policy/transport_pathways.py:13`) | `{'methanol': 0.16, 'ammonia': 0.24}` | Cost fractions for supported marine methanol/ammonia retrofits. Retrofitting consumes eligible incumbent stock. |
| `transport_marine_retrofit_remaining_years` (`policy/transport_pathways.py:15`) | `10` | Remaining service life assigned to supported marine retrofits. |
| `transport_physical_upgrade_capex_fraction` (`policy/transport_pathways.py:20`) | `{'bio_diesel': 0.03, 'ethanol': 0.05, 'methanol': 0.1}` | Baseline-CAPEX fractions for supported physical fuel upgrades by fuel family. |
| `transport_physical_upgrade_remaining_years_by_sector` (`policy/transport_pathways.py:23`) | `{'Passenger_cars': 5, 'commercial_vehicles': 5, 'Motor_coaches_buses_and_trolley_buses': 8, 'Rail_transport': 10, 'Rail_metro_and_tram': 10, 'Domestic_shipping': 10, 'international_shipping': 10}` | Remaining life of paid physical upgrades by transport sector. |
| `transport_physical_upgrade_capex_meur_per_vehicle` (`policy/transport_pathways.py:31`) | `{}` | Optional explicit per-vehicle upgrade CAPEX overrides. Empty uses the implemented fraction-based treatment. |
| `transport_upgraded_max_volume_share` (`policy/transport_pathways.py:32`) | `{'bio_diesel': 1.0, 'ethanol': 0.85, 'methanol': 1.0}` | Maximum supported upgraded-fuel blend volume share. Volume shares require the model's energy-conversion treatment before use in energy balances. |
| `transport_drop_in_fuels` (`policy/transport_pathways.py:34`) | `('e_diesel', 'e_petrol', 'e_kerosene', 'SAF')` | Fuel labels treated as compatible drop-in pathways in the supported equipment representation. This is a model compatibility assumption, not universal real-engine certification. |
| `transport_fame_max_volume_share` (`policy/transport_pathways.py:36`) | `0.07` | Unmodified-equipment FAME volume-blending ceiling, default 7%. |
| `transport_ethanol_max_volume_share` (`policy/transport_pathways.py:37`) | `0.1` | Unmodified-equipment ethanol volume-blending ceiling, default 10%. |
| `transport_methanol_max_volume_share` (`policy/transport_pathways.py:38`) | `0.03` | Unmodified-equipment methanol volume-blending ceiling, default 3%. |
| `transport_synthetic_jet_max_volume_share` (`policy/transport_pathways.py:41`) | `1.0` | Synthetic jet volume-blending ceiling in the supported scenario; default one. Treat certification and real fleet applicability separately. |

## Conditional input paths and table-level selections

The top-level assignment catalogue is supplemented by conditional paths such as `policy_dat_fuels` (e-fuel carrier price workbook), `demand_co2` (external CO2 demand in the non-e-fuel branch) and the selected ammonia-demand path. These are derived from module choices. They are not additional independent physical options.

Workbook controls are equally important: `setup` years/hours, `active_zones`, detailed-industry `include_in_model`/native inclusion fields, `CC_active`, technology/capacity/cost rows, terminal activation and allowed import/export directions, RPS/CO2 paths, transport targets, market mandatory flags and supplier/route eligibility. Exact capitalization and placement are file-specific; follow the reader and [data reference](DATA_REFERENCE.md).

Individual flags do not guarantee investment or dispatch. They make a technology, equation or policy available; the optimizer still chooses within costs, demand, build rates, resource limits and all other active constraints. Likewise, removing one policy can leave another policy binding.
