"""Demand regions need full input coverage, but need not host a power plant."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model_input_bundle import validate_bundle
from model_variants import update_workbooks


class ZeroGeneratorZoneTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.data = self.root / "data"
        self.data.mkdir()
        self.zones = ["HR021", "HR023"]
        periods = list(range(1, 8761))
        local = pd.concat([pd.DataFrame(dict(period=periods, System="HR", zone=zone)) for zone in self.zones], ignore_index=True)
        demand = local.rename(columns={"zone": "Zone"}).assign(Power=1.)
        demand.to_csv(self.data / "electricity_demand.csv", index=False)
        generators = pd.DataFrame(dict(System=["HR"], Zone=["HR021"], unit_name=["wind"], technology=["WTON"]))
        generators.to_csv(self.data / "generators.csv", index=False)
        pd.DataFrame(dict(period=periods, wind=.5)).to_csv(self.data / "renewable_availability.csv", index=False)
        pd.DataFrame(dict(period=periods)).to_csv(self.data / "hydro_inflows.csv", index=False)
        for name in ["heating_individual", "heating_district", "cooling_individual", "cooling_district",
                     "industry_electricity", "heating_electricity", "solar_thermal_availability"]:
            pd.DataFrame({"period": periods, **{zone: 1. for zone in self.zones}}).to_csv(self.data / (name + ".csv"), index=False)
        local.assign(Steel=1.).to_csv(self.data / "industry_heat.csv", index=False)
        local.assign(ICE_car=1.).to_csv(self.data / "transport_profiles.csv", index=False)
        local.assign(Passenger_cars=1.).to_csv(self.data / "transport_demand.csv", index=False)
        active = pd.DataFrame(dict(System="HR", zone=self.zones, active="Y"))
        industry = active[["System", "zone"]].assign(Industry="Steel", unit_name="Gas_industry",fuel_type="Gas",
                    include_in_the_model="Y",cap_mw=1.,share_fuel_2020=1.,max_share_fuel=1.,efficiency=.9)
        transport = active[["System", "zone"]].assign(unit_name="ICE_car", sector="Passenger_cars")
        with pd.ExcelWriter(self.data / "flex_tech.xlsx") as writer:
            active.to_excel(writer, sheet_name="active_zones", index=False)
            industry.to_excel(writer, sheet_name="Industry_data", index=False)
            industry.iloc[:0].to_excel(writer,sheet_name="simple_industry",index=False)
            pd.DataFrame(dict(year=[2020],wind=[1.])).to_excel(writer,sheet_name="tech_cost_years",index=False)
            pd.DataFrame(dict(year=[2020,2020],zone=self.zones,wind=[1.,0.])).to_excel(writer,sheet_name="cap_inv_lim",index=False)
            pd.DataFrame([['zone','System','zoneTo','To','km','cap_mw'],['HR021','HR','HR023','HR',0.,1.],['HR023','HR','HR021','HR',0.,1.]],
                columns=['Unnamed: 0','Unnamed: 1','Unnamed: 2','Unnamed: 3','Unnamed: 4','400kV_AC']).to_excel(writer,sheet_name='transmission',index=False)
            pd.DataFrame([['System','zone','km','cap_mw'],['HR','HR021',0.,1.],['HR','HR023',0.,1.]],
                columns=['Unnamed: 0','Unnamed: 1','Unnamed: 2','400kV_AC']).to_excel(writer,sheet_name='transmission_outside',index=False)
            transport.to_excel(writer, sheet_name="transport_all", index=False)
        (self.root / "bundle_manifest.json").write_text(json.dumps(dict(generated_sectors=["power", "industry", "transport", "heating"])))

    def tearDown(self):
        self.directory.cleanup()

    def report(self):
        return validate_bundle(self.root, "flex_tech.xlsx", False, "regular")

    def test_active_zone_without_local_generation_is_valid_and_explicit(self):
        report = self.report()
        self.assertTrue(report["ready"], report["errors"])
        self.assertEqual(report["zones_without_sourced_generators"], [["HR", "HR023"]])
        self.assertTrue(any("No sourced generator records" in item for item in report["warnings"]))

    def test_zone_without_generators_still_requires_all_hourly_demand(self):
        path = self.data / "electricity_demand.csv"
        frame = pd.read_csv(path)
        frame.loc[~(frame.Zone.eq("HR023") & frame.period.eq(8760))].to_csv(path, index=False)
        report = self.report()
        self.assertFalse(report["ready"])
        self.assertTrue(any("8760 distinct hours" in item and "HR023" in item for item in report["errors"]))

    def test_regular_validator_rejects_unsupported_industry_fuels_even_at_zero_capacity(self):
        from model_input_bundle import replace_sheets
        from openpyxl import load_workbook
        path = self.data / "flex_tech.xlsx"
        book = load_workbook(path)
        if 'simple_industry' in book.sheetnames:
            del book['simple_industry']
        book.copy_worksheet(book["Industry_data"]).title = "simple_industry"
        book.save(path)
        book.close()
        for sheet in ("Industry_data", "simple_industry"):
            frame = pd.read_excel(self.data / "flex_tech.xlsx", sheet_name="Industry_data")
            frame["fuel_type"] = "heat"
            replace_sheets(self.data / "flex_tech.xlsx", {sheet: frame})
            report = self.report()
            self.assertFalse(report["ready"])
            self.assertTrue(any(sheet + ": non-eFuel industry contains unsupported fuels" in error for error in report["errors"]))

    def test_existing_wind_generator_still_requires_its_availability_column(self):
        pd.DataFrame(dict(period=range(1, 8761))).to_csv(self.data / "renewable_availability.csv", index=False)
        report = self.report()
        self.assertFalse(report["ready"])
        self.assertTrue(any("lacks generator columns" in item and "wind" in item for item in report["errors"]))

    def test_generated_plants_outside_requested_zones_remain_an_error(self):
        path = self.data / "generators.csv"
        frame = pd.read_csv(path)
        pd.concat([frame, pd.DataFrame(dict(System=["HR"], Zone=["HR999"], unit_name=["outside"], technology=["STUR"]))]).to_csv(path, index=False)
        report = self.report()
        self.assertFalse(report["ready"])
        self.assertTrue(any("inactive or absent" in item for item in report["errors"]))

    def test_failed_validation_closes_the_workbook_on_windows(self):
        with patch("model_input_bundle.pd.read_csv", side_effect=ValueError("broken CSV")):
            with self.assertRaisesRegex(ValueError, "broken CSV"):
                self.report()
        path = self.data / "flex_tech.xlsx"
        moved = path.with_name("closed.xlsx")
        path.replace(moved)
        self.assertTrue(moved.is_file())

    def test_variants_read_defaults_from_reference_not_already_regionalized_workbook(self):
        reference = self.root / "reference"
        (reference / "data").mkdir(parents=True)
        source = self.root / "transport" / "combined"
        source.mkdir(parents=True)
        generated = pd.DataFrame(dict(System="HR", zone=self.zones, sector="Passenger_cars", unit_name="ICE_car",
                                      total_load=[10., 20.], number=[1., 2.], efficiency_primary=.5))
        generated.to_csv(source / "transport_all.csv", index=False)
        with pd.ExcelWriter(reference / "data" / "flex_tech.xlsx") as writer:
            generated.iloc[:1].assign(zone="HR1", **{"2025": 5.}).rename(columns={"2025": 2025}).to_excel(writer, sheet_name="transport_all", index=False)
        active = pd.DataFrame(dict(System="HR", zone=self.zones, active="Y"))
        with pd.ExcelWriter(self.data / "flex_tech.xlsx") as writer:
            active.to_excel(writer, sheet_name="active_zones", index=False)
            generated.assign(**{"2025": [90., 91.]}).rename(columns={"2025": 2025}).to_excel(writer, sheet_name="transport_all", index=False)
        with patch("model_variants.configurations", return_value=[(False, "regular", "conservative")]):
            update_workbooks(SimpleNamespace(out_root=self.root, sectors=["transport"]), self.data,
                             {"active_zones": active}, reference=reference)
        actual = pd.read_excel(self.data / "flex_tech.xlsx", "transport_all")
        self.assertEqual(actual[2025].tolist(), [5., 5.])
        self.assertEqual(actual.number.tolist(), [1., 2.])


if __name__ == "__main__":
    unittest.main()
