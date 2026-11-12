# Assumptions, limitations and evidence register

This register distinguishes observations from processing rules and scenario choices. It is part of both manuals. An internet source can contain analytically reconstructed data, and a referenced technology report does not validate a specific national parameter transferred from a template.

## 1. Classification

| Class | Definition | Example |
|---|---|---|
| Source observation | Quantity taken from the identified source version/cell/response | JRC annual useful/final energy; ENTSO-E hourly load |
| Derived quantity | Reproducible transformation with a stated equation and units | Useful/final efficiency; capacity-weighted profile |
| Spatial/temporal proxy | Allocation using related evidence rather than direct local measurement | Raster shares, inherited hourly shapes, flat fallback |
| Inherited template assumption | Value retained from the supplied model/cost workbook | Lifetime, annual build limit, some conversion/cost rows |
| Explicit scenario assumption | Deliberately selected future or technical policy | 2050 renewable target, investment multiplier, compatible replacement envelope |
| Unverified inherited provenance | A value/comment/reference whose original calibration cannot be established here | Unattributed technology defaults or missing source price-year details |

## 2. Parameter and method register

| ID | Item | Classification / implication | Required study disclosure |
|---|---|---|---|
| A01 | Country selection | Processing/output filter; bulk source geography can be wider | Selected codes, observed output System/zone, cache/source scope |
| A02 | Geographic allocation | Source NUTS3 data plus proxy/custom mapping | Boundary vintage, raster/facility evidence, equal/custom weights, cross-border assumptions |
| A03 | Power technical defaults | Mixed observed asset attributes and inherited technology defaults | Source snapshot, operating-status audit, donor parameters and remaining lives |
| A04 | Weather/renewable profiles | Reanalysis/proxy conversion, optional national scaling | Weather year/backend, technology assumptions, IRENA extract and scaling |
| A05 | Hydro profiles | Bundled runoff shapes plus scaling/matching assumptions | Runoff source/year, mapping distances, exclusions, natural/closed-loop distinction |
| A06 | Category industry | Older annual/source profile vintages plus inherited temperature allocation | Reference years and what has/has not been recalibrated for the selected country |
| A07 | Complex industry initial MW | Annual useful energy / 8760 | Average-utilization assumption; not observed nameplate plant census |
| A08 | Process product activity | Observed activity to source end; constant thereafter | Future growth/structural-change scenario, fallback observation years |
| A09 | Process electrical/HP applicability | Service screening and inherited equipment assumptions | Conservative/technical case, partial-furnace coefficient, COP/lifetime, cumulative/source budgets |
| A10 | Biomass/waste split | Exact single-class evidence or assumed common sector blend | Strict/blend choice, exact source evidence, future mixed-stream composition assumption |
| A11 | Material H2 convention | Non-energy gas/oil services represented as H2-fed demand | Chemical-route justification and possible process-emissions overlap |
| A12 | Croatian ammonia exception | Guarded inherited accounting interpretation | Exact country/branch/year/amount; independent evidence required elsewhere |
| A13 | Biomass/lignin substitution | Baseline biomass ceiling and bounded local lignin option | Share versus absolute annual MWh distinction; sustainability/resource scenario |
| A14 | Transport stock/profiles | Bundled national data, service coefficients and allocation proxies | Source vintage, fleet/service units, availability, fractional stock and OSM fallback |
| A15 | Paid conversions/blends | Technology-screening assumptions, including marine transfers | Engine approvals, pilot fuel, conversion cost/remaining life, actual fleet calibration |
| A16 | Heating allocation | Annual observations plus population/HDD/density proxies | DH boundary, fuels, weather/population vintage and baseline electricity convention |
| A17 | Costs/lifetimes/build limits | Inherited/reference or explicit scenario | Source workbook/cells, capacity basis, price year, finance/lifetime, total versus annual ceilings |
| A18 | External energy supply | Network/capacity/price/availability assumptions | Import origin, hourly limits, fuel-specific trade prices and active endpoints |
| A19 | Non-energy materials/CO2 | Separate recipe and carbon classifications | Energy/material units, capture/reuse/storage distinction and imported stream tagging |
| A20 | Future chronology | Full hourly or sampled/rolling mode | Period sets/weights, boundary conditions, what has actually been operationally validated |
| A21 | Renewable preset | Explicit energy-origin constraints, not a forecast or net-zero definition | Target scope, adapter version, imports and cleared stocks, process/lifecycle exclusions |
| A22 | Numerical acceptance | Solver tolerances and physical-unit quality gates | Status, primary/recovery, scaled/unscaled violations, slack and accepted history |

## 3. Current boundary conditions worth checking

The live model's category/e-fuel selection does not automatically activate the process compiler's all-sector selection. The process policy defaults to non-metallic minerals until changed. Conversely, a workbook retaining data for other countries does not activate them if the active-zone scope is correct.

Several local entered values are Croatian plant/technology calibrations. Changing `--countries` can replace historical demand/inventory without supplying a new transmission network, biomass potential, outside-trade target, CAPEX forecast or heating/transport policy for that country. Complete native coverage and country-specific scientific calibration are separate review tasks.

Ordinary/category and complex industry have distinct vintages and definitions. Their totals may differ even when both are internally correct. Do not force equality by adding a remainder that duplicates replaced services. The model's process-replacement audit preserves ordinary services separately.

The documented conservative whole-energy preset blocks unverified imported energy and clears generic uncertified boundary stocks. That is stricter than permitting certified renewable imports. It can make a target infeasible even when another origin-tracing formulation would allow it. Stating “100% renewable” without the trade/storage boundary definition is insufficient.

## 4. Evidence levels

| Level | Typical evidence | Does not establish |
|---|---|---|
| Dependencies/startup | Import checks, hidden interface construction | Source availability or correct national calibration |
| File structure/coverage | Validation JSON, unique keys, 8760 periods | A feasible optimization scenario |
| Source calibration | Cell reconciliation and baseline comparisons | Future technology realism or complete lifecycle emissions |
| Model reader | Actual native input reader completes | All constraints/objective built or a solve accepted |
| Small adapter/model test | Sample periods, bounded equation/LP tests | Full national chronology and all modes |
| Full solve | Exact input/version, solver logs and quality certificates | Empirical truth outside the modeled assumptions |
| Independent study validation | Historical reproduction and external plausibility/sensitivity checks | Universal validity for other countries/scenarios |

The preparation verification reports record passing bounded tests. The supplied critical-rebuild folder also contains synthetic fixtures, unpromoted candidate checks and user-reported remote results. These evidence classes must not be merged into a claim of an independently reproduced full transition in this documentation session.

## 5. Source and reference completeness

The bibliography contains verified public data/method references and retained identifiable references from the industry handoff and cost-source records. Exact endpoint/cell inventories support further audit. Some publisher pages block automated retrieval or large PDFs exceed the browser tool's limit; those cases are labelled rather than represented as fully re-read.

Inherited parameters without a verified primary source remain marked as inherited/unattributed. A catalogue URL, generic literature citation or software repository is not enough to reconstruct an individual numeric price, efficiency or lifetime. A publication-ready parameter table needs the exact edition, page/table/sheet/cell, physical units, price year and all conversion steps.

## 6. Recommended sensitivity and handoff record

Archive at least: command/configuration; selected countries/sectors/mapping; raw data/version/hashes; future years/demand; technology costs/lifetimes; annual/total investment limits; resource/biomass assumptions; industrial route and HP eligibility; fuel/engine compatibility; external prices/origins; storage initial/final policies; chronology/sampling; solver settings; accepted residuals/slack; resume history and exported results.

Useful sensitivity dimensions include high/low demand growth, renewable potential, grid/terminal expansion, weather years, profile calibration, industrial electrification scope, HP source limits, biomass ceilings, transport turnover/retrofit cost, renewable imports, financing and different chronological representations. Report which constraints bind and which inputs dominate the result.

## 7. Additional 12 November model assumptions

The new DSM energy pools, hourly power cap, rollout and enabling/activation costs are scenario assumptions. They are not independently measured values for all active countries. The supplied simple-industry plants, world/European offers, product demand and carbon footprints are illustrative and require calibration. Product trade can move emissions outside the modeled territory; falling territorial emissions alone do not establish falling embedded emissions or domestic technology replacement.

The external workbook `simple_industry.xlsx` and the flex-tech worksheet `simple_industry` have different meanings. Enabling the product model disables overlapping legacy blocks. Baseline electricity removal must be calibrated when a plant's load is already included in the basic profile.

This version enables separated process/other carbon balances. Its default solver settings also permit provisional outcomes and warning-only postoptimal checks. Output files alone are not an optimization-quality certificate. This manual is a static inspection with source/input hashes, not a new national solve or a certification of the preparation adapter against every 12 November extension.
