"""Refresh narrative documentation for the inspected 12 November model snapshot."""
from pathlib import Path
import json

D = Path(__file__).resolve().parent


def replace(path, old, new):
    text=path.read_text(encoding='utf-8')
    if old in text:
        path.write_text(text.replace(old,new),encoding='utf-8')
    elif new not in text:
        raise ValueError(f'Expected narrative not found in {path.name}: {old[:80]}')


def main():
    for name in ['H2RES_MODEL_MANUAL.md','DATA_REFERENCE.md','README.md']:
        p=D/name
        text=p.read_text(encoding='utf-8').replace('H2RES_1.11.2026','H2RES_12.11.2026').replace('1 November 2026','12 November 2026')
        p.write_text(text,encoding='utf-8')
    p=D/'H2RES_MODEL_MANUAL.md'
    replace(p,'The reviewed `main.py` uses scenario name `industry_testx`, `Myopic=True`, `partial_perfect_foresight=True`,',
            'The reviewed `main.py` uses scenario name `industry_CC_5y`, `Myopic=True`, `partial_perfect_foresight=False`,')
    replace(p,'and `disable_transport_infrastructure=True`. The latter is labelled a debugging setting in the source: do not describe EV/FCEV infrastructure investment as active in a study using that setting.',
            'and `disable_transport_infrastructure=False`. Transport infrastructure is therefore not suppressed by that debug switch. Product based simple industry and both daily/weekly electricity DSM are disabled in the delivered selection; they are documented in sections 19 and 20.')
    replace(p,'Technology file selection follows regular/category/complex and e-fuel flags. Category e-fuel conservative mode selects `flex_tech_efuel_categories_electricity_review.xlsx`; its technical alternative selects the corresponding `_electricity_technical_2050.xlsx`. Complex electricity variants change the complex workbook name. The retained legacy combined category/complex workbooks are not a supported simultaneous mode. See [data reference](DATA_REFERENCE.md) for the exact mapping.',
            'Technology file selection follows regular/category/complex and e-fuel flags. Category e-fuel conservative mode now selects `data/flex_tech_efuel_categories.xlsx`; its technical alternative selects `data/variants/technical_2050/flex_tech_efuel_categories.xlsx`. Complex electricity variants select the corresponding `industry_complex*_electricity_technical_2050.xlsx` process workbook while retaining their normal flex-tech filename. Categories and complex industry are alternatives. See the [visual user guide](H2RES_USER_GUIDE.md) and [data reference](DATA_REFERENCE.md) for the exact mapping.')
    replace(p,'An optional separated industry-process/other-carbon representation restricts which captured streams can enter geological storage. It is disabled in the reviewed snapshot.',
            'The separated industry-process/other-carbon representation restricts which captured streams can enter geological storage. It is enabled in this snapshot through `separate_industry_process_carbon_balances=True`; `model_CC`, amine storage and post-generation CO2 storage are also enabled. `complex_industry_process_capture_required=False` leaves process-capture deployment to the applicable carbon and technical constraints rather than universally forcing it.')
    replace(p,'python outputs_complex_HR/model_inputs/run_model_scenario.py --model-root "D:\\POSAO\\H2RES_12.11.2026"\npython outputs_complex_HR/model_inputs/run_model_scenario.py --model-root "D:\\POSAO\\H2RES_12.11.2026" --solve',
            'python outputs_all_HR/data/run_model_scenario.py --model-root "D:\\POSAO\\H2RES_12.11.2026"')
    replace(p,'### 15.2 Separate integration example','### 15.2 Separate preparation integration')
    text=p.read_text(encoding='utf-8')
    marker='### 15.3 Resume and historical decisions'
    caveat='The preparation contract was developed against the 2 November native layout. A current legacy bundle is not evidence that the new product-industry workbook, DSM assumptions or every later model extension has been generated or validated. Use the adapter validation output before considering a solve; this documentation did not validate that adapter against a full 12 November solve. Run the native model directly for the script-based workflow described in the visual guide.\n\n'
    if caveat not in text: text=text.replace(marker,caveat+marker)
    text=text.replace('The supplied folder also contains a critical-correction/rebuild harness and verification files describing unpromoted candidates.',
        'The supplied folder contains the unified-model implementation notes, component regression tools, and a historical critical-correction/rebuild harness. The current `docs/UNIFIED_MODEL.md` describes the integration of simple industry, electricity CBAM history handling and DSM. These are distinct from older verification files describing unpromoted candidates.')
    solver_note='The delivered `main.py` has `solver_allow_provisional_solution=True` and `solver_postoptimal_checks_warn_only=True`. Consequently, a finished export can contain warnings or a provisional solution: completion alone is not a strict quality certificate. Runtime policy also requires annual capture-quality checks and sets a 0.1 physical-energy tolerance and a 0.001-tonne amine-mass tolerance in their applicable checks. Read the exported status and physical audits together with the actual branch that produced them; a warning is not proof that a gate stopped the run.\n\n'
    if solver_note not in text: text=text.replace('A barrier solution without crossover',solver_note+'A barrier solution without crossover')
    p.write_text(text,encoding='utf-8')
    addition='''
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

## 20. Product based simple industry and regional trade

This is a separate optional representation, selected by `model_simple_industry=True` and `simple_industry_dat='./data/simple_industry.xlsx'`. It is different from the worksheet named `simple_industry` inside a flex-tech workbook: that worksheet is the legacy pooled-service remainder. The new external workbook contains fixed industrial product recipes, physical plants and product markets. The delivered model leaves this mode off.

Enabling product industry configures the electricity-and-product-industry run and disables overlapping legacy transport/industry, category/complex, e-fuel, hydrogen and industrial capture/storage blocks. Heating retains its switch. Active example systems are HR, RS and BA through `simple_industry_active_zones` in model policy. Independent switches control industrial CBAM, domestic carbon pricing, outside imports, optional outside exports and flexible steel operation. Only one electricity CBAM option may be selected; electricity CBAM and product CBAM are separate accounts.

The workbook uses `plants`, `inputs_per_tonne`, `economics`, `fuel_prices`, `markets`, `market_years`, `carbon_policy`, `import_suppliers`, `import_years`, `trade_routes`, `profiles`, `baseline_load` and `metadata`. Production is tonnes per one-hour interval, electricity is MWh/t, non-electric recipes GJ/t and carbon factors tCO2/GJ. Supply ceilings, grid limits and inventories limit dispatch; nameplate capacity does not require production. Fixed-operation plants remain constant within each calendar day after availability adjustment; flexible plants may vary hourly under their limits.

Mandatory product markets must be supplied. Regional plants can trade; bounded outside offers are available only under their applicable switches and eligibility. One supplier's annual budget is shared across destinations. No unlimited emergency source or automatic demand reduction is introduced. Origin tracking preserves supplier footprints for final-destination carbon charging and separates territorial direct emissions from embedded trade emissions. Prices are prescribed; there is no endogenous steel-price equilibrium.

The supplied RS BF-BOF and BA scrap-EAF plants, external supplier prices/footprints and rest-of-Europe supply are illustrative scenario inputs, not calibrated named installations. The example requires RS 800,000, BA 300,000 and HR 1,000,000 tonnes/year, plus 134,000,000 tonnes/year for Europe outside HR. The European background offer serves that Europe market, not a bypass for domestic import restrictions. Check every price, quantity and route before drawing policy conclusions.

`baseline_load` specifies already-existing plant electricity to remove from the basic profile. Example removals are zero, so example plant loads are additions. Calibrating a real plant requires a defensible removal to avoid counting the same demand twice. Likewise, do not enter coke carbon in both the fuel recipe and process-carbon field.

Review `simple_industry_hourly.csv`, `simple_industry_fuels.csv`, `simple_industry_sales.csv`, `simple_industry_markets.csv`, `simple_industry_summary.csv`, `simple_industry_imports.csv`, `simple_industry_demand.csv`, `simple_industry_cbam_borders.csv`, `simple_industry_fiscal.csv` and the applicable levelized-cost summary. For field-level operation, trade budgets and capital/CBAM allocation, use the supplied [simple-industry implementation notes](model_notes_2026_11_12/SIMPLE_INDUSTRY.md). The [unified-model notes](model_notes_2026_11_12/UNIFIED_MODEL.md) report bounded component/8760-hour example evidence and known baseline regression exceptions; they do not certify a full national transition solve.
'''
    if '## 19. Basic electricity' not in text: p.write_text(text+'\n'+addition,encoding='utf-8')
    p=D/'DATA_REFERENCE.md'
    replace(p,'Conservative: `flex_tech_efuel_categories_electricity_review.xlsx`; technical: `flex_tech_efuel_categories_electricity_technical_2050.xlsx`',
            'Conservative: `flex_tech_efuel_categories.xlsx`; technical: `variants/technical_2050/flex_tech_efuel_categories.xlsx`')
    p=D/'README.md'
    text=p.read_text(encoding='utf-8')
    start=text.index('**Preparation update,')
    end=text.index('## Start here',start)
    text=text[:start]+'''**12 November model update:** start with the [illustrated script-based user guide](H2RES_USER_GUIDE.md), [model user manual PDF](H2RES_USER_MANUAL.pdf) or [offline model manual](H2RES_USER_MANUAL.html). The guide contains 32 screenshots of actual source excerpts, directory listings and worksheet previews, labelled as read-only documentation views. The desktop GUI is outside this manual's scope. New sections cover electricity DSM, product based industry and trade, current workbook selection and solver-warning behavior.

The model source/input inventory now describes `H2RES_12.11.2026`, including nested variants. The preparation tool still has its separately dated 2 November native export contract and refactored CSV export; see [native data delivery](MODEL_DATA_2_11_2026.md), [current portable preparation guide](PORTABLE_USER_GUIDE.md), [paper-method audit](PAPER_METHOD_AUDIT.md) and [refactored export](REFACTORED_EXPORT.html). Preparing a legacy bundle does not validate every newly added model feature.

'''+text[end:]
    text=text.replace('The original PDF/HTML and source inventories retain their dated snapshot; these linked updates describe the newer preparation behavior.','')
    text=text.replace('1. **First use:** preparation manual sections 1–5, then its troubleshooting section.','1. **First model use:** the illustrated script-based guide, then model manual sections 3, 15 and 16. For data preparation, use the current portable guide.')
    text=text.replace('python docs/build_documentation.py','python docs/capture_model_manual.py --render\npython docs/build_documentation.py')
    p.write_text(text,encoding='utf-8')
    p=D/'ASSUMPTIONS_AND_LIMITATIONS.md'
    text=p.read_text(encoding='utf-8')
    if '## 7. Additional 12 November' not in text:
        text+='''
## 7. Additional 12 November model assumptions

The new DSM energy pools, hourly power cap, rollout and enabling/activation costs are scenario assumptions. They are not independently measured values for all active countries. The supplied simple-industry plants, world/European offers, product demand and carbon footprints are illustrative and require calibration. Product trade can move emissions outside the modeled territory; falling territorial emissions alone do not establish falling embedded emissions or domestic technology replacement.

The external workbook `simple_industry.xlsx` and the flex-tech worksheet `simple_industry` have different meanings. Enabling the product model disables overlapping legacy blocks. Baseline electricity removal must be calibrated when a plant's load is already included in the basic profile.

This version enables separated process/other carbon balances. Its default solver settings also permit provisional outcomes and warning-only postoptimal checks. Output files alone are not an optimization-quality certificate. This manual is a static inspection with source/input hashes, not a new national solve or a certification of the preparation adapter against every 12 November extension.
'''
    p.write_text(text,encoding='utf-8')
    notes=D/'model_notes_2026_11_12'; notes.mkdir(exist_ok=True)
    model=Path(json.loads((D/'inventory/documented_version.json').read_text())['model_root'])
    for name in ['SIMPLE_INDUSTRY.md','ELECTRICITY_DSM.md','UNIFIED_MODEL.md']:
        (notes/name).write_bytes((model/'docs'/name).read_bytes())
    print('Updated 12 November narrative and copied supplied module notes; original model unchanged.')


if __name__=='__main__': main()
