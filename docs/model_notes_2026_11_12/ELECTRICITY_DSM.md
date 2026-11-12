# Basic electricity demand-side management

Implemented 10 November 2026. The old reference is
`D:\POSAO\za_DSM_stari\scripts\Build_model.py`, especially its daily/weekly
`demand_flex` equations. The restored version is in `scripts/electricity_dsm.py`.

## Select a run

DSM is off by default in this unified copy. To enable both nested classes and their rollout, use:

```python
DSM_day = True
DSM_week = True
dsm_energy_budget_active = True
dsm_availability_ramp_active = True
```

With both enabled, the 1.5% weekly-capable potential is a subset of the 7%
daily-capable potential: 5.5% balances daily and 1.5% balances weekly. Daily only
uses the full 7%; weekly only uses 1.5%; both false preserves fixed basic load.
Legacy hourly-only configurations remain available with
`dsm_energy_budget_active=False` and a single class.
Use a fresh scenario name to preserve an existing comparison. Resume checks
rebuild from the first year whose DSM metadata differs from the current budgets
or rollout; old capacity bundles and rolling checkpoints are incompatible.

Inputs in `policy/runtime_policy.py`:

| Input | Supplied value | Meaning |
| --- | ---: | --- |
| `dsm_daily_energy_fraction` | 0.07 | Total daily-capable moved-energy pool, including the weekly subset |
| `dsm_weekly_energy_fraction` | 0.015 | Weekly-capable subset of that pool |
| `dsm_availability_full_year` | 2030 | Year when the linear rollout reaches its target |
| `dsm_shift_fraction` | 0.10 | Shared hourly adjustment power cap, independent of energy quotas |
| `dsm_capacity_cost_eur_per_mw_year` | 10,000 | Annual enabling resource cost per MW of available adjustment |
| `dsm_shift_cost_eur_per_mwh` | 5 | Real activation/discomfort cost per MWh moved, counted once |

The energy shares are user-selected central scenario estimates from
*Flexibility of Base Electricity Demand in Croatia Literature Review.docx*,
10 November 2026. That review describes them as a synthesis, not measured Croatian
values. The hourly power cap and costs remain sensitivity assumptions. The same
defaults apply to active systems unless overridden by zone/system; the review
does not establish country-specific values outside Croatia.
Fractions and costs accept a scalar or a dictionary, with precedence
`(zone, System, year)`, then `year`, then `'default'`. The rollout target is one
calendar year. For example:

```python
dsm_daily_energy_fraction = {'default': 0.07, ('HR1', 'HR', 2030): 0.09}
dsm_capacity_cost_eur_per_mw_year = {2025: 12000, 2030: 10000, 'default': 8000}
```

The fraction must be between zero and one; costs must be finite and nonnegative.
Missing dictionary entries raise an error rather than silently enabling free DSM.

The rollout is `clip((year - base_year) / (2030 - base_year), 0, 1)` and multiplies
both energy pools. It uses the original global base year even in future myopic
chunks, fixed-capacity dispatch and restarts. The hourly power cap is a separate
sensitivity input; zero energy availability also forces zero dispatch in the base
year. Full-year planning chooses zero DSM capacity there.

| Year with current base 2025 | Daily-balanced pool | Weekly-balanced pool | Total |
| --- | ---: | ---: | ---: |
| 2025 | 0% | 0% | 0% |
| 2026 | 1.1% | 0.3% | 1.4% |
| 2027 | 2.2% | 0.6% | 2.8% |
| 2028 | 3.3% | 0.9% | 4.2% |
| 2029 | 4.4% | 1.2% | 5.6% |
| 2030 onward | 5.5% | 1.5% | 7% |

## Physical formulation

For each active zone, system and year, let `b[h]` be the original electricity
profile multiplied by that year's demand multiplier, and `x[c,h]` its signed DSM
adjustment in class `c`. The electricity balance uses `b[h] + sum_c x[c,h]` for basic consumption.
Other demands continue to enter through their existing sector equations. Where
the simple-industry mode explicitly removes historical industry electricity from
the base profile, DSM applies to the remaining basic demand.

The LP chooses one shared annual available power `K` and class-specific hourly
absolute adjustments `a[c,h]`. For each daily or weekly class block `B`:

```text
a[c,h] >= x[c,h]; a[c,h] >= -x[c,h]
sum_c a[c,h] <= min(K, dsm_shift_fraction * b[h])
E[c,h] = E[c,previous] + x[c,h]            (one physical hour per step)
E[c,end of B] = 0
0.5 * sum_h_in_B a[c,h] <= class_fraction[c,year] * sum_h_in_B b[h]
```

The half-absolute sum counts each MWh moved once. The class energy shares cap
MWh shifted; they are not hourly demand percentages. The combined shared power
limit includes the absolute activity in both classes, so opposite class actions
cannot hide capacity use or activation costs by cancelling in aggregate demand.
One signed power variable per class avoids independent simultaneous upward and
downward activations inside that class. No electricity is shed, created or transferred to another zone.
The formulation assumes lossless shifting; it does not change total service.

Daily blocks are hours 1–24, 25–48, etc. Weekly blocks are 1–168, 169–336, etc.,
anchored to model hour 1 rather than ISO calendar weeks. The final incomplete
block closes too: an 8760-hour year has a final 24-hour weekly remainder.
Advance consumption and deferred consumption are both possible. This is a
block-balancing model, not an appliance-level deadline or recovery-time model.
The energy percentages are upper bounds. A 10% symmetric hourly power cap can
bind first: it mathematically limits total moved energy to at most 5% of block
energy, even if a 7% total energy allowance exists. This is intentional separation
of constraints, not a requirement to exhaust the energy budget. Vary the hourly
cap in sensitivities before interpreting an unused allowance as uneconomic DSM.

## Temporal modes

| Model configuration | DSM handling |
| --- | --- |
| Annual full chronology, myopic or perfect foresight | Each day/week closes within each modelled year |
| Partial perfect foresight | Each year's own active hours are used; full and sampled years can coexist |
| Representative periods | Each contiguous sampled fragment of a day/week closes independently; no energy crosses missing hours |
| Two-stage planning and dispatch | Stage 1 chooses `K`; Stage 2 fixes it using the capacity bundle |
| Rolling daily/weekly/custom solves | Accepted energy balance passes into the next solve; forecast decisions are discarded |
| Interrupted rolling runs | Saved accepted DSM rows reconstruct the same balance, with configuration/capacity/baseline checks |

Representative weights enter costs, not physical state transitions. If weights
differ within one sampled fragment, an additional weighted conservation equation
also preserves its represented energy. Sampling four isolated days consequently
provides only within-day flexibility in Stage 1 even with weekly DSM. For a study
of weekly investment benefits, use complete representative weeks or full chronology.

Rolling windows may cross either type of balancing boundary and may be shorter
than a week. Each class carries its outstanding energy and the amount of its
block budget already used. Forecast decisions are discarded. The quota is based
on original unperturbed demand in the complete physical block, including its
accepted past, rather than being reset for every optimization window. It reserves
half the outstanding adjustment for repayment within that same quota.
Repayment guards also check both classes together against the shared remaining
hourly power and their respective deadlines. A new day/week resets only its own
balance/budget. The horizon's final incomplete block closes on its actual final hour.
These guards check energy budgets and hourly DSM limits; they do not prove that future
generation/network dispatch is feasible under all forecast errors.

Rolling DSM requires contiguous accepted hours:
`rolling_step_size == rolling_realized_horizon <= rolling_window_size`.
Daily, weekly, and custom windows satisfying this rule are supported.
Changed DSM settings require rebuilding the Stage 1 bundle. Incompatible saved
windows are recomputed from the first mismatch onward. No outstanding DSM energy
is carried across calendar years.

## Economic interpretation at the whole-system boundary

Treat DSM as a competing flexibility resource within the system-cost objective.
Include incremental control/metering/communications equipment, maintenance,
administration, and real wear or inconvenience. Electricity supply costs already
respond to the shifted profile through dispatch. Do not add avoided electricity
bills as another benefit. Payments between participants, suppliers and aggregators
inside the system boundary cancel in aggregate; payments crossing the chosen
boundary require separate treatment. This follows the total-resource/societal
perspective described by [Woolf et al. (2013), sections 3.3 and 5.2.6](https://www.ferc.gov/sites/default/files/2020-04/napdr-cost-effectiveness.pdf).

The implemented annual incremental DSM cost is:

```text
C_DSM = c_capacity * K + c_shift * 0.5 * sum_c,h(weight[h] * abs(x[c,h]))
```

With energy-neutral blocks, half the absolute adjustment counts the transferred
MWh once: moving 1 MWh out of one hour into another costs `c_shift`, not twice
that value. DIETER instead attaches variable coefficients to both upward and
downward activation. To reproduce equal DIETER per-leg coefficients, set this
model's per-MWh-moved price to twice that coefficient.
[DIETER objective documentation](https://diw-evu.gitlab.io/dieter_public/dieterpy/model/equations/eq_objective.html).

Supply an **annualized equipment cost plus annual real fixed OPEX** in
`c_capacity`. A capital-recovery factor can convert an upfront EUR/MW estimate
to EUR/MW/year; use the same financing and payment-timing convention as the rest
of the study. This implementation chooses an annual enabled portfolio, which may
expand or contract between years. It does not track DSM build vintages, retirement,
or sunk investment. This is suitable for an annual service-cost approximation;
it must not be interpreted as a persistent equipment-stock investment pathway.
The annual capacity charge enters fixed costs; activation costs enter variable
costs with the model's existing annualization, discounting and MEUR conversion.
Fixed-capacity rolling solves retain constant capacity charges; realized annual
reports charge the annual capacity once, rather than once per window.

Do not use market incentive rates unchanged as `c_shift`: they may include
transfers, scarcity rents or payment for both inconvenience and equipment already
covered by `c_capacity`. A zero real activation cost is a valid technical-potential
sensitivity. A positive calibrated disutility is needed for welfare interpretation
when consumers lose comfort. Existing carbon/trade policy accounting elsewhere
in H2RES is unchanged by the DSM extension.

## Literature findings and calibration implications

For appliance availability estimates excluding heating, industry and transport,
the source review in the DSM development copy contains the extracted country data; that research archive is not bundled here.

- [Zerrahn and Schill (2015), *Energy* 84, 840–845](https://doi.org/10.1016/j.energy.2015.03.037)
  ([author manuscript](https://wolfpeterschill.de/wp-content/uploads/Zerrahn_Schill_2015_Energy.pdf))
  show how inconsistent recovery constraints can overstate flexibility. They also
  allow both preponing and postponing load. Their pairwise time-limit formulation
  is more detailed than this restored day/week block model; the two should not be
  presented as identical.
- [Gils (2016), *Applied Energy* 162, 401–415](https://doi.org/10.1016/j.apenergy.2015.10.083)
  ([DLR manuscript](https://elib.dlr.de/99320/1/Gils_EconomicDRPotential_rev1.pdf))
  integrates flexible loads in REMix with investment and operating costs. Avoided
  backup capacity is a major benefit in that case study. Cost and technical
  assumptions strongly affect uptake. This supports endogenous enabled MW and
  cost sensitivities alongside energy-shift reporting.
- [Heitkoetter et al. (2020), regionalised open DR dataset](https://arxiv.org/abs/2009.05122)
  estimate time-dependent potentials and technology-specific cost curves.
  Geographic and appliance composition matter; their German results are not a
  ready-made cost calibration for another country. Heating and e-mobility in that
  dataset also need to be excluded when these are already separate H2RES sectors.
- [DIETER objective documentation](https://diw-evu.gitlab.io/dieter_public/dieterpy/model/equations/eq_objective.html)
  includes annualized DSM investment, fixed costs, and variable activation costs.
  It provides an operational example of placing DSM alongside supply and storage
  in a common system-cost objective.
- [Thrän, Green and Shorten (2026), *Energy Conversion and Management* 349, 120811](https://doi.org/10.1016/j.enconman.2025.120811)
  ([open manuscript, revised December 2025](https://arxiv.org/abs/2502.03124))
  propose levelised DR costs that explicitly include consumer reward payments.
  That is useful for stakeholder procurement comparisons. Our boundary-based
  inference is that those payments must be separated from real resource costs
  before importing their estimates into a whole-system objective. Their EV and
  heat-pump examples are also outside this module's basic-load scope.

For this model, the practical inference is to calibrate the **eligible residual
basic load** first and then the costs of enabling that load. The selected 1.5%
weekly subset is a scenario estimate for buffered loads, not evidence that ordinary
household demand can actually wait a week. The legacy adjustment-ramp fee is not
restored: it needs a demonstrated physical switching cost rather than an
actor-payment interpretation.

A useful exploratory comparison is off/daily/weekly/combined, varying the shared
hourly power cap independently of the energy fractions. Annual enabling costs of
0/5,000/10,000/30,000 EUR/MW/year and shifting costs of 0/2/5/20 EUR/MWh remain
proposed sensitivity points, not measured ranges.
Compare total discounted system cost, installed supply/storage capacities,
peak demand, curtailment and emissions. Evaluate costs against a matching no-DSM
case with identical policy, temporal sampling and forecast assumptions. Benefits
already visible in supply costs must not be added again as a separate credit.

## Outputs and validation

Each exported year or myopic result chunk includes `dsm_hourly_YEAR.csv`,
`dsm_classes_YEAR.csv`, `dsm_summary_YEAR.csv`, and `dsm_assumptions.json`. Hourly rows show original and
shifted basic demand, signed/up/down adjustment, outstanding block energy and
annual reporting weight. Summaries show enabled MW, transferred MWh, upward and
downward energy, net energy, and undiscounted annual DSM costs in EUR. Class rows
show the outstanding balance and actual used/available energy quota in each block.
Summaries include daily/weekly shifted MWh, effective class fractions and rollout.
Representative summaries are annualized estimates; stitched rolling summaries
use accepted hours only. `annual_capacity_cost_eur` includes annualized equipment
and fixed operation together.

Run `python -m unittest scripts.test_electricity_dsm -v`. Tests solve physical and
economic cases, including an 8760-hour multi-year chronology, weekly carryover
through daily solves, custom horizons without lookahead, year-end remainders,
sample gaps, weighted conservation, checkpoint restart, and the actual production
electricity-demand balance. DSM energy equations also enter the model's existing
physical balance audit. Full national multi-sector scenario runs are separate
from these focused regression solves.
