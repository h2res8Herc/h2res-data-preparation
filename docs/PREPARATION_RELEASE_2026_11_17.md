# Data preparation release — 17 November 2026

This release updates the data-preparation application. H2RES optimization is run separately. Both native workbooks (`data`) and the optional refactored CSV case (`data_refactored`) are supported.

## Regional electricity profiles

On **Power & profiles**, select **Regional electricity profiles → sector-weighted**. Select **Data task → generate** on **Output format** to calculate the new curves; exporting existing outputs retains previously prepared curves.

The method combines regional Eurostat employment/GVA, population and accommodation-night observations with representative BDEW and TU Berlin sector templates. Tourism follows downloaded visitor geography and seasonality, rather than a uniform share of every service region. Its national electricity intensity is an explicit assumption: by default, 10% of service electricity is assigned to accommodation, deducted from the service budget. This setting is editable.

Balancing preserves both the ENTSO-E national load in every hour and the existing JRC annual regional ratios. Different source-year national totals are reconciled by a common national scale; unscaled 2019 atlas MWh are not imposed on a different year's ENTSO-E total. The source-year and 8,760-hour model calendars both retain the regional annual ratios. The same gross curves feed both export interfaces. Explicitly coupled sectors reduce refactored residual demand according to its documented accounting rules.

The existing `national-scaled` calculation remains the default for compatibility. Select `sector-weighted` explicitly to use the new process. Its additional data use Eurostat and public holiday sources, not additional Open-Meteo weather requests or neural-network training. The compact representative-profile library is included in both GitHub source and the portable download. ENTSO-E credentials are still required for uncached national observations.

See [method, sources, equations and assumptions](REGIONAL_ELECTRICITY_PROFILES.md).

## Export corrections

- Refactored exports respect the selected sectors. Power-only cases do not attempt to build transport, heating or industry inputs; they retain gross electricity demand.
- Regional defaults can use prepared electricity shares when other sector demand is not available at the selected regional resolution. Absolute stocks and applicable hourly quantities are divided among regions rather than copied at national scale into every region.
- The `simple_industry` remainder is recomputed after regional expansion and remains consistent with the excluded services in each variant.
- Complete power preparation generates hydro availability/inflows from bundled data even when an old saved configuration requested skipping them. Source-only diagnostic exports can still skip hydro.
- Export-existing mode checks required power files before expensive workbook processing and reports missing inputs without replacing the earlier validated bundle.
- Recent generator financial-key, unsupported power-asset, Excel integrity, atomic-publication and weather retry corrections remain included. Open-Meteo HTTP 429 responses retain successful caches and retry until success or cancellation; daily local estimates do not create the former long local pauses.

## Updating and reusing previous work

1. Extract the complete portable ZIP into a new writable folder and run `SETUP_WINDOWS.bat`. Do not copy a virtual environment from another installation.
2. Start `START_DATA_PREPARATION.bat` and point the output/cache fields to the existing case folders if you wish to reuse them. Keep **Refresh downloaded source data** off.
3. To rebuild exports from complete existing sector files, select **export existing outputs**, with matching country, geography and source settings.
4. To change electricity shape method or create missing profiles, select **generate** with the required sectors. Cached source observations and completed weather downloads are reused. A missing file is not created by export-existing mode.
5. Enable the refactored export checkbox if both model formats are required. Review each output's validation report.

## Verification and limits

The release regression suite contains 304 tests. It covers calendar reconciliation, sector/tourism accounting, source-library integrity, export scope, regional defaults, financial links, Excel structure, hydro checks, packaging/recovery and weather handling. Actual Croatian 2020 load was checked for all 21 regions; Italian public-source coverage was checked for 107 packaged regions, while its numerical trial used synthetic national load. Existing Croatian native/refactored exports and the separate refactored reader were also exercised during development.

These checks establish accounting and interface consistency. They do not guarantee source availability for every country/year, regional prediction accuracy, optimization feasibility or the absence of future bugs. Generated case data and personal API credentials are not distributed. Source vintages, transferred timing templates and unsourced scenario defaults remain documented assumptions.
