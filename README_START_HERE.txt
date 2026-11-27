H2RES DATA PREPARATION — 27 November 2026

Extract the complete folder to a writable directory. Run SETUP_WINDOWS.bat,
then START_DATA_PREPARATION.bat. Python 3.12 x64 with Tcl/Tk is recommended.
The portable package includes offline Python 3.12 dependency wheels, but no
Python interpreter. GitHub source installations obtain dependencies online.

For the new regional curves select Power & profiles > Regional electricity
profiles > sector-weighted, and Output format > Data task > generate.
The national-scaled method remains the default. Both preserve ENTSO-E national
hourly load and JRC annual regional ratios. Sector-weighted uses public economy
and tourism observations plus the bundled representative-profile library.

Choose the original workbook export, optional refactored CSV export, or both.
To reuse complete prepared sector files choose export existing outputs. To
change curve method or create missing profiles choose generate. Keep the same
cache folder and leave Refresh unchecked to reuse observations.

Open docs/PORTABLE_USER_GUIDE.html and docs/PREPARATION_RELEASE_2026_11_17.md.
CHECK_PACKAGE.bat checks inventory, required references and dependencies.
The optimization model is a separate installation. No prepared country output,
personal configuration, API credentials or virtual environment is included.

Transport uses separate domestic and international airport passenger counts. Choose Generate with Transport selected to recalculate existing regional outputs. The 2020 airport weights are included for offline use.
