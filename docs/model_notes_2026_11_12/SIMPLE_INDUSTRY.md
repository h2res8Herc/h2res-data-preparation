# Simple industry and industrial CBAM

The module couples fixed industrial recipes to hourly electricity dispatch.
The supplied workbook contains illustrative RS BF–BOF and BA scrap-EAF cases.
These are scenario plants, not calibrated Smederevo or Zenica installations.

## Switches

In `main.py`:

```python
model_simple_industry = True
industry_cbam_active = True
industry_carbon_pricing_active = False
industry_external_imports_active = True
industry_external_exports_active = True
steel_flexible_operation = True
```

The switches are independent boolean controls within the simple-industry mode.
Industrial CBAM or domestic pricing requires `model_simple_industry=True`.
With the module disabled, the new workbook is not read and no new variables
or costs are added. The delivered main configuration leaves the feature off.

Enabling the module selects the electricity-and-simple-industry configuration:
legacy transport/industry, industry categories, e-fuel, hydrogen and industrial
capture/storage are disabled. Heating retains its existing switch. Active
zones come from `simple_industry_active_zones` in `policy/model_policy.py`,
initially HR1/HR, RS1/RS and BA1/BA. Electricity `Option_1`–`Option_4` remain
separate controls. Only one electricity CBAM option can be selected.

The scenario name receives a suffix identifying industry CBAM, domestic
pricing, flexible/fixed operation and lifetime capital accounting, separating
their saved histories from older capital assumptions.
Steel trade adds `_trade_v1` and the outside import/export switch settings.
This separates the new demand/trade formulation from earlier local-production
histories. Dispatch signatures also include suppliers, routes and trade flags.
Use a fresh base scenario name when changing workbook data, other policies
or the planning horizon.

When a generator's unit/year limit is present identically in the generic
workbook's other zone rows but its own zone row is absent, the reader reuses
that unambiguous value. Conflicting or absent unit/year values require an
explicit input row; no technology limits are guessed.

## Inputs

`simple_industry_dat` selects `data/simple_industry.xlsx`. All quantities use
the same product basis, initially a tonne of finished steel. Inputs include:

| Sheet | Meaning |
|---|---|
| `plants` | Product, route, zone/system, operating years, t/h, net MWh/t, MW connection, stock tonnes and capital inputs |
| `inputs_per_tonne` | Fixed GJ/t of each non-electric input and tCO2/GJ, including any reductant carbon assigned here |
| `fuel_prices` | EUR/GJ by fuel and year; 1 MWh fuel = 3.6 GJ |
| `economics` | Materials and variable maintenance EUR/t; annual fixed maintenance |
| `markets` | Product, domestic/EU/external market, domestic country, eligible plant IDs and profile |
| `market_years` | Annual tonnes, EUR/t sale price, EUR/t delivery cost and maximum hourly deliveries |
| `carbon_policy` | Independent industrial price/benchmark/allocation/credit paths by plant and year |
| `import_suppliers` | Outside origins, product, EU exemption, availability profile, eligible markets and background-supply flag |
| `import_years` | Annual/hourly supply ceilings, purchase prices, embedded footprints, EU benchmark/price path and foreign carbon-price credit |
| `trade_routes` | Optional supplier/market delivery costs, hourly ceilings and enabled flag |
| `profiles` | Named profiles covering all full-year hours; `flat` is built in |
| `baseline_load` | Explicit annual MWh to remove by zone/system/year, distributed with its profile |
| `metadata` | Calibration status, product boundaries and scenario provenance |

Recipes remain fixed; annual prices and policies can change. Fuel emissions
are GJ/t times tCO2/GJ, plus `process_co2_t_per_t`. Do not enter the same coke
or process carbon twice. Upstream precursor emissions entered separately
affect the CBAM footprint, not domestic physical scope-one emissions.

Every modeled plant/year must have economics and carbon-policy rows, and
every market/year and required fuel/year must have its own row. Named plant
availability profiles must remain between zero and one. Market profiles are
normalized demand shapes; their annual tonnages are preserved in sampled
planning years. Optional export delivery limits also follow their profile.

The example sets baseline removals to zero, so its plant loads are additions.
For historical calibration, explicitly remove the matching steel load already
inside `electricity_demand.csv`; excessive removals are rejected. Baseline
removal values are already year-specific and are not grown a second time.

The example assumes the same product can be sold by either plant into the
shared EU market. Use distinct product IDs and eligible plants if grades or
finished products are not substitutes.

Demand tonnes are in `market_years`. The updated workbook uses RS 800,000,
BA 300,000 and HR 1,000,000 t/year. Europe totals 135,000,000 t/year including
HR, so `EU_steel` contains the remaining 134,000,000 t/year. All four markets
are mandatory; the existing non-EU `other_exports` market remains optional.
`markets.mandatory` distinguishes a requirement from an optional sales ceiling.
Domestic demand must remain mandatory; use zero tonnes to disable a market.

A domestic market may name any active `System` and optionally an active `zone`
within that system. Eligible suppliers can be in other modeled countries or
zones. The existing `eligible_plants` column can restrict either plant or
outside-supplier IDs; a blank cell allows all compatible suppliers. Physical
production, electricity use and direct emissions always remain at the plant.

The outside offers are explicitly illustrative: `WORLD_STEEL` supplies at most
3 million t/year and 400 t/hour, priced at EUR 750/t with a 1.5 tCO2/t embedded
footprint. `EU_BACKGROUND` represents other European producers serving only
the rest-of-Europe market, with a 150 million t/year ceiling, 20,000 t/hour
ceiling and EUR 650/t purchase price. Its EU carbon costs are included in the
purchase price; its origin is EU and its steel is CBAM-exempt. These offers
require calibration before a policy study.

`industry_external_imports_active=False` disables additional outside suppliers,
including their deliveries to domestic or European markets. Europe's own
background production remains available only for the Europe market; it cannot
be used to bypass the import switch for HR/BA/RS. Regional trade among modeled
plants remains available. `industry_external_exports_active=False` disables
optional non-EU export markets, while required Europe demand remains in place.
If available supply cannot meet demand, the model is infeasible; demand is
never reduced automatically and there is no unlimited emergency import source.

Each outside supplier has one annual supply budget shared across destinations
and one hourly supply ceiling. Optional `trade_routes` rows can override a
market's delivery cost and add a supplier/market hourly ceiling, or disable
that pair. Without a route row, the market's delivery cost and common delivery
ceiling apply. Costs may be booked to an explicit active `accounting_zone` and
`accounting_System`; defaults use the destination system, or HR for the external
Europe account when HR is modeled.

## Production and markets

Production and sales use tonnes in each one-hour interval. Electricity is
fixed MWh/t times output, with the corresponding hourly MW grid limit.
Material balances track inventory by originating plant, preserving its
emission factor in all destination accounts.

Domestic and configured Europe deliveries are mandatory. Local plant output
is a decision: fixed nameplate capacity is an upper bound, not a production
requirement. Demand can be met by domestic production, other modeled countries
or enabled outside suppliers. Optional external sales are bounded by hourly
delivery limits and a shared annual market allowance.
External prices are exogenous: carbon costs change margins, break-even prices
and export allocation. There is no automatic green premium or endogenous
steel price equilibrium.

Plants with `flexible=Y` use hourly operation when the flexibility switch is
on. Other plants have a constant operating rate within each calendar day,
multiplied by their availability profile. Production may therefore change
between days. Optional ramp limits constrain adjacent modeled hours.
Opening/retirement years determine available capacity; steel construction
decisions are prescribed in this version. Power investment can anticipate
their future load.

Each plant's `capacity_tph` is fixed throughout its operating years. There is
no steel-capacity investment, expansion or gradual capacity depreciation.
Hourly production may vary within that fixed nameplate capacity.

`capital_paid_back` is an explicit True/False field in the `plants` sheet:

- RS BF–BOF: True. Historical/reference investment can remain in
  `capital_cost_eur`, but capital charges are zero in the objective and LCOS.
  Operating and maintenance costs still apply.
- BA EAF: False. The full `capital_cost_eur` is annualized across
  `lifetime_years`, starting in `capital_start_year`. There is no one-year
  lump-sum charge and no second charge for the original investment.

At zero financing interest, the annual amount is CAPEX divided by lifetime.
Otherwise the existing H2RES annuity-due convention uses
`capital_finance_rate`, with the first payment in the capital-start year.
Annual payments are constant within the lifetime and stop afterward;
physical capacity remains governed by the plant's fixed capacity and
operating dates. Capital payments follow their configured lifetime even
while a plant is idle; fixed operating maintenance applies in operating
years. Reports show capacity, paid-back status, capital basis,
lifetime and the annual capital payment.

Stocks start and finish each modeled year at zero. Outside deliveries go
directly to their destination and cannot create free local plant stock.
Representative blocks
close separately, preventing material creation in unsampled gaps. Rolling
windows carry accepted stock, previous output and consumed export allowances;
forecast sales never enter those ledgers. Stocks close at the calendar-year
end. Changing a workbook requires a fresh scenario/checkpoint history.
Accepted outside deliveries also consume the supplier's shared annual import
budget, including on checkpoint resume. Forecast deliveries do not consume it.
Dispatch bundles include an industry-input signature. Reusing a capacity
bundle with different recipes, markets or industrial carbon switches is rejected.

## Carbon prices and objective

Domestic payment per tonne is the domestic industrial carbon price multiplied
by direct emissions above its specified domestic allowance. This applies to
all production when industrial carbon pricing is enabled.

The planning CBAM proxy per exported EU tonne is:

```
eligible_credit = domestic_payment * credit_eligible_share
liable_emissions = max(0, embedded_emissions - free_factor * benchmark)
CBAM = max(0, EU_price * liable_emissions - eligible_credit)
```

CBAM starts at the plant's `cbam_start_year`, default 2026. It is zero before
that year and when the industrial CBAM switch is off. General electricity-use
emissions are reported separately from this steel CBAM input. Use verified
product/CN boundaries, applicable benchmarks, allocation factors and effective
foreign-price credits for policy studies. The example benchmark and price
values are deliberately illustrative and do not constitute a customs calculation.

EU importers are the legal CBAM payers. `exporter_cbam_share` specifies the
fraction economically borne by the producer through its sale price. Reports
retain both gross CBAM receipts and the producer's assumed burden.

The integrated objective adds industrial fuel/material/maintenance costs,
domestic carbon payments, producer CBAM and delivery costs, and subtracts
sales revenue. Electricity supply costs remain in the power-sector objective.
The plant electricity bill is calculated afterward using correctly scaled
zonal balance duals. Annual fixed maintenance and capital service are added
once, outside hourly cost annualization.

Domestic industrial payments are reported as national revenue. They remain
perceived carbon costs in the optimization; fiscal accounts do not cancel
their incentive. Revenue-funded renewable investment is not assumed automatically.

CBAM is determined by origin and destination, not by the label `domestic`:

| Delivery | Steel CBAM when enabled |
|---|---|
| BA/RS to HR | Yes: HR is an EU destination |
| BA/RS to the external Europe market | Yes |
| BA to RS, or RS to BA | No |
| EU-origin steel to HR or Europe | No |
| Non-EU outside steel to HR or Europe | Yes |

Set `markets.cbam_destination=True` for other EU destinations. Set an outside
supplier's origin and exemption explicitly. The source-specific benchmark,
phase-in and eligible carbon payment determine the charge once at the final
destination. Direct deliveries retain their original supplier ID; no
transshipment or origin relabeling is modeled. Outside purchase prices already
include foreign production and foreign carbon costs; `foreign_carbon_credit_eur_per_t`
is an explicit eligible credit independent of the modeled domestic-tax switch.
Outside footprints are reported separately and are not added to territorial
industrial emissions or electricity demand in HR/BA/RS.
For deliveries into a modeled EU domestic market such as HR, the complete
CBAM payment is a modeled cost even when the producer bears less than 100%.
The remainder is booked to the domestic importer; it cannot disappear by
setting `exporter_cbam_share=0`. External Europe exports retain the configured
producer share because their importer is outside the modeled country accounts.

With a zero national emissions cap, an emitting local plant may be idle while
imports meet demand, subject to the stated import limits. Its capacity remains
fixed and its configured annual capital/fixed costs still apply while idle.

## Foresight and sampling

Use `Myopic=True` and `partial_perfect_foresight=True` for a short moving
investment horizon. Set `partial_foresight_lookahead_years` in
`policy/runtime_policy.py`, already 10 by default. Future steel operating
dates, markets and industrial carbon policies enter all lookahead years.

Electricity CBAM now also has definitions in future lookahead years. Its
default exogenous intensity holds the latest available historical/realized
factor constant. Supply explicit `(zone, year)` entries in
`electricity_cbam_future_intensity_tco2_per_mwh` to use another future path.
No endogenous emissions/generation ratio is introduced into the LP.

Hourly flow quantities, costs and emissions use model weights and annualize
once. Stocks, coefficients and prices are never annualized. Rolling exports
sum committed hours directly, without expanding them into a second full year.

## Results

Each realized year's directory contains:

- `simple_industry_hourly.csv`: output, electricity, stocks, direct/indirect
  emissions, electricity prices and cost components.
- `simple_industry_fuels.csv`: GJ and MWh fuel by plant/hour.
- `simple_industry_sales.csv`: sales, revenue, delivery cost, CBAM and credits.
- `simple_industry_markets.csv`: producer and landed unit costs by destination.
- `simple_industry_summary.csv`: annual plant quantities, cost and margin.
- `simple_industry_fiscal.csv`: domestic carbon revenue and EU CBAM receipts.
- `simple_industry_imports.csv`: outside/background quantities, purchase costs
  and foreign embedded emissions, separated from local production.
- `simple_industry_demand.csv`: mandatory deliveries, local supply, regional
  imports, outside imports and background supply for each market/year.
- `simple_industry_cbam_borders.csv`: steel quantities, charges and credits by
  original source system and final destination system.

`simple_industry_levelized_cost.csv` in the scenario root discounts realized
annual production costs and tonnes, using the model's year and discount
weights. It includes annuity-due capital service over the reported years.
It is an analysis-period levelized cost, not a forecast of unmodeled lifetime
cash flows. `capital_paid_back=True` excludes historical investment from
capital charges while retaining its reference value in the input workbook.
Sales revenue is not subtracted from the levelized production-cost numerator.

Indirect emissions use realized domestic generation intensity, excluding
storage output. They are an attribution account and are not added again to
regional physical emissions. For hours without domestic generation, the
explicit policy fallback is used and labeled in the hourly output. These
factors are not import-adjusted consumption footprints or legal CBAM defaults.

## Verification

Run `python -B -m unittest scripts.test_simple_industry -v` for small physical
and economic regressions. Gurobi must have license access.
`scripts.test_simple_industry_trade` additionally checks regional supply,
mandatory Europe demand, import/export switches, HR border charges, bounded
outside offers, zero-cap import substitution and rolling import budgets.
`python -B scripts/validate_unified_model.py` checks input preservation, annual
steel trade with the actual workbook, and combined steel/DSM/electricity-CBAM
operation. These subsystem checks do not establish full-system feasibility.
See `reports/unified_integration/README.md` for the complete validation record.

`validation/simple_industry/run_integration_smoke.py` uses real H2RES inputs
and equations on four hours. It compares the disabled module with preserved
pre-change production files and exercises a sampled future steel/CBAM year.
It disables annual calibration targets and the carbon cap for that shortened
integration solve; it does not establish full-horizon regional feasibility.
