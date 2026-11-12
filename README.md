# H2RES data preparation

Download public energy data and prepare inputs for the original workbook-based H2RES model and the newer bus-based H2RES-refactored model. This application prepares data; the optimization model runs separately.

## Start on Windows

For a complete ready-to-copy installation, use the **attached portable ZIP in [Releases](https://github.com/h2res8Herc/h2res-data-preparation/releases)**. It includes the complete hydro input and offline Python 3.12 dependency wheels. The current **Code → Download ZIP** source also includes all required local data: setup reconstructs the hydro archive from verified local parts. Source downloads install Python dependencies online.

1. Install 64-bit Python 3.12 with Tcl/Tk. Compatible Python 3.10+ and Anaconda installations are also supported.
2. Run `SETUP_WINDOWS.bat` to create the project's Python environment.
3. Run `START_DATA_PREPARATION.bat`.
4. Select countries, spatial resolution, sectors and scenario assumptions.
5. On **Output format**, enable **Also export H2RES-refactored CSV case** to produce both formats. Leave it unchecked for the original format only.
6. Click **Source and prepare data**. Choose **export existing outputs** to reuse previously prepared sector results.

Outputs are written to `data/` (original workbooks) and, when enabled, `data_refactored/` (CSV case), with separate archives. They are runtime outputs and are not committed to this repository.

Weather request estimates start at zero for each new preparation run. Wind/solar and heating jobs within that run share the count, and existing weather caches are reused. Minute/hour estimates pace bursts; day/month estimates do not create long local pauses. If Open-Meteo returns HTTP 429, acquisition keeps retrying until success or Stop, honoring Retry-After or using a gradually increasing delay capped at 15 minutes when no reset hint is supplied. This resets the local estimate, not the provider's counters.

The refactored electricity export reuses the original ENTSO-E hourly curves and normalized JRC regional demand shares. Its totals account for electricity represented explicitly in other sectors. The refactored model's industrial-service and prescribed fleet-pathway adaptations are documented in the export report.

## Download or clone source

Download and extract **Code → Download ZIP**, or clone the repository:

```powershell
git clone https://github.com/h2res8Herc/h2res-data-preparation.git
cd h2res-data-preparation
```

Run `SETUP_WINDOWS.bat`. The 107,182,326-byte hydro archive is stored in ordinary Git parts, each below GitHub's file-size limit, in `power/hydro/precomputed/runoff_shapes_2020.npz.parts`. Setup validates each part and the combined SHA-256 before creating the original NPZ atomically. Git LFS is not required for the current source tree. Keep the parts directory when copying a source download.

Older source ZIPs may contain a 134-byte Git LFS pointer for the NPZ. For an existing installation, copy the actual `power/hydro/precomputed/runoff_shapes_2020.npz` from the complete portable ZIP into the same location and rerun setup. Alternatively download the current source ZIP with its parts. Previously downloaded observations can be reused. The hydro data does not require enabling pickle loading.

The repository includes the required local reference data. Source observations that are not bundled are downloaded during preparation. The source checkout installs Python dependencies from the internet; dependency wheels and the complete offline installer are provided in the repository's Releases when available. Download the attached portable ZIP for copying to another machine.

API tokens are entered locally or supplied through environment variables. Do not commit tokens, `.env` files, saved GUI settings or completed datasets. `.gitignore` excludes the standard runtime folders and local settings.

## Expanded model manual — 12 November 2026

The **150-page H2RES model manual** documents the separate `H2RES_12.11.2026` optimization model, with **62 source-linked equations**, **378 unique settings explained**, 32 illustrated source/data views, complete workflow/dependency guidance and 60 bibliography entries. It covers the sector representations, e-fuels, capture and process-carbon accounting, networks/terminals, DSM, industrial/electricity CBAM, planning/dispatch modes, solver acceptance and resume behavior. Author-reported tests are distinguished from static source inspection.

* [Model manual PDF](docs/H2RES_USER_MANUAL.pdf)
* [Configuration recipes and dependencies](docs/MAIN_CONFIGURATION_GUIDE.md)
* [Equations rendered on GitHub](docs/MATHEMATICAL_FORMULATION_GITHUB.md)
* [Complete option reference](docs/MODEL_OPTION_REFERENCE.md)
* [Offline HTML source](docs/H2RES_USER_MANUAL.html) — download the documentation ZIP from [Releases](https://github.com/h2res8Herc/h2res-data-preparation/releases/tag/v2026.11.12) for local browsing with all images and equations.

The expanded PDF and standalone documentation ZIP are attached to the release. Existing application installer assets retain their original program contents; the expanded manual is available separately. This documentation update does not change preparation calculations or run the optimization model.

## Documentation

* [User guide](USER_GUIDE.md)
* [Illustrated transfer and GUI guide](docs/PORTABLE_USER_GUIDE.md)
* [Refactored export, units and model differences](docs/REFACTORED_EXPORT.md)
* [Native H2RES input layout](docs/MODEL_DATA_2_11_2026.md)
* [Spatial allocation methods and data references](docs/PAPER_METHOD_AUDIT.md)
* [Custom-zone examples and support limits](docs/CUSTOM_ZONES.md)
* [Technical documentation](TECHNICAL_DOCUMENTATION.md)
* [Complete documentation index](docs/README.md)

The exporter validates input coverage, calendars, unit/bus references and financial keys. Optional checks exercise the separate model's reader and sector data preparation. These checks do not solve the optimization or certify scenario feasibility.

## Development

After installing the dependencies, run:

```powershell
python -m unittest discover -s tests -q
```

Commit source changes from this checkout. Publish complete portable ZIPs as GitHub Release assets rather than adding generated archives, environments or source-download caches to Git history.
