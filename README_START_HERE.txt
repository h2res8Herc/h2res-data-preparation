H2RES DATA PREPARATION - WINDOWS TRANSFER PACKAGE
Release: 4 November 2026. Native format: H2RES_2.11.2026_novi.

1. Extract/copy this entire folder to a writable local directory.
2. Python 3.12 (64-bit, Tcl/Tk) is recommended for offline setup. Existing compatible
   Anaconda/Python 3.10+ is also detected; other versions install dependencies online.
3. Run SETUP_WINDOWS.bat once to create this machine's .venv and install dependencies.
4. Run START_DATA_PREPARATION.bat.
5. Open docs/PORTABLE_USER_GUIDE.html or docs/PORTABLE_USER_GUIDE.pdf for the screenshot guide.

The interface sources and prepares data; H2RES optimization uses a separate installation.
The model-format reference and required seed data are included. Large public datasets
download as needed. Standard Python dependencies install from the bundled Windows
wheels with Python 3.12; other compatible versions use online dependencies. An explicit
interpreter can be selected with SETUP_WINDOWS.bat -PythonExe "C:\path\python.exe".
The launcher uses the completed local .venv and does not fall back after setup fails.
Enter your own API credentials. No user settings/tokens/virtual
environment or old machine-specific download caches are included.

Previously generated country outputs and completed input bundles are not included.
Run generate to create your selected country's inputs, then inspect validation.json.
EU27 is the intended coverage; full updated end-to-end verification is for HR.
Missing-sector assumptions and differing source vintages are documented in the guide.

CHECK_PACKAGE.bat verifies this release's file hashes and dependencies after setup.
PACKAGE_MANIFEST.json records all shipped files. The supplied data/source licences
and attribution are documented in docs/REFERENCES.md and docs/PAPER_METHOD_AUDIT.html.

NATIVE INPUT CONTRACT UPDATE - 5 NOVEMBER 2026

The exporter reconciles pooled industry, exact generator financial keys,
regional investment budgets, global outside-system curves and national policy scopes.
Missing regional network links are explicit virtual exchange defaults,
with a report outside the native data folder. Unsupported reference
generation calibration targets are recorded as unapplied with a warning.
Use the generated run_model_scenario.py launcher for the separate model: it
applies selected variants and corrects its legacy regional industry-reader
loop in memory. See docs/MODEL_DATA_2_11_2026.html for commands and assumptions.
This reusable transfer release still contains no generated country outputs.
Custom-zone mapping examples and support limits: docs/CUSTOM_ZONES.html.
Partial-country maps and independent offshore zones are not supported yet.
Windows archive staging uses short sibling paths. Validated recovery folders
can rebuild a missing package without repeating source preparation. See the native data guide.
Each new preparation run starts its local weather estimate at zero; countries and
sectors share that run's counter. Day/month estimates do not impose local waits.
HTTP 429 responses retry until success or Stop, honoring provider reset delays.
Existing weather caches remain reusable; see the user guide.
Optional bus-based H2RES-refactored CSV case export: select it on Output format.
See docs/REFACTORED_EXPORT.html for use, mappings and representation differences.
Refactored electricity retains the older export's hourly curves and JRC shares;
sector energy is removed nationally before regional allocation. Regenerate existing
refactored cases to replace the earlier regional subtraction/clipping method.
