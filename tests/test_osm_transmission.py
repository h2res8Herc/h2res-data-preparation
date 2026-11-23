import json
from pathlib import Path
import tempfile
import unittest

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from power.osm_transmission import extract, rating, read_prepared
from regional_network_inputs import internal_regions, mapped_network


class OsmTransmissionTests(unittest.TestCase):
    def test_osm_crossings_at_multiple_spatial_levels(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            nuts = folder / "regions.geojson"
            ids = ["AA001", "AA002", "BB001"]
            gpd.GeoDataFrame({"NUTS_ID": ids}, geometry=[box(x, 0, x+1, 1) for x in range(3)],
                             crs=4326).to_file(nuts)
            mapping = pd.DataFrame(dict(country=["AA", "AA", "BB"], nuts3=ids, zone=["west", "mid", "east"]))
            osm = folder / "lines.osm"
            osm.write_text("""<osm version="0.6">
                <node id="1" lon="0.5" lat="0.5"/><node id="2" lon="2.5" lat="0.5"/>
                <node id="3" lon="0.5" lat="0.4"/><node id="4" lon="1" lat="0.4"/>
                <node id="5" lon="1.5" lat="0.4"/>
                <way id="10"><nd ref="1"/><nd ref="2"/><tag k="power" v="line"/>
                  <tag k="voltage" v="220000"/><tag k="circuits" v="2"/></way>
                <way id="11"><nd ref="3"/><nd ref="4"/><tag k="power" v="cable"/>
                  <tag k="voltage" v="150000"/><tag k="frequency" v="0"/></way>
                <way id="12"><nd ref="4"/><nd ref="5"/><tag k="power" v="cable"/>
                  <tag k="voltage" v="150000"/><tag k="frequency" v="0"/></way>
                <way id="13"><nd ref="1"/><nd ref="2"/><tag k="power" v="minor_line"/></way>
                <way id="14"><nd ref="1"/><nd ref="2"/><tag k="power" v="line"/>
                  <tag k="voltage" v="20000"/></way>
                </osm>""", encoding="utf-8")
            paths = {"AA": osm, "BB": osm}  # overlapping country extracts
            grid = extract(paths, nuts, mapping)
            self.assertEqual(len(grid["corridors"]), 3)
            self.assertEqual(len(grid["crossings"]), 7)
            self.assertEqual(len(grid["country_border_estimates"]), 1)
            self.assertEqual(sum(r["way_ids"] == [11, 12] for r in grid["crossings"]), 1)
            ac = [r for r in grid["corridors"] if r["unit_name"] == "400kV_AC"]
            self.assertEqual(len(ac), 2)
            self.assertAlmostEqual(ac[0]["cap_mw"], (220 * 1.29 * 2 + (35 + 20) * .21) * 3**.5)
            self.assertEqual(grid["counts"]["ways_with_assumed_voltage_intersecting_regions"], 1)
            self.assertEqual({r["volts"] for c in grid["crossings"] for r in c["ratings"] if r["assumed_voltage"]}, {35000})
            self.assertTrue(any(r["System"] != r["To"] for r in ac))
            path = folder / "grid.json"
            path.write_text(json.dumps(grid))
            national = mapping.assign(zone=mapping.country)
            with self.assertRaisesRegex(ValueError, "geography"):
                read_prepared(path, national, set(zip(national.country, national.zone)))
            grouped = extract(paths, nuts, national)
            self.assertEqual(len(grouped["corridors"]), 1)
            self.assertEqual(grouped["corridors"][0]["cap_mw"], ac[0]["cap_mw"])

    def test_low_voltage_and_ambiguous_tags(self):
        for value, expected in [("400",400), ("20 kV",20000), ("0.4kV",400), ("35000",35000)]:
            record, = rating(dict(voltage=value))
            self.assertEqual(record["volts"], expected)
            self.assertFalse(record["assumed_voltage"])
        for value in ("", "unknown", "0"):
            record, = rating(dict(voltage=value))
            self.assertEqual(record["volts"], 35000)
            self.assertTrue(record["assumed_voltage"])
        self.assertEqual([(r["volts"], r["assumed_voltage"]) for r in rating(dict(voltage="10000;unknown"))],
                         [(10000, False), (35000, True)])
        self.assertFalse(rating(dict(voltage="110000;220000", circuits="3")))
        self.assertFalse(rating(dict(voltage="110000", frequency="16.7")))
        self.assertEqual(len(rating(dict(voltage="110000;220000", circuits="1;2"))), 2)
        self.assertEqual(rating(dict(voltage="110000", cables="6"))[0]["circuits"], 2)

    def test_only_disconnected_component_keeps_virtual_electricity(self):
        frame = pd.DataFrame([dict(unit_name=t, System="HR", zone="HR1", To="SI", zoneTo="SI1",
                                   cap_mw=10., max_cap=1000., max_cap_period=20., km=100., var_cost=1.,
                                   loss=.01, final_life_cap=.1) for t in ["400kV_AC", "HVDC"]])
        targets = {("HR", z) for z in "abc"}
        baseline, notes = internal_regions(frame, targets, {("HR","a"): 1.})
        corridor = dict(System="HR", zone="a", To="HR", zoneTo="b", unit_name="400kV_AC", cap_mw=250., km=30.)
        result, audit = mapped_network(frame, baseline, notes, [corridor], targets)
        ab = result.loc[result.zone.eq("a") & result.zoneTo.eq("b")]
        self.assertEqual(ab.unit_name.tolist(), ["400kV_AC"])
        self.assertEqual(ab.cap_mw.tolist(), [250.])
        self.assertEqual(sum(n["electricity_fallback"] for n in audit), 2)
