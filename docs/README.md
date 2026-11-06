# H2RES documentation library

**Edition:** 1 November 2026. **Language:** English. **Model examined:** `D:\POSAO\H2RES_1.11.2026`.

This library documents two separate applications: the standalone internet data preparation tool in this repository and the supplied H2RES optimization model. Data preparation writes files. Model execution, investment optimization and dispatch belong to the separate model environment.

**Preparation update, 4 November 2026:** the current native data layout follows `H2RES_2.11.2026_novi`. Read [native data delivery](MODEL_DATA_2_11_2026.md) and the [paper-method audit with automatic sources](PAPER_METHOD_AUDIT.md) for the latest regional calculations. The original PDF/HTML and source inventories retain their dated snapshot; these linked updates describe the newer preparation behavior.

## Start here

**6 November update:** [H2RES-refactored CSV export](REFACTORED_EXPORT.html) supports the supplied bus-based model and `data_chile` layout. It retains the workbook export and documents the native industrial-service and exogenous transport-pathway adaptations.

| Document | Audience and contents |
|---|---|
| [Data preparation manual](DATA_PREPARATION_MANUAL.md) | Installation, interface, internet sources, country selection, caching, sector methods, input assumptions, validation and troubleshooting |
| [Paper-method audit](PAPER_METHOD_AUDIT.md) | Facility-based industry, eight-point heating weather, CHP/fuel maps, actual OSM transport infrastructure, automatic downloads, source vintages and explicit coverage assumptions |
| [H2RES model manual](H2RES_MODEL_MANUAL.md) | Model architecture, planning modes, mathematical formulation, sector coupling, policy constraints, cost accounting, execution, solver diagnostics and outputs |
| [Input and output reference](DATA_REFERENCE.md) | File contracts, workbook families, field meanings, units, annual investment limits, joins, schema and examples |
| [Assumptions and limitations](ASSUMPTIONS_AND_LIMITATIONS.md) | What is observed, derived, inherited or assumed; applicability and outstanding calibration needs |
| [References](REFERENCES.md) | Scientific literature, dataset/API documentation, technology references, inherited bibliography and verification notes |
| [Code reference](CODE_REFERENCE.md) | Configuration values, optimization variable/constraint call sites and source line locations extracted from this exact model copy |
| [Machine-readable inventories](inventory/) | Complete CLI catalogue, workbook headers, CSV headers, configuration assignments, source URLs and hashes |
| [BibTeX bibliography](references.bib) | Bibliography suitable for a publication or reference manager |

Open the [complete PDF manual](H2RES_COMPLETE_DOCUMENTATION.pdf) for reading or sharing, or the [searchable offline HTML](H2RES_COMPLETE_DOCUMENTATION.html) for navigation between sections and references. Markdown files remain the editable source of the documentation.

## Reading paths

1. **First use:** preparation manual sections 1–5, then its troubleshooting section.
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
python docs/build_reference_inventory.py --model-root "D:\POSAO\H2RES_1.11.2026"
python docs/build_documentation.py
python docs/validate_documentation.py
python docs/render_pdf.py
```

The first command reads the model and writes only documentation inventories. The second creates the reference lists and combined HTML. The third checks internal links, references, inventory consistency and source hashes. The optional final command prints the HTML to PDF using a hidden Chrome or Edge session and an isolated browser profile. These commands are documentation tools, not model runs.
