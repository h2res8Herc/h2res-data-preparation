"""Conservation and source/accounting regressions for optional sector profiles."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
from email.message import Message
from unittest.mock import patch

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from power.demand import sector_profiles as profiles
from power.demand import generate_electricity_demand_standalone as demand
from refactored_input_export import CaseExporter, residual_electricity
from h2res_input_gui import build_command
from model_input_bundle import copy_demand_provenance


def observations(year=2020):
    stamps = pd.date_range(f"{year}-01-01", f"{year}-12-31 23:00", freq="h", tz="UTC")
    hour = stamps.hour.to_numpy()
    return pd.Series(1400 + 100 * np.sin(2 * np.pi * hour / 24) + 80 * np.cos(2 * np.pi * np.arange(len(stamps)) / len(stamps)), index=stamps)


class FixtureCache:
    """Deliberately different economic mixes, not artificial metered curves."""
    def __init__(self, *args, **kwargs):
        self.sources, self.warnings = [], []
        self.tables = {}
        self.regions = ["HR050", "HR035", "HR028"]
        records = []
        for region, levels in zip(self.regions, ([10, 10, 10, 70, 40, 20, 20, 50, 80, 30],
                                                  [10, 20, 10, 70, 10, 10, 10, 20, 10, 30],
                                                  [70, 300, 10, 10, 5, 5, 5, 5, 10, 5])):
            for code, value in zip(["A", "B-E", "F", *profiles.SERVICES], levels):
                records.append(dict(geo=region, nace_r2=code, value=float(value)))
        economy = pd.DataFrame(records)
        totals = economy.groupby("nace_r2", as_index=False).value.sum().assign(geo="HR")
        economy = pd.concat([economy, totals], ignore_index=True)
        self.tables["nama_10r_3empers"] = economy
        self.tables["nama_10r_3gva"] = economy.assign(value=economy.value * 2)
        self.tables["demo_r_pjanaggr3"] = pd.DataFrame(dict(geo=self.regions, value=[800000., 450000., 160000.]))
        self.tables["nrg_bal_c"] = pd.DataFrame(dict(nrg_bal=["FC_E", "FC_IND_E", "FC_OTH_CP_E", "FC_OTH_HH_E", "FC_OTH_AF_E", "FC_OTH_FISH_E"],
                                                    value=[1000., 350., 300., 300., 20., 0.]))
        self.tables["tour_occ_nin3"] = pd.DataFrame(dict(geo=self.regions, value=[200000., 3000000., 10000.]))
        self.tables["tour_occ_nin2m"] = pd.DataFrame([dict(geo=region, month=f"M{month:02d}", value=(10. if month in (6, 7, 8) else 1.))
                                                    for region in ["HR03", "HR"] for month in range(1, 13)])

    def table(self, dataset, year, **filters):
        return self.tables[dataset]

    optional_table = table

    def get(self, name, url):
        return [dict(date="2020-01-01", **{"global": True}, types=["Public"])]


class BalancingTests(unittest.TestCase):
    def test_both_margins_and_true_zero_support(self):
        prior = np.array([[8., 1., 7.], [2., 7., 4.], [1., 1., 9.]])
        final, _ = profiles.balance(prior, [12., 18., 0.], [20., 10., 0.])
        np.testing.assert_allclose(final.sum(axis=1), [12., 18., 0.], atol=1e-9)
        np.testing.assert_allclose(final.sum(axis=0), [20., 10., 0.], atol=1e-9)
        self.assertTrue((final[-1] == 0).all())
        self.assertTrue((final[:, -1] == 0).all())

    def test_invalid_or_infeasible_targets_are_rejected(self):
        for prior, hourly, annual in (([[1., 1.]], [2.], [1., 2.]),
                                      ([[0., 1.]], [2.], [1., 1.]),
                                      ([[np.nan, 1.]], [2.], [1., 1.]),
                                      ([[1., 1.]], [-2.], [-1., -1.])):
            with self.assertRaises(ValueError):
                profiles.balance(prior, hourly, annual)
        with self.assertRaisesRegex(ValueError, "did not converge"):
            profiles.balance([[1., 0.], [0., 1.]], [1., 3.], [2., 2.], max_iterations=8)

    def test_leap_year_preserves_full_and_model_annual_budgets(self):
        load = observations()
        weights = pd.Series([.4, .35, .25], index=["HR050", "HR035", "HR028"])
        cache = FixtureCache()
        budgets, mix, _ = profiles.composition("HR", 2020, weights, cache, .1)
        shapes, _ = profiles.construct_shapes("HR", load, list(weights.index), mix, cache, .1)
        result, reports = profiles.reconcile_profiles(load, weights, pd.DataFrame(budgets, index=weights.index), shapes)
        model = ~((load.index.month == 2) & (load.index.day == 29))
        for mask in (np.ones(len(load), dtype=bool), model, ~model):
            np.testing.assert_allclose(result[mask].sum(axis=1), load.to_numpy()[mask], rtol=1e-10, atol=1e-7)
            np.testing.assert_allclose(result[mask].sum(axis=0), weights.to_numpy() * load.to_numpy()[mask].sum(), rtol=1e-10, atol=1e-6)
        self.assertEqual(set(reports), {"model_8760", "february_29"})
        normalized = result / result.sum(axis=0)
        self.assertGreater(float(np.abs(normalized[:, 0] - normalized[:, 2]).max()), 1e-5)
        residual, _ = residual_electricity(pd.DataFrame(result), pd.DataFrame(result * .2), {0: "HR", 1: "HR", 2: "HR"})
        np.testing.assert_allclose(residual, result * .8)
        np.testing.assert_allclose(residual.div(residual.sum()), normalized)


class SourceAndCompositionTests(unittest.TestCase):
    def test_public_source_rate_limit_retries_then_reuses_cache(self):
        headers = Message()
        headers["Retry-After"] = "1"
        rejected = urllib.error.HTTPError("https://example.test", 429, "rate limited", headers, None)
        with tempfile.TemporaryDirectory() as folder:
            cache = profiles.SourceCache(folder)
            with patch.object(profiles.urllib.request, "urlopen", side_effect=[rejected, io.BytesIO(b'{"value":{}}')]) as fetch, patch.object(profiles.time, "sleep") as sleep:
                first = cache.get("fixture", "https://example.test")
                second = cache.get("fixture", "https://example.test")
            self.assertEqual(first, second)
            self.assertEqual(fetch.call_count, 2)
            sleep.assert_called_once_with(1.)
            self.assertEqual(len(list(Path(folder).glob("*.part"))), 0)
            self.assertEqual(cache.sources[0]["sha256"], cache.sources[1]["sha256"])

    def test_sparse_jsonstat_and_real_zeros(self):
        data = dict(id=["nace_r2", "geo"], size=[2, 2], dimension={
            "nace_r2": dict(category=dict(index={"B-E": 1, "A": 0})),
            "geo": dict(category=dict(index={"HR050": 0, "HR035": 1}))}, value={"0": 0, "3": 25})
        decoded = profiles.decode_jsonstat(data)
        self.assertEqual(len(decoded), 2)
        self.assertEqual(decoded.iloc[0].value, 0)
        self.assertEqual(decoded.iloc[1].nace_r2, "B-E")
        self.assertEqual(decoded.iloc[1].geo, "HR035")

    def test_sector_energy_not_gva_shares_and_tourism_is_subdivision(self):
        cache = FixtureCache()
        weights = pd.Series([.4, .35, .25], index=cache.regions)
        budgets, _, report = profiles.composition("HR", 2020, weights, cache, .1)
        np.testing.assert_allclose(budgets.sum(axis=1), weights, atol=1e-12)
        totals = dict(zip(profiles.SECTORS, budgets.sum(axis=0)))
        self.assertAlmostEqual(totals["industry"], .35)
        self.assertAlmostEqual(totals["tourism"], .03)
        self.assertAlmostEqual(totals["services"] + totals["tourism"], .30)
        self.assertGreater(budgets[2, 1] / weights.iloc[2], budgets[0, 1] / weights.iloc[0])
        self.assertEqual(report["fallbacks"], [])

    def test_missing_region_uses_reported_parent_not_zero(self):
        cache = FixtureCache()
        for key in ("nama_10r_3empers", "nama_10r_3gva"):
            cache.tables[key] = cache.tables[key].loc[lambda f: f.geo != "HR028"]
        weights = pd.Series([.4, .35, .25], index=cache.regions)
        budgets, mix, report = profiles.composition("HR", 2020, weights, cache, .1)
        self.assertTrue(np.isfinite(mix).all())
        self.assertTrue((budgets[2] > 0).all())
        self.assertTrue(any("parent HR" in f["basis"] for f in report["fallbacks"]))

    def test_no_economic_sources_fails_and_does_not_invent_a_mix(self):
        cache = FixtureCache()
        cache.tables["nama_10r_3empers"] = pd.DataFrame()
        cache.tables["nama_10r_3gva"] = pd.DataFrame()
        with self.assertRaisesRegex(ValueError, "needs Eurostat"):
            profiles.composition("HR", 2020, pd.Series([1.], index=["HR050"]), cache, .1)
        for invalid in (-.1, 1., np.nan):
            with self.assertRaisesRegex(ValueError, "Tourism share"):
                profiles.composition("HR", 2020, pd.Series([1.], index=["HR050"]), cache, invalid)

    def test_library_integrity_and_bdew_month_weekend_mapping(self):
        bdew, research, manifest = profiles.library()
        self.assertEqual(set(bdew.profile), {"H25", "G25", "L25"})
        self.assertEqual(research.profile.nunique(), 32)
        self.assertEqual(len(bdew), 3 * 12 * 3 * 24)
        self.assertEqual(manifest["sources"][1]["licence"], "CC BY 4.0")
        cache = FixtureCache()
        stamps = pd.DatetimeIndex(["2020-01-01T09:00Z", "2020-01-04T09:00Z", "2020-01-06T09:00Z"])
        local, weekday, daytype, _ = profiles.country_calendar("HR", stamps, cache)
        self.assertEqual(list(local.hour), [10, 10, 10])
        self.assertEqual(list(daytype), ["sunday", "saturday", "weekday"])


class GeneratorIntegrationTests(unittest.TestCase):
    def test_refactored_export_uses_prepared_shapes_and_records_method(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "electricity_demand_method.json").write_text('{"method":"sector-weighted"}')
            stamps = observations(2021)
            a = stamps.to_numpy() * (.4 + .05 * np.sin(2 * np.pi * stamps.index.hour.to_numpy() / 24))
            b = stamps.to_numpy() - a
            gross = pd.DataFrame(dict(HR1=a, HR2=b), index=pd.Index(range(1, 8761), name="period"))
            native = gross.stack().rename("Power").reset_index()
            native.columns = ["period", "Zone", "Power"]
            native["System"] = "HR"
            baseline = (gross * .1).reset_index()
            exporter = CaseExporter.__new__(CaseExporter)
            exporter.bundle = root
            exporter.data = root / "data"
            exporter.countries = dict(HR1="HR", HR2="HR")
            exporter.fleets = []
            exporter.years = [2025]
            exporter.audit = {}
            exporter.source_files = {}
            exporter.series = lambda name: native if name == "electricity_demand.csv" else baseline
            exporter.demand_multiplier = lambda *args: 1.
            exporter.bus = lambda region, carrier: region + "_" + carrier
            exporter.build_electricity_demand()
            np.testing.assert_allclose(exporter.electricity.to_numpy(), gross.to_numpy() * .8)
            self.assertEqual(exporter.audit["electricity_profile_provenance"]["method"], "sector-weighted")
            self.assertIn("electricity_demand_method.json", exporter.source_files)

    def test_export_requires_matching_prepared_method_year_and_assumption(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            demand_file = root / "electricity_demand_2020.csv"
            demand_file.write_bytes(b"prepared demand")
            output = root / "bundle"
            output.mkdir()
            report = dict(method="sector-weighted", source_year=2020, countries={"HR": dict(tourism_fraction_of_services=.1)},
                          prepared_model_source_sha256=hashlib.sha256(demand_file.read_bytes()).hexdigest())
            (root / "electricity_demand_method.json").write_text(json.dumps(report))
            args = argparse.Namespace(electricity_demand_method="sector-weighted", electricity_demand_year=2020, electricity_tourism_share=.1)
            copy_demand_provenance(demand_file, output, args)
            self.assertTrue((output / "electricity_demand_method.json").exists())
            self.assertFalse((output / "data").exists())
            for field, value in (("electricity_demand_method", "national-scaled"), ("electricity_demand_year", 2021), ("electricity_tourism_share", .2)):
                changed = argparse.Namespace(**vars(args))
                setattr(changed, field, value)
                with self.assertRaises(ValueError):
                    copy_demand_provenance(demand_file, output, changed)
            demand_file.write_bytes(b"changed independently")
            with self.assertRaisesRegex(ValueError, "source changed"):
                copy_demand_provenance(demand_file, output, args)

    def test_gui_passes_method_without_requiring_new_old_config_fields(self):
        config = dict(countries="HR", spatial_level="nuts3", out_root="out", data_root="cache", sector_power=True,
                      power_output_level="aggregated", hydro_output_level="match-power", hydro_year="2020", vre_year="2020",
                      skip_vre=True, model_export=False, electricity_demand_year="2020")
        command = build_command(config)
        self.assertEqual(command[command.index("--electricity-demand-method") + 1], "national-scaled")
        config.update(electricity_demand_method="sector-weighted", electricity_tourism_share="0.2")
        command = build_command(config)
        self.assertEqual(command[command.index("--electricity-demand-method") + 1], "sector-weighted")
        self.assertEqual(command[command.index("--electricity-tourism-share") + 1], "0.2")
        config["electricity_tourism_share"] = "NaN"
        with self.assertRaisesRegex(ValueError, "Tourism share"):
            build_command(config)

    def test_failed_source_acquisition_retains_previous_demand(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            weights = root / "HR_NUTS3_2019_tot.csv"
            pd.DataFrame(dict(NUTS3=["HR050"], GWh_tot=[1.])).to_csv(weights, index=False)
            original = root / "electricity_demand.csv"
            original.write_bytes(b"previous complete export")
            args = argparse.Namespace(countries=["HR"], year=2020, out_dir=root, weights_dir=root,
                                      zone_map=None, token="test", cache_dir=root, refresh=False,
                                      demand_method="sector-weighted", tourism_share=.1)
            with patch.object(demand, "national_load", return_value=observations()), patch.object(demand, "generate_sector_profiles", side_effect=ValueError("source unavailable")):
                with self.assertRaisesRegex(ValueError, "source unavailable"):
                    demand.generate(args)
            self.assertEqual(original.read_bytes(), b"previous complete export")
            self.assertFalse(list(root.glob("*.part")))

    def test_generator_native_custom_aggregation_and_unchanged_baseline(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = FixtureCache()
            weights_dir = root / "weights"
            weights_dir.mkdir()
            pd.DataFrame(dict(NUTS3=source.regions, GWh_tot=[40., 35., 25.])).to_csv(weights_dir / "HR_NUTS3_2019_tot.csv", index=False)
            zone_map = root / "zones.csv"
            pd.DataFrame(dict(country="HR", nuts3=source.regions, zone=["HR1", "HR2", "HR1"])).to_csv(zone_map, index=False)
            args = argparse.Namespace(countries=["HR"], year=2020, out_dir=root / "result", weights_dir=weights_dir,
                                      zone_map=zone_map, token="test-not-used", cache_dir=root / "cache", refresh=False,
                                      demand_method="sector-weighted", tourism_share=.1)
            load = observations()
            with patch.object(demand, "national_load", return_value=load), patch.object(profiles, "SourceCache", return_value=source):
                demand.generate(args)
            native = pd.read_csv(args.out_dir / "electricity_demand.csv")
            self.assertEqual(native.period.nunique(), 8760)
            self.assertEqual(list(native.columns), ["period", "Power", "System", "Zone"])
            expected = load.loc[~((load.index.month == 2) & (load.index.day == 29))]
            np.testing.assert_allclose(native.groupby("period").Power.sum(), expected.to_numpy(), atol=1e-7)
            np.testing.assert_allclose(native.groupby("Zone").Power.sum().reindex(["HR1", "HR2"]), expected.sum() * np.array([.65, .35]), atol=1e-6)
            ledger = pd.read_csv(args.out_dir / "electricity_sector_budgets_2020.csv")
            self.assertAlmostEqual(ledger.filter(like="_MWh").to_numpy().sum(), expected.sum(), places=5)
            report = json.loads((args.out_dir / "electricity_demand_method.json").read_text())
            self.assertEqual(report["method"], "sector-weighted")
            self.assertEqual(report["electricity_demand_sha256"], hashlib.sha256((args.out_dir / "electricity_demand.csv").read_bytes()).hexdigest())
            # Reverting the option must restore the exact original calculation
            # and replace the provenance, including removing a stale ledger.
            args.demand_method = "national-scaled"
            with patch.object(demand, "national_load", return_value=load):
                demand.generate(args)
            raw = pd.read_csv(args.out_dir / "electricity_demand_nuts3_2020.csv")
            wide = raw.pivot(index="timestamp", columns="zone", values="el_dem_mw").reindex(columns=source.regions)
            np.testing.assert_allclose(wide, np.outer(load.to_numpy(), [.4, .35, .25]), atol=1e-10)
            self.assertFalse((args.out_dir / "electricity_sector_budgets_2020.csv").exists())

    def test_new_cli_option_defaults_preserve_existing_behavior(self):
        args = demand.parser().parse_args(["--countries", "HR", "--year", "2020", "--out-dir", "out", "--cache-dir", "cache"])
        self.assertEqual(args.demand_method, "national-scaled")


if __name__ == "__main__":
    unittest.main()
