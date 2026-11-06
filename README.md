# H2RES data preparation

Download public energy data and prepare inputs for the original workbook-based H2RES model and the newer bus-based H2RES-refactored model. This application prepares data; the optimization model runs separately.

## Start on Windows

1. Install 64-bit Python 3.12 with Tcl/Tk. Compatible Python 3.10+ and Anaconda installations are also supported.
2. Run `SETUP_WINDOWS.bat` to create the project's Python environment.
3. Run `START_DATA_PREPARATION.bat`.
4. Select countries, spatial resolution, sectors and scenario assumptions.
5. On **Output format**, enable **Also export H2RES-refactored CSV case** to produce both formats. Leave it unchecked for the original format only.
6. Click **Source and prepare data**. Choose **export existing outputs** to reuse previously prepared sector results.

Outputs are written to `data/` (original workbooks) and, when enabled, `data_refactored/` (CSV case), with separate archives. They are runtime outputs and are not committed to this repository.

The refactored electricity export reuses the original ENTSO-E hourly curves and normalized JRC regional demand shares. Its totals account for electricity represented explicitly in other sectors. The refactored model's industrial-service and prescribed fleet-pathway adaptations are documented in the export report.

## Clone with Git LFS

One required hydro input uses Git Large File Storage. Install Git LFS before cloning, or run `git lfs pull` afterward:

```powershell
git lfs install
git clone https://github.com/h2res8Herc/h2res-data-preparation.git
cd h2res-data-preparation
git lfs pull
```

The repository includes the required local reference data. Source observations that are not bundled are downloaded during preparation. The source checkout installs Python dependencies from the internet; dependency wheels and the complete offline installer are provided in the private repository's Releases when available. Download the attached portable ZIP for copying to another machine.

API tokens are entered locally or supplied through environment variables. Do not commit tokens, `.env` files, saved GUI settings or completed datasets. `.gitignore` excludes the standard runtime folders and local settings.

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
