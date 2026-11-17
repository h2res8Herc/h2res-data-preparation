# Regional electricity profiles: neural networks and economic composition

**Assessment date:** 16 November 2026. **Status:** historical feasibility analysis written before implementation. The production `sector-weighted` option is now implemented; use the [current method, sources and equations](REGIONAL_ELECTRICITY_PROFILES.md) and [17 November release guide](PREPARATION_RELEASE_2026_11_17.md) for current behavior. The discussion below retains the original design assessment. No regional neural network was trained and no accuracy improvement is claimed. Read-only public-data probes and a synthetic conservation check were recorded locally in `validation/nuts3_electricity_feasibility/analysis_checks.json`; these working analysis files are not distributed.

## 1. Conclusion

Both extensions are technically feasible as optional demand-generation methods. The recommended design combines regional sector-specific electricity budgets and activity profiles with local weather/calendar response, then reconciles the result to national hourly demand and regional annual energy. A neural network can provide part of the shape model, but national aggregate load alone cannot identify the true hourly behavior of every region or sector.

The user-proposed Eurostat datasets, `nama_10r_3gva` and `nama_10r_3empers`, are appropriate core indicators of economic composition. They should be features and allocation evidence, rather than direct substitutes for electricity consumption. A 20% GVA share is not a 20% electricity share. Tourism requires an additional indicator because the broad NACE accounts do not isolate visitor-related electricity consumption.

The existing national-scaled method should remain available as a reproducible baseline. New curves should initially be described as **reconciled synthetic regional estimates**, with measured accuracy reported only where independent regional observations support it.

## 2. What exists now and what the paper describes

`power/demand/generate_electricity_demand_standalone.py` downloads national ENTSO-E Actual Total Load, reads packaged 2019 JRC EIGL regional electricity totals and normalizes them to shares. At the inspected line 216, `np.outer(load.values, weights.values)` constructs every regional curve as national hourly load multiplied by a fixed regional share. Custom zones subsequently aggregate those source regions.

For country c, region r and hour t:

```text
D[r,t] = w[r] * N[c,t]
sum_r w[r] = 1
```

Thus all positive-demand regions within a country currently have the same normalized hourly shape. Their totals differ. The weights describe modeled regional electricity demand, not merely population. They are historical spatial shares applied to the requested national load year; their unscaled annual GWh values are not asserted to match that year's national annual consumption.

The supplied `SEE.SDEWES2026.0044.docx`, Power demand paragraphs 30–32, describes a different temporal method: a national-load neural network using historical weather/calendar drivers, regional weather from eight population-weighted samples, and two simultaneous reconciliation conditions. Regional hourly sums must match national load, and regional annual shares must match the atlas-derived distribution. That ANN path is not present in the currently active demand generator.

The manuscript establishes the intended method but does not, in those paragraphs, specify a complete architecture, loss, training split, model weights and reproducible hyperparameter configuration. A new implementation could follow the method transparently; it should not be presented as reproducing an unavailable original trained artifact exactly.

## 3. Eurostat economy data: verified suitability and caveats

Live calls to the public Eurostat API verified the following for 2020 in HR050 (Grad Zagreb) and ITC4C (Milano):

| Dataset | Verified selection | Meaning |
|---|---|---|
| `nama_10r_3gva` | `unit=CP_MEUR` | Annual GVA at current prices, million euro, by NUTS3/NACE category |
| `nama_10r_3empers` | `unit=THS`, `wstatus=EMP` | Annual employed persons, thousands, by NUTS3/NACE category |

Each of the four filtered probes returned 15 nonmissing NACE entries. This verifies these examples, not complete coverage for all countries, regions or years. Preserve source flags, revisions and NUTS versions; missing/confidential data must not be interpreted as zero. Use a coherent currency/price-year basis when estimating electricity intensity from monetary GVA. Employment status EMP is distinct from SAL (employees) and SELF (self-employed); do not sum all three as disjoint employment groups.

The returned economic categories include TOTAL, A, B-E, C, F, G-J, G-I, J, K-N, K, L, M_N, O-U, O-Q and R-U. They contain overlapping aggregates. For example, C manufacturing is inside B-E industry; G-J overlaps G-I and J; K-N overlaps K/L/M_N; O-U overlaps O-Q/R-U. A valid nonoverlapping A10 partition in the verified examples is:

```text
A, B-E, F, G-I, J, K, L, M_N, O-Q, R-U
```

Its shares summed to one in both economic datasets for both sample regions. A coverage-aware importer must choose one partition, rather than normalize every returned entry together. TOTAL is the denominator, not another sector to add.

The GVA/employment distinction is substantive. In the checked 2020 Zagreb example, B-E industry represented approximately 12.53% of GVA and 14.16% of employment. In Milano, real estate L represented approximately 12.32% of GVA and 1.13% of employment. Neither observation measures electricity share. Monetary value, labor intensity, capital-intensive processes, imputed rents, establishments and consumption locations differ.

Eurostat's [GVA table](https://ec.europa.eu/eurostat/databrowser/view/nama_10r_3gva/default/table?lang=en), [employment table](https://ec.europa.eu/eurostat/databrowser/view/nama_10r_3empers/default/table?lang=en) and [regional accounts metadata](https://ec.europa.eu/eurostat/cache/metadata/en/reg_eco10_esms.htm) are the primary references. Source responses, request URLs and SHA-256 hashes are cached with the analysis probes.

## 4. Tourism is a separate modeling problem

G-I combines trade, transport, accommodation and food services. It cannot be labeled tourism. Even detailed accommodation/food-service employment is not equivalent to visitor demand: restaurants also serve residents, while tourism affects retail, transport and other services.

Use annual NUTS3 nights spent as tourism intensity and a monthly occupancy/visitor distribution as a seasonal shape driver. `tour_occ_nin3` is the relevant annual regional source; `tour_occ_nin2m` provides monthly breakdowns at its available regional levels. Availability must be checked for the exact country/year/geography rather than inferred from the table name.

The live 2023 monthly probes returned **zero nonmissing observations for HR035**, but **195 observations for HR03**, across accommodation/residence/month categories. This supports using a flagged NUTS2 seasonal fallback for that example. It does not prove that monthly NUTS3 data are unavailable everywhere or in every year. Probe optional finer data and national statistical-office sources before falling back. Do not label an inherited HR03 monthly distribution as observed Istrian monthly occupancy.

Tourism should modify a defined accommodation/service component or split it into nonoverlapping components. Adding a new tourism energy total on top of unchanged services would double count. Annual visitor nights do not, by themselves, identify hourly hotel, cooling, restaurant or water-pumping load. Day visitors, informal accommodation and winter tourism introduce further uncertainty.

References: [Eurostat tourism metadata](https://ec.europa.eu/eurostat/cache/metadata/en/tour_occ_esms.htm), [annual NUTS3 nights](https://ec.europa.eu/eurostat/databrowser/view/tour_occ_nin3/default/table?lang=en), [monthly regional nights](https://ec.europa.eu/eurostat/databrowser/view/tour_occ_nin2m/default/table?lang=en).

## 5. From economic composition to electricity composition

Prefer directly evidenced regional/sector electricity wherever available. Otherwise combine national sector electricity budgets with branch-specific regional proxies and calibrated electricity intensity. Do not choose an arbitrary 50/50 mixture of GVA and employment and call it measured energy demand.

For sector s and region r, a transparent first approximation is:

```text
P[r,s] = employment[r,s] * electricity_per_worker[country,s]
```

Alternatively use GVA and MWh per constant/coherent-price unit of sector GVA. Employment and GVA can both enter a fitted predictor where training evidence permits; neither should be assumed universally superior. Normalize the resulting proxy over regions to allocate the national sector budget, then jointly reconcile sector and regional energy totals. Construction and utilities need explicit mapping to the final-demand boundary.

The current JRC map service distinguishes electricity industry, transport, transformation input, non-energy, other and total, rather than providing all desired tourism/commercial/residential subsectors as separate layers. Inspect any downloadable underlying products before assuming the map's Other category is already disaggregated. National JRC/Eurostat sector energy can anchor broad sector budgets; facility evidence and profiles can refine industry within them. [JRC map layer catalogue](https://arcgis.jrc.ec.europa.eu/server/rest/services/eigl/EIGL_SERVICES_Energy_atlas__PUB/MapServer/layers).

Use the already prepared geolocated industrial branches as evidence for the industrial component. ETS emissions are not themselves an electricity-demand meter: a low-emission electric process can have high electrical demand. Where annual industrial electricity is inferred from national branch energy and facility activity, retain that provenance and uncertainty.

Residential demand needs population/households, buildings and appliance/heat/cooling evidence. Its electricity cannot be inferred by assigning the unemployed share of the economy to households. Agriculture needs more than the number of agricultural workers: irrigated land, crop and pumping seasons, greenhouses and weather can matter. Data centers, water treatment and large hospitals can require separately evidenced components if material.

## 6. Shape model: sector mixture plus local weather

Give each region a continuous mixture of sectors rather than a single label such as industrial or tourist. Select a normalized temporal response for each component:

```text
p[r,s,t] >= 0
sum_t p[r,s,t] * delta_t = 1
Q[r,t] = sum_s E[r,s] * p[r,s,t]
```

Here E is annual MWh and p is a normalized hourly response. With one-hour steps the timestep factor is numerically one. Weather, calendars and activity shape the profile; economic/energy evidence determines the annual mix. Suitable mechanisms include:

| Component | Shape drivers to represent, subject to calibration |
|---|---|
| Residential | Occupancy, morning/evening use, weekends, holidays, local heating/cooling sensitivity and daylight |
| Offices/public administration | Local working hours, weekdays/holidays, occupancy and cooling; hospitals may need their own continuous component |
| Retail/hospitality | Opening hours, weekend activity, refrigeration and visitor occupancy |
| Industrial branches | Continuous versus one/two/three-shift operation, weekends, shutdowns and branch-specific weather response |
| Tourism-related services | Monthly visitor/occupancy intensity, accommodation electricity, cooling or winter heating and daily activity |
| Agriculture | Irrigation/crop calendar, pumping, livestock/greenhouses and weather |
| Residual/unclassified | An explicit calibrated residual component with uncertainty, not silently called residential |

These are mechanisms to estimate, not universal fixed curves. Heavy industry is not always flat; tourist regions do not all peak in summer; commercial loads do not all disappear on weekends. National/country holidays and local clock time must be aligned with UTC model hours, DST and the model's 8760-hour/leap-day convention.

Population-weighted weather follows the paper for broad residential demand. Facility-, employment- or accommodation-weighted weather can be more appropriate for specific sectors. Start with a limited cached set of weather locations and aggregate locally; avoid repeating many identical Open-Meteo requests for each sector/model variant. Multi-year training adds acquisition cost beyond one weather-year generation. Reuse validated weather caches where variable coverage, coordinates, dates and provider semantics match.

## 7. Where neural networks help, and where they do not

An ANN can estimate nonlinear temperature response, calendar interactions and sector-specific weather sensitivity. A practical hybrid predicts sector profile adjustments or residual shape corrections conditioned on local weather and regional composition. Compare it against transparent schedule/temperature models and a simpler statistical learner before selecting it.

A national ANN transferred to regional weather follows the paper's broad direction. It does not automatically learn how Zagreb offices differ from an industrial county: within one country/year the national economic mix is constant, and national targets do not identify regional sector responses. Training against artificially allocated regional targets would mainly teach the old allocation assumption back to the network.

Even with perfect national fit and exact annual regional totals, many different regional hourly matrices satisfy those constraints. Aggregate agreement is therefore necessary but insufficient validation. National load can support weakly supervised fitting with explicit sector priors, smoothness, positivity and measured local anchors; resulting decompositions remain model-dependent. A more complex NN does not resolve this identifiability problem by itself.

For transfer learning, measured sector/region profiles in other countries can supply priors, but country differences in working hours, building stock, heating/cooling, tourism and industrial mix must be evaluated. Existing synthetic DemandRegio outputs are valuable methodology/benchmark material, not independent ground-truth measurements merely because they are detailed. Its reference implementation and GPLv3 license should be reviewed before any code reuse. [DemandRegio project](https://github.com/DemandRegioTeam/disaggregator).

The published national ANN study by Behm, Nolting and Praktiknjo demonstrates national weather-dependent load modeling, not universal NUTS3 sector accuracy. [Applied Energy paper, DOI 10.1016/j.apenergy.2020.115564](https://doi.org/10.1016/j.apenergy.2020.115564). Dynamic versus static regionalization is also discussed in [Sundblad et al., author preprint](https://arxiv.org/abs/2304.02951).

## 8. Preserve both national hourly load and regional annual shares

Let N[c,t] be observed national hourly MW and let w[r] be the selected regional annual share within the modeled country. Annual target energy must first be put on the same national boundary:

```text
E_target[r] = w[r] * sum_t N[c,t] * delta_t
sum_r D[r,t] = N[c,t]                          for every hour
sum_t D[r,t] * delta_t = E_target[r]            for every region
D[r,t] >= 0
```

Use constrained matrix balancing (for example iterative proportional fitting or a KL-divergence projection) to stay close to the positive prior Q while satisfying both margins. Alternating hourly and regional scaling converges under compatible positive support. Hourly-only scaling generally changes annual regional shares; annual-only scaling generally breaks national hourly agreement. A final one-pass normalization is not a sufficient substitute for two-margin reconciliation.

The prior and targets must have compatible support. Keep true zero-demand/offshore regions at zero and exclude their zero rows from the positive balancing problem. Exact structural zeros, fixed sector baselines, incompatible totals or additional hard hourly bounds can make a problem infeasible. Detect and explain that condition instead of filling unsupported cells or clipping negative residuals silently. Report convergence tolerance and how much reconciliation distorted the prior shapes.

A synthetic three-region, 8760-hour check in this analysis preserved distinct normalized shapes and both margins, with maximum errors below 1e-8 MW hourly and 1e-7 MWh annually. This establishes numerical feasibility of the conservation step only; it does not validate regional demand prediction.

Sector budgets add further margins. Reconcile annual region-by-sector E[r,s] against compatible regional and national sector totals before hourly profiling, or use a suitably constrained joint formulation. Do not independently impose incompatible raw EIGL energy, national final-sector electricity and ENTSO-E grid-load totals: they may have different years, losses, own-use and grid/autoproducer boundaries.

## 9. H2RES accounting and export compatibility

The final native schema can remain `period,Power,System,Zone`. The new method changes the hourly numbers and adds provenance/diagnostic sidecars; the optimization model does not need to know which statistical method produced a fixed load CSV. Custom model-zone curves should sum the already calculated NUTS3 curves.

Maintain a separate sector ledger for gross historical grid demand and for components that H2RES represents explicitly. Industry, electric heating, existing EVs and product-industry loads must not remain fully embedded in basic demand and then be added again through their model equations.

The current refactored exporter intentionally removes historical sector energy at the national annual level, then multiplies every regional gross curve by the same national residual fraction. This preserves each prepared shape, but it does not reconstruct a measured local residual sector split or exact historical gross hourly load after adding explicit sectors. A sector-aware upgrade should therefore have two explicit stages:

1. Generate and reconcile the requested gross regional demand with a documented sector ledger.
2. Export the appropriate basic/residual demand and explicit-sector baseline using each model version's accounting convention, with reconciliation and no duplicate sector energy.

Do not silently change that residual policy merely to add an NN selector. An optional physically decomposed residual export requires its own checks and comparison against the current behavior. Regenerate on method/feature changes; merely exporting old sector outputs cannot create new regional temporal behavior.

Relevant inspected source: `power/demand/generate_electricity_demand_standalone.py:157,216`; `generate_all_sector_inputs.py:507`; `refactored_input_export.py:68,485`.

## 10. Suggested user-facing options and implementation stages

**Implementation update, 16 November 2026:** the non-neural `sector-weighted` option is now implemented alongside the unchanged `national-scaled` default. See [the production method guide](REGIONAL_ELECTRICITY_PROFILES.md) for actual options, equations, source coverage and limits. The table and stages below are the earlier feasibility proposal; ANN options remain unimplemented.

Proposed selector names below are design suggestions; they are not implemented options:

| Method | Behavior | Appropriate initial status |
|---|---|---|
| National curve with JRC regional shares | Current fixed-share shape and reconciliation | Stable baseline/default |
| Weather/calendar ANN | Paper-aligned national-trained response transferred to regional conditions, with two-margin reconciliation | Experimental until independently checked |
| Economic-sector profiles | Sector budgets, activity calendars, local weather and tourism seasonality, with reconciliation | Recommended first extension to develop/validate |
| Economic-sector profiles with ANN | Same accounting plus learned nonlinear sector responses/corrections | Subsequent optional hybrid |

Stage 1: build source downloads/caches, NUTS/year mapping, the disjoint economic partition and a per-region feature/coverage report. Add tourism and sector-energy/facility evidence with explicit fallback levels.

Stage 2: implement transparent sector/weather profile construction and two-margin reconciliation, preserving the existing method. Compare shapes, peaks, weekends and seasonal shares before changing default behavior.

Stage 3: add training/inference with model version, feature scaler, training periods, seeds, hyperparameters and optional ML dependency metadata. Training should be separate from routine generation; portable model artifacts can support inference without retraining every installation.

Stage 4: compare against independent regional observations, then evaluate effects on H2RES peak demand, storage, transfer congestion and investment. Expose the method in GUI/CLI only with its actual coverage/support status and reproducibility metadata.

Core national ENTSO-E acquisition still needs the user's token unless a supported cache/source supplies it. The sampled public Eurostat APIs required no API token. Weather-provider/alternative data credentials remain provider-specific. An ANN does not remove upstream data/API requirements.

## 11. Validation requirements and limits

Retain year-blocked out-of-sample national tests before reconciliation, plus spatial or country holdouts where measured data exist. Do not randomly split adjacent hours and interpret leakage-prone fit as independent transfer accuracy. Historical 2020 is affected by exceptional pandemic/occupancy patterns; tourism and business calendars should use the chosen observation year rather than an unlabelled normal-year assumption.

After reconciliation, national RMSE is zero by construction and cannot be used as evidence of regional ANN accuracy. Evaluate independent regional peaks/timing, daily and annual load factors, monthly shares, weekday/weekend ratios, temperature response and hourly errors where observations permit. Flag source geography and aggregation mismatches. RTE publishes regional and metropolitan consumption indicators that can support aggregated validation; those are not automatically direct measurements for every NUTS3, and their estimation/consolidation status must be checked. [RTE regional data](https://www.rte-france.com/en/data-publications/eco2mix/regional-data), [download scope](https://www.rte-france.com/en/data-publications/eco2mix/download-indicators).

Include an ablation comparison: current fixed-share curves, weather/calendar only, economy only, economy plus tourism, and the hybrid NN. Test at least more than one weather/economic setting and quantify parameter/transfer uncertainty. Source-based annual shares, measured hourly truth and synthetic profile assumptions must have distinct provenance labels.

Before enabling broadly, check source availability per country/year, NUTS vintage crosswalks, parent/child sector double counting, tourism overlap, residential representation, electricity intensities, aggregate energy boundaries, valid UTC/calendar coverage, nonnegative values, structural zeros, both reconciliation margins, custom aggregation and both model export formats. The key development gap is validated shape inference and sector accounting, not the availability of the two broad Eurostat economy tables.
