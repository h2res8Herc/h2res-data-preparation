# Current model input paths

The model reads live inputs from `data`. Generator sources and reference
workbooks are kept separately in `analysis/input_templates`. Edit the live
workbook selected by your flags; `main.py` prints its path when data loads.

## Technology workbook selection

| Industry mode | `model_efuel=False` | `model_efuel=True` |
|---|---|---|
| Regular | `flex_tech.xlsx` | `flex_tech_efuel.xlsx` |
| Categories | `flex_tech_categories.xlsx` | `flex_tech_efuel_categories.xlsx` |
| Complex industry | `flex_tech_complex_industry.xlsx` | `flex_tech_efuel_complex_industry.xlsx` |
Categories and complex industry are alternative methods for the same problem.
Enable at most one. The configuration and reader reject enabling both.
The old combined workbooks are retained in `archive/combined_industry`.

The six names above are the live inputs. `flex_tech_efuel_categories.xlsx`
contains the previously selected conservative electricity case (formerly
`flex_tech_efuel_categories_electricity_review.xlsx`). Its technical-2050
alternative has the same short filename in `data/variants/technical_2050`;
select it with `industry_category_electricity_case = "technical_2050"`.
The default `"conservative"` setting selects the live workbook above.
Other historical inputs and manual copies are kept in `archive`.

Every live technology workbook already contains the existing annual heating
investment curves. Every e-fuel workbook also includes the existing e-petrol
pathway. The model no longer adds `_heat_curves` or `_e_petrol` to these names.

## Policy and complex-industry data

| Purpose | Live workbook |
|---|---|
| Regular policy | `policy.xlsx` |
| E-fuel policy | `policy_efuel.xlsx` |
| E-fuel trade prices | `policy_fuels.xlsx` |
| Complex industry, regular model | `industry_complex.xlsx` |
| Complex industry, e-fuel model | `industry_complex_efuel.xlsx` |
| Standalone H2 terminals | `h2_terminals.xlsx` |

## Annual industry investment limits in every flex-tech workbook

All six live `flex_tech*.xlsx` workbooks and the technical-2050 alternative
have annual investment columns for 2025–2050.
The supported workbook selection and category/complex exclusivity stay as
described above. The workbook's pooled sheet is named `simple_industry`.

| Sheet | Annual columns | Capacity added per calendar year |
|---|---|---|
| `Industry_data`, `simple_industry` | `max_inv_period_2025` … `max_inv_period_2050` | MW per equipment row |
| `industry_heat_stor`, where present | `max_inv_period_2025` … `max_inv_period_2050` | MWh per storage row |
| `industry_CC` and industry sheets containing capture fields | `CC_max_inv_period_2025` … `CC_max_inv_period_2050` | tCO2/h of capture capacity |
| Same capture sheets | `Reboiler_max_inv_period_2025` … `Reboiler_max_inv_period_2050` | MW of reboiler capacity |
| Same capture sheets | `Tank_stor_max_inv_period_2025` … `Tank_stor_max_inv_period_2050` | tCO2 of amine inventory capacity |

Process and heat-storage columns initially copy each row's existing scalar
`max_inv_period`; no baseline capacities or demands were recalibrated. The
current process defaults are 10,000 MW/year in the regular no-category inputs
and 1,000 MW/year in category/e-fuel inputs. Storage defaults are 100 MWh/year.
Capture-equipment annual cells initially remain blank, meaning unrestricted.

Zero blocks new additions while preserving existing capacity. Blank or absent
annual values use the corresponding legacy scalar (`max_inv_period`,
`CC_max_inv_period`, `Reboiler_max_inv_period`, or `Tank_stor_max_inv_period`).
If that scalar is absent or blank, the year is unrestricted. Values are not
interpolated; negative, non-numeric and infinite active-equipment limits are
rejected, including supplied columns outside the current solve years.

The model sums calendar-year limits over the global investment windows. A
2030 decision following 2025 uses 2026–2030, also when resuming in 2030. The
first decision uses its own year only. A period containing an unrestricted
year remains unrestricted. In single-sector mode, included source-sector
limits first sum by equipment and calendar year. In remainder mode, the
`simple_industry` row supplies the pooled equipment limit directly.

These limits apply in regular, category and complex modes, with or without
e-fuels, under full perfect foresight and myopic planning with or without
partial foresight. They are maximum additions, not required investments,
total-capacity ceilings or spending limits. Process limits that were disabled
in the old no-category builder are now enforced. Equipment without CAPEX
data remains unavailable for investment under the existing category safeguard.

Only active equipment is constrained. The existing `industry_CC` sheet remains
the authority for capture activation and its annual limit takes precedence
over legacy inline capture fields. A capture row shared across categories
limits their combined additions, rather than multiplying the allowance by
the category count. Inline limits can constrain an existing runtime capture
unit without a matching dedicated row; adding annual columns does not enable
new capture units. Amine-tank limits require amine storage to be enabled.
Thermal-storage limits require industry storage to be enabled.

Run `python -m scripts.expand_industry_investment_limits` to append missing
annual columns without overwriting annual edits. The migration preserves
original cells and cached formula results, and leaves unrelated workbook
parts unchanged. Backups and validation are in
`local_validation/all_industry_annual_limits_2026_10_22`.

## Annual complex-industry investment limits

Both `industry_complex.xlsx` and `industry_complex_efuel.xlsx` contain editable
annual columns for 2025–2050:

| Sheet | Columns | Maximum new capacity |
|---|---|---|
| `complex_non_metalic_minerals` | `max_inv_period_2025` … `max_inv_period_2050` | MW/year for each equipment row (branch/component/unit/zone/system) |
| `CC` | `CC_max_inv_period_2025` … `CC_max_inv_period_2050` | tCO2/h of capture capacity added per year |
| `CC` | `Reboiler_max_inv_period_2025` … `Reboiler_max_inv_period_2050` | MW of reboiler capacity added per year |
| `CC` | `Tank_stor_max_inv_period_2025` … `Tank_stor_max_inv_period_2050` | tCO2 of amine inventory capacity added per year |

Zero prevents investment in that equipment in that year; positive values set
an upper bound on additions, not total installed capacity or spending. A blank
process-equipment cell uses the row's legacy `max_inv_period` value, also used
for years without an annual column. The new process columns initially copy
that value (currently 1,000 MW/year). These limits are now enforced in complex
mode; the previous configuration did not enforce the scalar process ceiling.

Capture, reboiler and tank columns initially remain blank (unrestricted).
Only enabled equipment is constrained; tank limits apply when amine storage
is enabled. Blank capture-equipment cells remain unrestricted. For multi-year
decisions, limits are summed over the calendar years since the previous global
decision year; an unrestricted year makes that equipment's period unrestricted.
For example, the 2030 decision on a 2025/2030 grid uses 2026–2030, including
when resuming a myopic run in 2030. The first decision uses just its own year.
Non-numeric, negative and infinite limits are rejected during input loading.

`python -m scripts.expand_complex_industry_investment_limits` adds missing
annual columns while preserving existing annual edits. Backups of the inputs
before this expansion are in
`local_validation/complex_industry_annual_limits_2026_10_22/before`.

## Annual heat-pump investment availability

Annual limits are in the technology workbook, sheet `cap_inv_lim`. Each row
specifies a `year` and `zone`; technology columns give maximum new thermal
capacity in MW/year. The current Croatia HR1 values are estimated scenario
assumptions and can be edited directly in that sheet.

| Technology | 2025 | 2026 | 2030 | 2035 | 2040 | 2050 |
|---|---:|---:|---:|---:|---:|---:|
| Air_to_water_HP | 50 | 90 | 250 | 450 | 650 | 750 |
| Ground_to_water_HP | 5 | 6 | 10 | 15 | 20 | 30 |
| Electric_heater | 100 | 110 | 150 | 200 | 250 | 400 |
| Water_to_water_HP | 5 | 6 | 10 | 15 | 20 | 30 |
| Air_to_water_HP_DH | 50 | 60 | 100 | 150 | 200 | 300 |
| Ground_to_water_HP_DH | 50 | 50 | 50 | 60 | 75 | 100 |
| Electric_heater_DH | 50 | 60 | 100 | 150 | 250 | 500 |
| Water_to_water_HP_DH | 50 | 60 | 100 | 200 | 300 | 650 |

These ceilings constrain additions in both individual and district heating,
with or without e-fuels. They do not require the model to invest, limit
electricity directly, or define hourly heat-pump availability. Electricity
consumption follows the model COP and operation constraints.

For annual decision years, each investment uses that year's cap. A decision
spanning several calendar years receives the sum of those years' limits.
Other constraints still apply: the existing base-year calibration pins new
individual heat-pump investment to zero in 2025.

The reader constructs `HP_inv_period_limit` and `DH_HP_inv_period_limit`;
the builder applies them to `heat_pump_ind_cap` and `heat_pump_dh_cap`.

## Excel repair and reproducibility

The flex workbooks contained worksheet filters overlapping their structured
Excel tables. Excel refused to open them even though Python readers and XML
schema validation accepted the files. The repair removes the duplicate
worksheet filter and its hidden filter name, retaining each table's filter.
Every worksheet cell, formula, cached result and table definition is preserved.

The complete original-to-new name map and source hashes are in
`validation/workbook_map.json`. `validation/preservation.json` verifies the
source files are unchanged and all worksheet cell XML is identical.
`validation/excel_after.json` records normal read-only opens in Microsoft Excel
for all 15 repaired files. `validation/input_paths.json` checks 72 supported
configurations, including both electricity cases.

Manual edits belong in the selected live workbook. Check the current paths
without solving with `python -m scripts.validate_input_paths`. The repair
utility supports read-only checks, for example:

```powershell
python -m scripts.repair_flex_workbooks data/flex_tech_efuel_categories.xlsx --check
```

Omit `--check` to repair a future overlapping-filter problem. The older template
generators require `analysis/input_templates`, which was absent from the source
project and is not needed to run the supplied live inputs.
