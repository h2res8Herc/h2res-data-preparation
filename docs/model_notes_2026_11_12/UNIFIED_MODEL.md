# Unified H2RES model — 12 November 2026

This standalone copy uses `H2RES_9.11.2026 - Copy - Copy` as its base and
incorporates selected code from `H2RES_11.11.2026`.
Run this folder's `main.py` with this folder as the working directory.
Previous model results are not included, so its results history starts empty.

## Included improvements

The current model's industry transition ending in 2045, electricity/e-methane
substitution ceilings, separate industrial process-carbon accounting, amine
inventory bounds and solver acceptance checks are retained.

The imported simple-industry extension adds regional product trade, bounded
outside suppliers, route-specific costs and capacities, mandatory market
balances, and rolling import budgets. Product CBAM follows the original
supplier and final destination, with exemptions, eligible foreign carbon
credits, and producer/importer cost allocation. Its reports distinguish
territorial production emissions from imported embedded emissions.

Electricity CBAM recovers a missing predecessor intensity from loaded history
or its saved CSV, preserves valid zero values and rejects missing/invalid data.
The existing four electricity-CBAM formulations are retained.

Basic electricity DSM adds daily/weekly energy shifting, shared hourly power,
energy quotas, availability rollout, capacity/operating costs, and planning,
rolling dispatch, resume and export integration.

## Choosing a case

All pre-existing case switches and policy inputs from the base copy are
retained. The new `industry_external_imports_active`,
`industry_external_exports_active`, `DSM_day`, `DSM_week`,
`dsm_energy_budget_active`, and `dsm_availability_ramp_active` switches are
present in `main.py` and default to `False`.
DSM parameter defaults are in `policy/runtime_policy.py`.

The detailed categories/complex-industry routes and simple product-industry
route remain selectable alternatives within this codebase. Setting
`model_simple_industry=True` configures the existing electricity/product case
and disables the overlapping legacy industry, transport, e-fuel and CC blocks.
Industrial product CBAM belongs to that simple-industry mode. Electricity
CBAM and DSM remain separately controlled.

The compatible `data/simple_industry.xlsx` includes the new supplier and route
schema and the trade example from the CBAM copy. Existing plants, recipes,
economics, carbon-policy paths, fuel prices, profiles and baseline-removal
inputs are unchanged. The updated markets include Croatian demand and
mandatory rest-of-Europe demand; outside offers are illustrative.
The previous workbook is preserved in
`reports/unified_integration/original_inputs/simple_industry.xlsx`.
Other input workbooks, including both green-substitution workbooks and the
annual policy horizon, retain their original bytes.

For configuration details see [simple industry](SIMPLE_INDUSTRY.md) and
[electricity DSM](ELECTRICITY_DSM.md).

## Validation

From this folder:

```powershell
& 'C:\Users\Korisnik\anaconda3\python.exe' -B scripts/run_unified_regressions.py
& 'C:\Users\Korisnik\anaconda3\python.exe' -B scripts/validate_unified_model.py
```

The regression runner records two reproduced baseline failures as expected
failures and skips five tests requiring historical assets absent from the
source copy. `--include-legacy` runs them without those annotations.
The underlying tests are unchanged. The report identifies every annotation
and includes the original-copy reproduction.

The additional validator checks retained inputs and Python syntax, solves a
combined steel/DSM/electricity-CBAM case, and solves an 8,760-hour steel case
with zero territorial industry emissions. The latter meets demand with bounded
outside supply; it demonstrates trade accounting rather than domestic
industrial decarbonization. Neither subsystem establishes feasibility of a
complete national 2025–2050 energy run.

See [the integration record](integration_record.md).
