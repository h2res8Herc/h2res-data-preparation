# Combined H2RES model-input output

The preparer writes a directly usable **`<output directory>/data`** folder for the selected countries/zones. By default it populates every native `flex_tech` alternative and all four complex-industry companions, with matching industry, transport and e-fuel inputs. The original sector outputs remain available for inspection. Costs, policy assumptions and other inputs not sourced online retain documented model defaults.

**Current target:** `H2RES_2.11.2026_novi`. The delivery now mirrors the model's complete 43-file `data` tree. See the [current model-data layout and migration guide](MODEL_DATA_2_11_2026.md), including the `sources` and `variants/technical_2050` directories.

## Files to use

Example layout for a Croatia category/non-e-fuel selection:

```text
outputs_HR/
  data/                               ready-to-use native H2RES data folder
  H2RES_DATA_manifest.json             configuration, defaults and validation
  model_inputs/
    data/                             complete working/reference bundle
    h2res_inputs/                     combined delivery for this configuration
      data/
        flex_tech_categories.xlsx     selected master technology workbook
        policy.xlsx
        policy_efuel.xlsx
        policy_fuels.xlsx
        h2_terminals.xlsx
        generators.csv
        electricity_demand.csv
        renewable_availability.csv
        hydro_inflows.csv
        industry_heat.csv
        industry_category_profiles.csv
        industry_electricity.csv
        heating_individual.csv
        heating_district.csv
        heating_electricity.csv
        transport_demand.csv
        transport_profiles.csv
        ...                           remaining native supporting CSV files
      README.md
      validation.json
      model_input_selection.json
      FILES.csv
      package_manifest.json
      bundle_manifest.json
      H2RES_model_inputs.zip
```

The ZIP contains the same `h2res_inputs` directory, excluding the ZIP itself. By default, every native `flex_tech` variant receives the prepared country data, and four generated `industry_complex` companions cover the e-fuel/electricity alternatives. `variant_inventory.json` records the settings for each; `model_input_selection.json` identifies the currently selected workbook. Native names and relative paths are retained because the model selects them by its flags.

The master workbook holds the applicable technology, heating, transport, industry, cost and investment sheets. Distribution/demand/availability inputs remain CSV files in the model's required layout. Files are copied byte-for-byte, preserving Excel formulas and cached results, numeric precision, hourly keys and input units.

## Interface

On **Output format**:

1. Keep **Package prepared data in H2RES input format** enabled.
2. Keep **Also create an input archive and validation package** enabled if you want the ZIP.
3. Choose the industry representation and e-fuel option for this configuration.
4. Select **generate** to source/prepare data, or **export existing outputs** to reuse prepared sector files.
5. Keep **Generate all native flex_tech and industry variants** enabled.
6. Use **Open H2RES data folder** to open `<output directory>/data`.

Select all four sectors when you want newly generated power, industry, transport and heating inputs. Unselected sectors use the portable reference; `model_input_selection.json` records this per sector. The existing Croatia bundle in `outputs_all` contains generated complex-industry inputs and reference inputs for the other three sectors.

When generating power for a complete H2RES export, wind/solar profiles are always enabled. The skip option applies only to source-only or diagnostic exports. Provider and calibration choices still apply, and downloaded site weather is cached for retries. A weather acquisition failure stops during power preparation and preserves existing curves; it cannot silently return success and defer missing generator columns until the final export. Exporting existing outputs remains an offline action and reports missing profiles without downloading them.

The updated generator creates the delivery even when launched from a preparation window opened before this update. Reopen the interface when you want to see the new checkbox and open-folder button.

## Commands

The combined delivery follows `--model-export` by default. Use `--no-model-ready-package` to skip it. To request it explicitly while re-exporting the existing Croatia complex-industry selection:

```powershell
python generate_all_sector_inputs.py --countries HR --sectors industry --spatial-level country --out-root outputs_all --data-root data_all --industry-mode complex --efuels --export-only --model-ready-package --require-model-ready
```

To package an already exported native bundle without downloading or regenerating sectors:

```powershell
python model_ready_package.py --bundle outputs_all/model_inputs
```

The standalone command rechecks native input coverage. No provider credentials are required to package existing files. New data sourcing still needs any credentials required by its selected provider.

## Validation and integration

The H2RES delivery requires **INPUT COVERAGE PASSED**. An incomplete or inconsistent input set is rejected before the folder/ZIP is published. Its errors are reported in the run log and `model_export_failure.json`; the previous valid export is retained. This requirement is enforced for combined H2RES input packages even if an older configuration disabled the optional coverage checkbox. Packaging does not fill missing national data silently.

`FILES.csv` and `package_manifest.json` inventory every data file and its SHA-256 digest. `model_input_selection.json` records the selected master workbook, flags, zones and generated/reference sector provenance. A prepared scenario carries its scenario metadata and launcher dependencies into the delivery.

Use the contents of the delivery's `data` directory with a separate H2RES installation configured for that selection. Preparing the package does not modify the model installation or run an optimization. Passing input coverage does not certify scenario feasibility.
