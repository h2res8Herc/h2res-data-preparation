# H2RES documentation library

**Edition:** 12 November 2026. **Language:** English. **Model examined:** `D:\POSAO\H2RES_12.11.2026`.

This library documents two separate applications: the standalone internet data preparation tool in this repository and the supplied H2RES optimization model. Data preparation writes files. Model execution, investment optimization and dispatch belong to the separate model environment.

**12 November model update:** start with the [illustrated script-based user guide](H2RES_USER_GUIDE.md), [model user manual PDF](H2RES_USER_MANUAL.pdf) or [offline model manual](H2RES_USER_MANUAL.html). The guide contains 32 screenshots of actual source excerpts, directory listings and worksheet previews, labelled as read-only documentation views. The desktop GUI is outside this manual's scope. New sections cover electricity DSM, product based industry and trade, current workbook selection and solver-warning behavior.

The model source/input inventory now describes `H2RES_12.11.2026`, including nested variants. The preparation tool still has its separately dated 2 November native export contract and refactored CSV export; see [native data delivery](MODEL_DATA_2_11_2026.md), [current portable preparation guide](PORTABLE_USER_GUIDE.md), [paper-method audit](PAPER_METHOD_AUDIT.md) and [refactored export](REFACTORED_EXPORT.html). Preparing a legacy bundle does not validate every newly added model feature.

**Expanded formulation and configuration edition:** the [main configuration guide](MAIN_CONFIGURATION_GUIDE.md) explains workflow selection, dependencies and scenario combinations across all modules. The [mathematical formulation](MATHEMATICAL_FORMULATION.md) contains 62 numbered, source-linked equations rendered as offline vector graphics. The [complete option reference](MODEL_OPTION_REFERENCE.md) explains all 381 recorded assignments, covering 378 unique settings across `main.py` and the three policy modules. Author-reported tested cases are identified separately from static source verification.

## Start here

**6 November update:** [H2RES-refactored CSV export](REFACTORED_EXPORT.html) supports the supplied bus-based model and `data_chile` layout. It retains the workbook export and documents the native industrial-service and exogenous transport-pathway adaptations.

| Document | Audience and contents |
|---|---|
| [Data preparation manual](DATA_PREPARATION_MANUAL.md) | Installation, interface, internet sources, country selection, caching, sector methods, input assumptions, validation and troubleshooting |
| [Paper-method audit](PAPER_METHOD_AUDIT.md) | Facility-based industry, eight-point heating weather, CHP/fuel maps, actual OSM transport infrastructure, automatic downloads, source vintages and explicit coverage assumptions |
| [H2RES model manual](H2RES_MODEL_MANUAL.md) | Model architecture, planning modes, mathematical formulation, sector coupling, policy constraints, cost accounting, execution, solver diagnostics and outputs |
| [Main configuration guide](MAIN_CONFIGURATION_GUIDE.md) | Complete workflow recipes, all sector/time/policy combinations, normalization and support limits |
| [Mathematical formulation](MATHEMATICAL_FORMULATION.md) | Numbered equations, notation, physical units, interpretation and code provenance |
| [Complete option reference](MODEL_OPTION_REFERENCE.md) | Meaning and effect of every recorded main/policy setting |
| [Input and output reference](DATA_REFERENCE.md) | File contracts, workbook families, field meanings, units, annual investment limits, joins, schema and examples |
| [Assumptions and limitations](ASSUMPTIONS_AND_LIMITATIONS.md) | What is observed, derived, inherited or assumed; applicability and outstanding calibration needs |
| [References](REFERENCES.md) | Scientific literature, dataset/API documentation, technology references, inherited bibliography and verification notes |
| [Code reference](CODE_REFERENCE.md) | Configuration values, optimization variable/constraint call sites and source line locations extracted from this exact model copy |
| [Machine-readable inventories](inventory/) | Complete CLI catalogue, workbook headers, CSV headers, configuration assignments, source URLs and hashes |
| [BibTeX bibliography](references.bib) | Bibliography suitable for a publication or reference manager |

Open the [complete PDF manual](H2RES_COMPLETE_DOCUMENTATION.pdf) for reading or sharing, or the [searchable offline HTML](H2RES_COMPLETE_DOCUMENTATION.html) for navigation between sections and references. Markdown files remain the editable source of the documentation.

## Reading paths

1. **First model use:** the illustrated script-based guide, then model manual sections 3, 15 and 16. For data preparation, use the current portable guide.
2. **Prepare Italy:** preparation manual sections 4, 6 and 14; compare generated `System`/`zone` fields with the selected country.
3. **Prepare process industry:** preparation manual section 10 and assumptions register A06–A10.
4. **Run a study:** model manual sections 1–5 and 15–18, followed by the data reference.
5. **Review a paper:** formulation, assumptions register, source registry, exact source hashes and validation evidence.
6. **Maintain code:** code reference and inventories; regenerate them after changing implementation or templates.

## Scope and evidence

The descriptions are based on the actual source files and live input schemas, not just the folder name or historical README files. Some notes supplied with the model describe older copies, experimental corrections or staged candidates. They are provenance, not proof that a feature or correction is active in this copy. The exact examined files are recorded in [documented_version.json](inventory/documented_version.json).

The mathematical notation is a readable representation of the implemented constraint families. It deliberately suppresses asset-specific indices and conditional branches. For the exact executable form, consult the named implementation and line-level inventories. A static call-site count is not the number of rows or columns in an instantiated optimization problem.

References explain scientific background or data provenance. They do not make inherited scenario values empirically calibrated. Unattributed or incompletely verified assumptions are identified explicitly. Preparing these documents did not run or solve H2RES and did not change the original model's inputs or code.

## Rebuilding the documentation

From the preparation repository:

```powershell
python docs/build_reference_inventory.py --model-root "D:\POSAO\H2RES_12.11.2026"
python docs/capture_model_manual.py --render
python docs/build_model_explanations.py
python docs/build_documentation.py
python docs/validate_documentation.py
python docs/render_pdf.py
```

The first command reads the model and writes only documentation inventories. The second creates the reference lists and combined HTML. The third checks internal links, references, inventory consistency and source hashes. The optional final command prints the HTML to PDF using a hidden Chrome or Edge session and an isolated browser profile. These commands are documentation tools, not model runs.
