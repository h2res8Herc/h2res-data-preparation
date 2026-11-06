#!/usr/bin/env python3
"""Standalone internet data sourcing and input preparation interface.

The historical module name remains compatible with existing configurations.
This frontend executes only generate_all_sector_inputs.py.
"""

from __future__ import annotations

import json
import argparse
import os
import queue
import csv
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, filedialog, messagebox
from tkinter import scrolledtext, ttk

from preparation_options import skip_vre_for_config


ROOT = Path(__file__).resolve().parent
DEFAULT_TEMPLATE_DIRECTORY = ROOT / "model_reference_2_11_2026"
RUNNER = ROOT / "generate_all_sector_inputs.py"
CONFIG_FILE = ROOT / "data_preparation_config.json"
LEGACY_CONFIG_FILE = ROOT / "h2res_gui_config.json"
APP_TITLE = "Energy Data Sourcing and Preparation"
SECTORS = ("power", "industry", "transport", "heating")
AVAILABLE_COUNTRIES = (
    "ALL", "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES", "FI",
    "FR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL",
    "PT", "RO", "SE", "SI", "SK",
)


def build_command(config: dict, python_executable: str | None = None) -> list[str]:
    """Translate a validated GUI configuration into runner arguments."""
    countries = ",".join(x.strip().upper() for x in config["countries"].split(",") if x.strip())
    sectors = ",".join(x for x in SECTORS if config.get(f"sector_{x}", False))
    if countries in {"", "ALL"} and config["spatial_level"] == "custom" and config.get("zone_map"):
        with open(config["zone_map"], encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            country_column = next(
                (name for name in ("country", "System", "system", "CNTR_CODE") if name in (reader.fieldnames or [])),
                None,
            )
            if country_column:
                countries = ",".join(dict.fromkeys(
                    row[country_column].strip().upper()
                    for row in reader if row.get(country_column, "").strip()
                ))
    if not countries:
        raise ValueError(
            "Enter at least one ISO2 country code, or select a custom map whose country column can supply them."
        )
    if not sectors:
        raise ValueError("Select at least one sector.")

    cmd = [
        python_executable or sys.executable, str(RUNNER),
        "--countries", countries,
        "--sectors", sectors,
        "--spatial-level", config["spatial_level"],
        "--out-root", config["out_root"],
        "--data-root", config["data_root"],
    ]
    if config["spatial_level"] == "custom":
        if not config.get("zone_map"):
            raise ValueError("Select a custom zone-map CSV.")
        cmd += ["--zone-map", config["zone_map"]]
    if config.get("refresh_sources"):
        cmd.append("--refresh-sources")
    cmd.append("--efuels" if config.get("efuels") else "--no-efuels")
    preset = config.get("scenario_preset", "reference")
    if preset != "reference":
        cmd += ["--scenario-preset", preset, "--scenario-scope", config.get("scenario_scope", "all-energy")]
        if preset == "res100":
            cmd += ["--renewable-target-year", str(config.get("renewable_target_year", "2050"))]
    if config.get("scenario_config"):
        cmd += ["--scenario-config", config["scenario_config"]]
    if config.get("planning_years"):
        cmd += ["--planning-years", config["planning_years"]]
    if config.get("renewable_start_share"):
        cmd += ["--renewable-start-share", str(config["renewable_start_share"])]
    if str(config.get("investment_multiplier", "1")) not in {"1", "1.0", ""}:
        cmd += ["--investment-multiplier", str(config["investment_multiplier"])]
    if preset == "res100" and config.get("scenario_scope", "all-energy") == "all-energy" and not config.get("efuels"):
        raise ValueError("Whole-energy RES requires the e-fuels option on the General tab.")
    cmd += ["--industry-mode", config.get("industry_mode", "categories"),
            "--industry-electricity-case", config.get("industry_electricity_case", "conservative")]
    if config.get("sector_industry"):
        cmd += ["--industry-base-year", str(config.get("industry_base_year", "2020")),
                "--industry-regional-allocation", config.get("industry_regional_allocation", "require-weights"),
                "--industry-waste-allocation", config.get("industry_waste_allocation", "sector-blend"),
                "--complex-industry-sectors", config.get("complex_industry_sectors", "all")]
        for key, flag in [("industry_source_root", "--industry-source-root"), ("industry_zone_weights", "--industry-zone-weights")]:
            if config.get(key):
                cmd += [flag, config[key]]
        if not config.get("industry_download", True):
            cmd.append("--no-industry-download")
    if config.get("model_root"):
        cmd += ["--model-root", config["model_root"]]
    if config.get("model_reference"):
        templates = Path(config["model_reference"])
        if templates.resolve() == (ROOT / "model_reference").resolve():
            templates = DEFAULT_TEMPLATE_DIRECTORY
        cmd += ["--model-reference", str(templates)]
    cmd.append("--model-export" if config.get("model_export", True) else "--no-model-export")
    if config.get('refactored_export'):
        if not config.get('model_export',True):
            raise ValueError('The refactored CSV export needs the prepared native model export enabled.')
        cmd.append('--refactored-export')
        if config.get('refactored_model_root'):
            cmd += ['--refactored-model-root',config['refactored_model_root']]
    cmd.append("--model-ready-package" if config.get("model_export", True) and config.get("model_ready_package", True)
               else "--no-model-ready-package")
    cmd.append("--all-model-variants" if config.get("all_model_variants", True) else "--no-all-model-variants")
    if config.get("require_model_ready", True) or (config.get("model_export", True) and config.get("model_ready_package", True)):
        cmd.append("--require-model-ready")
    if config.get("input_action", "generate") == "import model inputs":
        cmd.append("--import-model-inputs")
    elif config.get("input_action") == "export existing outputs":
        cmd.append("--export-only")

    if config.get("sector_power"):
        cmd += [
            "--power-output-level", config["power_output_level"],
            "--hydro-output-level", config["hydro_output_level"],
            "--hydro-year", config["hydro_year"],
            "--vre-year", config["vre_year"],
        ]
        if config.get("skip_hydro"):
            cmd.append("--skip-hydro-profiles")
        if skip_vre_for_config(config):
            cmd.append("--skip-vre-profiles")
        else:
            cmd += ["--vre-weather-source", config["vre_weather_source"]]
            cmd.append("--vre-calibrate" if config.get("vre_calibrate") else "--no-vre-calibrate")
            if config.get("vre_irena_year"):
                cmd += ["--vre-irena-year", config["vre_irena_year"]]
            if config.get("irena_xlsx"):
                cmd += ["--irena-xlsx", config["irena_xlsx"]]
        cmd += ["--electricity-demand-year", config["electricity_demand_year"]]
        if config.get("skip_electricity_demand"):
            cmd.append("--skip-electricity-demand")

    if config.get("sector_heating"):
        cmd += ["--temperature-source", config["temperature_source"]]
        if config.get("era5"):
            cmd += ["--era5", config["era5"]]
        if config.get("population_tif"):
            cmd += ["--population-tif", config["population_tif"]]
        if config.get("skip_heating_raw"):
            cmd.append("--skip-heating-raw")
    return [str(x) for x in cmd]


def command_text(command: list[str]) -> str:
    return subprocess.list2cmdline(command)


def missing_source_tokens(config: dict, environment: dict) -> list[str]:
    """Repackaging existing files needs no provider credentials."""
    if config.get("input_action", "generate") != "generate" or not config.get("sector_power"):
        return []
    messages = []
    if config.get("vre_weather_source") == "renewables-ninja" and not skip_vre_for_config(config) and not environment.get("RENEWABLES_NINJA_TOKEN"):
        messages.append("Set RENEWABLES_NINJA_TOKEN before using Renewables.ninja.")
    if not config.get("skip_electricity_demand") and not (str(config.get("entsoe_token", "")).strip() or environment.get("ENTSOE_API_TOKEN") or environment.get("ENTSOE_TOKEN")):
        messages.append("Enter an ENTSO-E API token or select Skip electricity-demand profiles.")
    return messages


class DataPreparationGui:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1020x760")
        self.root.minsize(850, 650)
        self.process: subprocess.Popen | None = None
        self.messages: queue.Queue = queue.Queue()
        self.vars: dict[str, StringVar | BooleanVar] = {}
        self._make_vars()
        self._build()
        self.load_config(silent=True)
        self.refresh_preview()
        self.root.after(100, self._drain_messages)

    def _make_vars(self) -> None:
        defaults = {
            "countries": "HR", "spatial_level": "nuts3", "zone_map": "",
            "out_root": str(ROOT / "outputs_all"), "data_root": str(ROOT / "data_all"),
            "power_output_level": "aggregated", "hydro_output_level": "match-power",
            "hydro_year": "2020", "vre_year": "2020", "vre_irena_year": "",
            "electricity_demand_year": "2020", "entsoe_token": "",
            "vre_weather_source": "openmeteo", "temperature_source": "open-meteo",
            "era5": "", "population_tif": "",
            "industry_mode": "categories", "industry_electricity_case": "conservative",
            "industry_source_root": "", "industry_zone_weights": "", "industry_base_year": "2020",
            "industry_regional_allocation": "require-weights", "complex_industry_sectors": "all",
            "industry_waste_allocation": "sector-blend",
            "model_root": "", "model_reference": str(DEFAULT_TEMPLATE_DIRECTORY), "refactored_model_root": "",
            "input_action": "generate",
            "scenario_preset": "reference", "scenario_scope": "all-energy", "planning_years": "",
            "renewable_target_year": "2050", "renewable_start_share": "", "investment_multiplier": "1",
            "scenario_config": "",
            "irena_xlsx": str(ROOT / "power" / "VRES_distributions" / "IRENA_Statistics_Extract_2025H2.xlsx"),
        }
        flags = {
            "sector_power": True, "sector_industry": True, "sector_transport": True,
            "sector_heating": True, "efuels": False, "refresh_sources": False,
            "skip_hydro": False, "skip_vre": False, "vre_calibrate": True,
            "skip_electricity_demand": False,
            "skip_heating_raw": False,
            "model_export": True, "require_model_ready": True, "model_ready_package": True, "all_model_variants": True,
            "refactored_export": False,
            "industry_download": True,
        }
        for key, value in defaults.items():
            self.vars[key] = StringVar(value=value)
        for key, value in flags.items():
            self.vars[key] = BooleanVar(value=value)
        def ensure_renewable_fuel_paths(*_):
            if self.vars["scenario_preset"].get() == "res100" and self.vars["scenario_scope"].get() == "all-energy":
                self.vars["efuels"].set(True)
        self.vars["scenario_preset"].trace_add("write", ensure_renewable_fuel_paths)
        self.vars["scenario_scope"].trace_add("write", ensure_renewable_fuel_paths)
        for var in self.vars.values():
            var.trace_add("write", lambda *_: self.refresh_preview())

    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text=APP_TITLE, font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(outer, text="Download public source data, prepare sector tables and hourly profiles, and export input files.").pack(anchor="w", pady=(0, 8))

        notebook = ttk.Notebook(outer)
        self.notebook = notebook
        notebook.pack(fill="both", expand=True)
        general = ttk.Frame(notebook, padding=12)
        power = ttk.Frame(notebook, padding=12)
        heating = ttk.Frame(notebook, padding=12)
        model = ttk.Frame(notebook, padding=12)
        industry = ttk.Frame(notebook, padding=12)
        scenario = ttk.Frame(notebook, padding=12)
        help_tab = ttk.Frame(notebook, padding=12)
        notebook.add(general, text="General")
        notebook.add(power, text="Power & profiles")
        notebook.add(heating, text="Heating & advanced")
        notebook.add(model, text="Output format")
        notebook.add(industry, text="Industry sources")
        notebook.add(scenario, text="Input assumptions")
        notebook.add(help_tab, text="Help & documentation")
        self._build_general(general)
        self._build_power(power)
        self._build_heating(heating)
        self._build_model(model)
        self._build_industry(industry)
        self._build_scenario(scenario)
        self._build_help(help_tab)

        preview_box = ttk.LabelFrame(outer, text="Command preview", padding=6)
        preview_box.pack(fill="x", pady=(8, 4))
        self.preview = scrolledtext.ScrolledText(preview_box, height=3, wrap="word", font=("Consolas", 9))
        self.preview.pack(fill="x")
        self.preview.configure(state="disabled")

        log_box = ttk.LabelFrame(outer, text="Run log", padding=6)
        log_box.pack(fill="both", expand=True, pady=(4, 6))
        self.log = scrolledtext.ScrolledText(log_box, height=10, wrap="word", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True)

        buttons = ttk.Frame(outer)
        # Reserve the action row before expandable content takes the height.
        buttons.pack(side="bottom", fill="x", before=notebook)
        ttk.Button(buttons, text="Save settings", command=self.save_config).pack(side="left")
        ttk.Button(buttons, text="Load settings", command=self.load_config).pack(side="left", padx=5)
        ttk.Button(buttons, text="Open output folder", command=self.open_output).pack(side="left")
        self.stop_button = ttk.Button(buttons, text="Stop", command=self.stop, state="disabled")
        self.stop_button.pack(side="right")
        self.run_button = ttk.Button(buttons, text="Source and prepare data", command=self.start)
        self.run_button.pack(side="right", padx=5)

    def _row(self, parent, row: int, label: str, key: str, browse: str | None = None) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(parent, textvariable=self.vars[key]).grid(row=row, column=1, sticky="ew", pady=4)
        if browse:
            ttk.Button(parent, text="Browse…", command=lambda: self.browse(key, browse)).grid(row=row, column=2, padx=5)

    def _build_general(self, tab) -> None:
        tab.columnconfigure(1, weight=1)
        ttk.Label(tab, text="Country").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        country_combo = ttk.Combobox(
            tab,
            textvariable=self.vars["countries"],
            values=AVAILABLE_COUNTRIES,
            state="normal",
        )
        country_combo.grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(
            tab,
            text="Select ALL, enter ISO2 codes, or leave blank to use every country in a custom map.",
            foreground="#555",
            wraplength=320,
        ).grid(row=0, column=2, sticky="w", padx=5)
        ttk.Label(tab, text="Sectors").grid(row=1, column=0, sticky="nw", pady=6)
        sector_frame = ttk.Frame(tab)
        sector_frame.grid(row=1, column=1, sticky="w")
        for sector in SECTORS:
            ttk.Checkbutton(sector_frame, text=sector.title(), variable=self.vars[f"sector_{sector}"]).pack(side="left", padx=(0, 12))
        ttk.Label(tab, text="Spatial level").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Combobox(tab, textvariable=self.vars["spatial_level"], values=("nuts3", "nuts2", "nuts1", "country", "custom"), state="readonly").grid(row=2, column=1, sticky="ew")
        self._row(tab, 3, "Custom zone map CSV", "zone_map", "file")
        self._row(tab, 4, "Output directory", "out_root", "directory")
        self._row(tab, 5, "Download/cache directory", "data_root", "directory")
        ttk.Checkbutton(tab, text="Enable e-fuel-compatible transport and industry tables", variable=self.vars["efuels"]).grid(row=6, column=1, sticky="w", pady=4)
        ttk.Checkbutton(tab, text="Refresh downloaded source data", variable=self.vars["refresh_sources"]).grid(row=7, column=1, sticky="w", pady=4)

    def _combo(self, parent, row: int, label: str, key: str, values: tuple[str, ...]) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Combobox(parent, textvariable=self.vars[key], values=values, state="readonly").grid(row=row, column=1, sticky="ew", pady=4)

    def _build_model(self, tab) -> None:
        tab.columnconfigure(1, weight=1)
        self._combo(tab, 0, "Data task", "input_action", ("generate", "export existing outputs"))
        self._combo(tab, 1, "Industry representation", "industry_mode", ("regular", "categories", "complex"))
        self._combo(tab, 2, "Industry electricity assumptions", "industry_electricity_case", ("conservative", "technical_2050"))
        self._row(tab, 3, "Portable format and technology templates", "model_reference", "directory")
        ttk.Checkbutton(tab, text="Package prepared data in H2RES input format", variable=self.vars["model_export"]).grid(row=4, column=1, sticky="w", pady=4)
        ttk.Checkbutton(tab, text="Also create an input archive and validation package", variable=self.vars["model_ready_package"]).grid(row=5, column=1, sticky="w", pady=4)
        ttk.Checkbutton(tab, text="Require complete coverage for unbundled exports", variable=self.vars["require_model_ready"]).grid(row=6, column=1, sticky="w", pady=4)
        ttk.Checkbutton(tab, text="Generate all native flex_tech and industry variants", variable=self.vars["all_model_variants"]).grid(row=7, column=1, sticky="w", pady=4)
        ttk.Button(tab, text="Open H2RES data folder", command=self.open_model_inputs).grid(row=8, column=1, sticky="w", pady=4)
        ttk.Checkbutton(tab,text='Also export H2RES-refactored CSV case (data_refactored)',variable=self.vars['refactored_export']).grid(row=9,column=1,sticky='w',pady=4)
        ttk.Label(tab, text=("Generate downloads missing internet sources or reuses cached observations, then prepares the selected sectors. "
                            "Export existing outputs only repackages previously prepared data. Portable templates supply the required "
                            "file structure and editable technology assumptions. The ready-to-use folder is <Output directory>/data. "
                            "The optional refactored CSV case is written to data_refactored with its own ZIP and export report. "
                            "Its industry services and fixed fleet pathway follow that model's equations. "
                            "See docs/REFACTORED_EXPORT.html for use and representation differences."),
                  wraplength=650).grid(row=10, column=0, columnspan=3, sticky="w", pady=8)

    def _build_industry(self, tab) -> None:
        tab.columnconfigure(1, weight=1)
        self._row(tab, 0, "Complex JRC source folder (optional)", "industry_source_root", "directory")
        self._row(tab, 1, "Industry reference year", "industry_base_year")
        self._row(tab, 2, "Complex regional weights CSV", "industry_zone_weights", "file")
        self._combo(tab, 3, "Regional allocation method", "industry_regional_allocation", ("require-weights", "equal"))
        self._row(tab, 4, "Complex sectors (all or Industry labels)", "complex_industry_sectors")
        ttk.Checkbutton(tab, text="Download missing public industry sources", variable=self.vars["industry_download"]).grid(row=5, column=1, sticky="w", pady=4)
        self._combo(tab, 6, "Mixed waste split", "industry_waste_allocation", ("sector-blend", "strict"))
        ttk.Label(tab, text=("The year, allocation method and download control also apply to regular/category industry. "
                            "Regional generation uses ETS/IED/EIGL facility evidence; automatic complex variants reuse those branch shares. "
                            "Custom complex-only runs can supply explicit weights. Equal allocation and sector-blend waste splits are recorded assumptions."),
                  wraplength=650).grid(row=7, column=0, columnspan=3, sticky="w", pady=12)

    def _build_scenario(self, tab) -> None:
        tab.columnconfigure(1, weight=1)
        self._combo(tab, 0, "Preset", "scenario_preset", ("reference", "res100"))
        self._combo(tab, 1, "Renewable target scope", "scenario_scope", ("all-energy", "electricity"))
        self._row(tab, 2, "Planning years (blank = reference)", "planning_years")
        ttk.Label(tab, text="Example: 2025,2030,2035,2040,2045,2050", foreground="#555").grid(row=3, column=1, sticky="w")
        self._row(tab, 4, "100% renewable target year", "renewable_target_year")
        self._row(tab, 5, "Starting electricity RES share (optional, 0–1)", "renewable_start_share")
        self._row(tab, 6, "Annual investment limit multiplier", "investment_multiplier")
        self._row(tab, 7, "Scenario JSON overrides (optional)", "scenario_config", "file")
        ttk.Label(tab, text=("These choices prepare future-year input tables and policy assumptions. reference retains supplied assumptions; "
                            "res100 records the renewable target for the selected year and enables e-fuel-compatible inputs. "
                            "A multiplier of 1 retains annual build limits; 0 sets finite limits to zero. Blank limits remain unrestricted. "
                            "Sourced historical observations stay separate from these assumptions."), wraplength=700).grid(row=8, column=0, columnspan=3, sticky="w", pady=12)

    def _build_power(self, tab) -> None:
        tab.columnconfigure(1, weight=1)
        self._combo(tab, 0, "GENCO resolution", "power_output_level", ("aggregated", "individual", "both"))
        self._combo(tab, 1, "Hydro profile resolution", "hydro_output_level", ("match-power", "aggregated", "individual", "both"))
        self._row(tab, 2, "Hydro profile year", "hydro_year")
        ttk.Checkbutton(tab, text="Skip hydro profiles", variable=self.vars["skip_hydro"]).grid(row=3, column=1, sticky="w")
        ttk.Separator(tab).grid(row=4, column=0, columnspan=3, sticky="ew", pady=10)
        self._row(tab, 5, "Wind/solar weather year", "vre_year")
        self._combo(tab, 6, "Wind/solar source", "vre_weather_source", ("openmeteo", "renewables-ninja"))
        self._row(tab, 7, "IRENA calibration year (optional)", "vre_irena_year")
        self._row(tab, 8, "IRENA workbook", "irena_xlsx", "file")
        ttk.Checkbutton(tab, text="Calibrate annual capacity factors to IRENA", variable=self.vars["vre_calibrate"]).grid(row=9, column=1, sticky="w")
        ttk.Checkbutton(tab, text="Skip wind and solar profiles (source-only / diagnostic exports)", variable=self.vars["skip_vre"]).grid(row=10, column=1, sticky="w")
        ttk.Label(tab, text="Renewables.ninja reads the RENEWABLES_NINJA_TOKEN environment variable.", foreground="#555").grid(row=11, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Separator(tab).grid(row=12, column=0, columnspan=3, sticky="ew", pady=10)
        self._row(tab, 13, "Electricity-demand year", "electricity_demand_year")
        ttk.Label(tab, text="ENTSO-E API token").grid(row=14, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(tab, textvariable=self.vars["entsoe_token"], show="*").grid(row=14, column=1, sticky="ew", pady=4)
        ttk.Checkbutton(tab, text="Skip electricity-demand profiles", variable=self.vars["skip_electricity_demand"]).grid(row=15, column=1, sticky="w")
        ttk.Label(tab, text="The token is used only for this run and is not saved in settings.", foreground="#555").grid(row=16, column=0, columnspan=3, sticky="w", pady=(5, 0))
        ttk.Label(tab, text="Complete H2RES exports always generate wind/solar profiles and reuse cached weather.", foreground="#555").grid(row=17, column=0, columnspan=3, sticky="w", pady=(5, 0))

    def _build_heating(self, tab) -> None:
        tab.columnconfigure(1, weight=1)
        self._combo(tab, 0, "Temperature source", "temperature_source", ("open-meteo", "cds-netcdf"))
        self._row(tab, 1, "Existing ERA5 NetCDF (optional)", "era5", "file")
        self._row(tab, 2, "Population raster (optional)", "population_tif", "file")
        ttk.Checkbutton(tab, text="Reuse existing raw heating files", variable=self.vars["skip_heating_raw"]).grid(row=3, column=1, sticky="w", pady=4)
        ttk.Label(tab, text="Defaults use packaged population data and download/cache public temperature data.", foreground="#555").grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))

    def _build_help(self, tab) -> None:
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        buttons = ttk.Frame(tab)
        buttons.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(
            buttons, text="Open user guide",
            command=lambda: self.open_document(
                ROOT / "docs/PORTABLE_USER_GUIDE.html" if (ROOT / "docs/PORTABLE_USER_GUIDE.html").exists()
                else ROOT / "USER_GUIDE.md"),
        ).pack(side="left")
        ttk.Button(
            buttons, text="Open technical documentation",
            command=lambda: self.open_document(
                ROOT / "docs/PAPER_METHOD_AUDIT.html" if (ROOT / "docs/PAPER_METHOD_AUDIT.html").exists()
                else ROOT / "TECHNICAL_DOCUMENTATION.md"),
        ).pack(side="left", padx=6)
        ttk.Button(
            buttons, text="Open package README",
            command=lambda: self.open_document(ROOT / "README_PORTABLE_INPUT_GENERATOR.txt"),
        ).pack(side="left")

        help_text = """QUICK START

1. Select a country from the drop-down list. For a multi-country run, type
   two-letter codes separated by commas, for example HR,SI.
2. Select the sectors to generate.
3. Choose the spatial level. NUTS3 is the most detailed default.
4. For power, choose aggregated, individual, or both.
5. Keep Hydro profile resolution at match-power unless you need a different output.
6. Keep wind/solar, hydro and electricity demand enabled for complete inputs.
7. Review the command preview and click Source and prepare data.

PURPOSE

This application sources and prepares data only. It writes CSV/Excel files,
hourly profiles, source records and input coverage reports. Run H2RES separately
in its own installation when you want to use the exported data.

ELECTRICITY DEMAND

Enter your ENTSO-E Transparency Platform API token and choose any available
demand year. The token is used only by the running process and is not saved.
Monthly responses are cached, while packaged normalized NUTS3 distributions
allocate each national hourly curve to the selected model zones.

INDUSTRY VARIANTS

Regular/category runs write regular and e-fuel-compatible technology tables.
Complex industry compiles the selected native workbook from country JRC data.
Regional regular/category runs download sector-filtered ETS, IED and EIGL
facility evidence. All native variants share the resulting branch geography.
Missing branch coverage uses documented industrial-site-density assumptions.
Custom complex-only allocations can use supplied weights or explicit equal shares.

POWER RESOLUTION

Aggregated creates one compatible unit per model zone, fuel and technology.
Individual preserves one row and profile per physical plant.
Both writes the aggregated model table plus supplementary individual files.

HYDRO

HDAM and HPHS profiles are in ScaledInflows files. HROR profiles are in
AvailabilityFactors_HROR files. Missing-capacity plants are excluded and HPHS
without natural inflow is treated as closed-loop.

WIND AND SOLAR

Open-Meteo is the key-free default. Requests are cached and can be resumed.
IRENA calibration adjusts annual national capacity factors while retaining the
hourly and regional profile. Renewables.ninja requires the environment variable
RENEWABLES_NINJA_TOKEN before starting this application.

OUTPUTS

The output directory contains power, industry, transport and heating folders.
The combined native files are in <output directory>/data, using the model's
43 native filenames and subdirectory layout. All seven flex_tech paths and
four complex-industry companions are updated when all variants is enabled.
Reports and the additional model_inputs/h2res_inputs delivery remain outside data.
model_inputs/h2res_inputs/H2RES_model_inputs.zip contains the same delivery.
Read its README and validation.json for readiness and sector provenance.
Mapping and quality-report CSV files explain how source units were transformed.
Use Open output folder after a successful run.

COMMON PROBLEMS

• No sectors selected: select at least one sector on the General tab.
• Custom spatial level: provide a CSV with country,nuts3,zone columns.
• Weather/API interruption: run again; completed requests remain cached.
• Partial source-only work: disable complete model export before using skip controls.
• Renewables.ninja token missing: set RENEWABLES_NINJA_TOKEN and restart.
• Detailed methodology: open Technical documentation above.
"""
        text = scrolledtext.ScrolledText(tab, wrap="word", font=("Segoe UI", 10))
        text.grid(row=1, column=0, sticky="nsew")
        text.insert("1.0", help_text)
        text.configure(state="disabled")

    def browse(self, key: str, kind: str) -> None:
        value = filedialog.askdirectory() if kind == "directory" else filedialog.askopenfilename()
        if value:
            self.vars[key].set(value)

    def config(self) -> dict:
        config = {key: var.get() for key, var in self.vars.items()}
        # This frontend is independent of an installed model and prepares files only.
        config["model_root"] = ""
        if config["input_action"] not in {"generate", "export existing outputs"}:
            config["input_action"] = "generate"
        return config

    def refresh_preview(self) -> None:
        if not hasattr(self, "preview"):
            return
        try:
            text = command_text(build_command(self.config()))
        except Exception as exc:
            text = f"Configuration incomplete: {exc}"
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text)
        self.preview.configure(state="disabled")

    def save_config(self) -> None:
        config = self.config()
        config.pop("entsoe_token", None)
        CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")
        messagebox.showinfo(APP_TITLE, f"Settings saved to\n{CONFIG_FILE}")

    def load_config(self, silent: bool = False) -> None:
        selected_config = CONFIG_FILE if CONFIG_FILE.exists() else LEGACY_CONFIG_FILE
        if not selected_config.exists():
            if not silent:
                messagebox.showinfo(APP_TITLE, "No saved settings file exists yet.")
            return
        try:
            data = json.loads(selected_config.read_text(encoding="utf-8"))
            for key, value in data.items():
                if key in self.vars:
                    self.vars[key].set(value)
            self.vars["model_root"].set("")
            if Path(str(self.vars["model_reference"].get())).resolve() == (ROOT / "model_reference").resolve():
                self.vars["model_reference"].set(str(DEFAULT_TEMPLATE_DIRECTORY))
            if self.vars["input_action"].get() not in {"generate", "export existing outputs"}:
                self.vars["input_action"].set("generate")
        except Exception as exc:
            if not silent:
                messagebox.showerror(APP_TITLE, str(exc))

    def start(self) -> None:
        try:
            config = self.config()
            command = build_command(config)
            from preparation_dependencies import dependencies_for_config, require_dependencies
            require_dependencies(dependencies_for_config(config))
            templates = Path(str(self.vars["model_reference"].get()))
            if self.vars["model_export"].get() and not (templates / "manifest.json").is_file():
                raise ValueError("Choose the portable format/technology templates directory on Output format (normally model_reference). A model installation is not needed.")
        except ImportError as exc:
            messagebox.showerror("Preparation dependencies", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return
        token_errors = missing_source_tokens(config, os.environ)
        if token_errors:
            messagebox.showerror("Missing token", "\n".join(token_errors))
            return
        self.log.delete("1.0", "end")
        self.run_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        child_env = os.environ.copy()
        token = self.vars["entsoe_token"].get().strip()
        if token:
            child_env["ENTSOE_API_TOKEN"] = token
        threading.Thread(target=self._run, args=(command, child_env), daemon=True).start()

    def _run(self, command: list[str], child_env: dict[str, str]) -> None:
        self.messages.put(("line", f"> {command_text(command)}\n\n"))
        try:
            self.process = subprocess.Popen(command, cwd=ROOT, env=child_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)
            assert self.process.stdout is not None
            for line in self.process.stdout:
                self.messages.put(("line", line))
            code = self.process.wait()
            self.messages.put(("done", code))
        except Exception as exc:
            self.messages.put(("line", f"ERROR: {exc}\n"))
            self.messages.put(("done", -1))

    def _drain_messages(self) -> None:
        try:
            while True:
                kind, value = self.messages.get_nowait()
                if kind == "line":
                    self.log.insert("end", value)
                    self.log.see("end")
                else:
                    self.process = None
                    self.run_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    title = "Completed" if value == 0 else "Stopped or failed"
                    messagebox.showinfo(APP_TITLE, f"{title} (exit code {value}). See the run log.")
        except queue.Empty:
            pass
        self.root.after(100, self._drain_messages)

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()

    def open_output(self) -> None:
        path = Path(str(self.vars["out_root"].get())).resolve()
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)  # type: ignore[attr-defined]

    def open_model_inputs(self) -> None:
        kind='data_refactored' if self.config().get('refactored_export') else 'data'
        path = Path(str(self.vars["out_root"].get())).resolve() / kind
        if not path.is_dir():
            messagebox.showinfo(APP_TITLE, "Create the H2RES data folder first, using Generate or Export existing outputs on Output format.")
            return
        os.startfile(path)  # type: ignore[attr-defined]

    def open_document(self, path: Path) -> None:
        if not path.exists():
            messagebox.showerror("Missing documentation", f"File not found:\n{path}")
            return
        os.startfile(path)  # type: ignore[attr-defined]


H2RESGui = DataPreparationGui  # Compatibility for the historical class name.


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Source internet energy data and prepare input files; no model execution.")
    parser.add_argument("--check", action="store_true", help="Check Python and preparation dependencies without opening a window")
    parser.add_argument("--smoke-test", action="store_true", help="Create and close the interface while keeping its window hidden")
    args = parser.parse_args(argv)
    if args.check:
        from preparation_dependencies import selected_dependencies, require_dependencies
        require_dependencies(selected_dependencies(["power", "industry", "transport", "heating"]))
        # Catch unsupported syntax or broken method imports before opening the GUI.
        import generate_all_sector_inputs
        import industry.generate_complex_industry_inputs
        print(json.dumps({"application": APP_TITLE, "python": sys.executable, "startup_check_passed": True,
                          "operation": "data sourcing and preparation", "runner": str(RUNNER)}))
        return 0
    root = Tk()
    if args.smoke_test:
        root.withdraw()
    app = DataPreparationGui(root)
    if args.smoke_test:
        root.update_idletasks()
        report = {"application": root.title(), "startup_passed": True,
                  "tabs": [app.notebook.tab(tab, "text") for tab in app.notebook.tabs()],
                  "run_button": app.run_button.cget("text"), "runner": str(RUNNER),
                  "operation": "data sourcing and preparation"}
        print(json.dumps(report))
        root.after(50, root.destroy)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
