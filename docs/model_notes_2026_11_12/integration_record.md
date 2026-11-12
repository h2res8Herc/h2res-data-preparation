Source: `reports/unified_integration/README.md` in the inspected model. Relative report links below are preserved as source-tree paths. Reported tests were not rerun for this manual.

# Unified model integration record

Base: `G:\LUKA\H2RES_9.11.2026 - Copy - Copy`.
Incoming extensions: `G:\LUKA\H2RES_11.11.2026`.
Standalone destination: `G:\LUKA\H2RES_12.11.2026_unified`.

## Merge scope

The simple-industry input, model, policy, results and example-generator modules
and their trade schema were imported together. Electricity DSM was imported
with all demand-balance, cost, export, capacity-bundle and rolling/resume hooks.
Electricity CBAM history recovery and its tests were imported.

`main.py`, the core builder, the cost/solver script and runtime policy were
merged selectively. Original case assignments and the current industry's
2045 completion policy, green-input changes, amine bounds/audits and annual
CC solver recovery were retained. General workbook/policy differences from
the CBAM development case were not copied.

The steel trade example workbook is the only replaced input workbook. The
prior workbook is in `original_inputs/`. Its plant, recipe, economic, carbon
policy, fuel price, profile and baseline sheets match the updated workbook.
New market/supplier examples are described in `docs/SIMPLE_INDUSTRY.md`.

## Validation result

854 tests passed out of 861 registered tests; two reproduced baseline failures
are explicitly expected and five unavailable-archive checks are skipped. There
are no unexpected failures or errors. Both solved subsystem probes passed.

## Evidence

- `merge_provenance.json`: incoming files and their hashes, and selectively
  merged files.
- `source_snapshot_sha256.json`: original file hashes before integration.
- `integration_review.json`: final source-preservation, case-assignment and
  merge checks.
- `final_payload_sha256.json`: hashes for the delivered code, docs and inputs.
- `test_summary.json` and `regression_tests.txt`: final regression run.
- `original_baseline_summary.json` and `original_baseline_tests.txt`: failures
  independently reproduced on the unchanged original model.
- `initial_test_summary.json` and `initial_regression_tests.txt`: initial broad
  run, including legacy import-path and temporary-directory setup failures;
  the final runner supplies both import roots and the temporary parent folder.
- `validation_summary.json`: input/syntax checks and solved subsystem results.
- `combined_subsystem/`: outputs from 48 chronological hours annualized to a
  year, using the real steel workbook, nested daily/weekly DSM and the actual
  production Option 2 electricity-CBAM constraint.
- `full_year_steel/`: outputs from 8,760 physical hours with zero local steel
  emissions caps and bounded outside suppliers.

The two solved probes returned OPTIMAL with zero reported constraint and bound
violations. In the combined probe, 288 MWh was shifted in the sample, 120 MWh
of electricity crossed RS to HR and its electricity-CBAM charge was EUR 5,040.
The steel-only year met 135 million tonnes of European demand including HR,
plus RS/BA demand. Local plants were idle; additional outside steel was
2.1 million tonnes and European background supply was 134 million tonnes.
These quantities depend on the illustrative offers, not calibrated forecasts.

## Inherited test limitations

Two failures were reproduced in the original model and have not been changed
by this integration:

1. The historical complex-workbook expansion utility serializes one float as
   `0.4336395781623076` instead of `0.43363957816230764`. Its strict byte-value
   preservation regression fails at roughly 5.6e-17.
2. The existing source-calibration helper returns efficiency `5.28` for its
   unobserved-combustion fixture, exceeding that regression's ceiling of one.

Five test methods also depend on older combined-category workbooks, an external
steam backup, or a combined-industry archive missing from both the base copy
and this delivered copy. No substitute historical inputs were invented.
The final runner annotates all seven limitations explicitly; unexpected failures
still fail the run and an unexpected success of an expected failure also fails.

A complete national energy-model run has not been performed. This record
establishes integration and subsystem behavior, with the above inherited
limitations stated explicitly.
