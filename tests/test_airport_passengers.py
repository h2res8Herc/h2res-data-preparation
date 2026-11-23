import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from transport.script.airport_passengers import BASIS, BUNDLED, FALLBACK, passenger_table, regional_weights


class AirportPassengerTests(unittest.TestCase):
    def test_bundled_croatia_preserves_small_airport_and_host_county(self):
        codes = ["HR025", "HR031", "HR033", "HR035", "HR036", "HR037", "HR065", "HR050"]
        # A generalized point-in-polygon match can place Zagreb Airport in the city.
        regions = gpd.GeoDataFrame({"NUTS_ID": codes}, geometry=[box(15,45,17,46)] * len(codes), crs=4326)
        weights, report = regional_weights(BUNDLED, regions, "HR", 2020)
        self.assertEqual(report["basis"], BASIS)
        self.assertEqual(report["unlocated_passengers"], 0)
        self.assertEqual(weights["HR025"], 1275)
        self.assertEqual(weights["HR065"], 747046)
        self.assertEqual(weights["HR050"], 0)
        self.assertAlmostEqual(100 * weights["HR025"] / weights.sum(), .0719, places=4)
        domestic, report = regional_weights(BUNDLED, regions, "HR", 2020, "domestic")
        self.assertEqual(domestic["HR025"], 5351)
        self.assertEqual(domestic["HR065"], 166657)
        self.assertEqual(domestic["HR050"], 0)
        self.assertEqual(report["unlocated_passengers"], 0)
        self.assertEqual(report["basis"], "domestic_airport_passengers")

    def test_domestic_evidence_order_and_total_only_airport(self):
        totals = pd.Series({"SI_AAAA": 100., "SI_BBBB": 100., "SI_CCCC": 100., "SI_DDDD": 100.})
        domestic = pd.Series({"SI_AAAA": 0., "SI_BBBB": 60., "SI_EEEE": 44.})
        international = pd.Series({"SI_AAAA": 100., "SI_BBBB": 40., "SI_CCCC": 85.})
        airports = passenger_table(2021, domestic, international, totals)
        self.assertEqual(airports.loc["SI_AAAA", "domestic"], 0)
        self.assertEqual(airports.loc["SI_AAAA", "domestic_basis"], "Eurostat_reported_domestic")
        self.assertEqual(airports.loc["SI_CCCC", "domestic"], 15)
        self.assertEqual(airports.loc["SI_CCCC", "domestic_basis"], "Eurostat_total_minus_reported_international")
        self.assertEqual(airports.loc["SI_DDDD", "domestic"], 25)
        self.assertEqual(airports.loc["SI_EEEE", "domestic"], 44)
        self.assertTrue(pd.isna(airports.loc["SI_EEEE", "international"]))

    def test_missing_location_is_reported_and_empty_coverage_uses_fallback(self):
        regions = gpd.GeoDataFrame({"NUTS_ID":["SI001"]}, geometry=[box(14,46,15,47)], crs=4326)
        airports = pd.DataFrame({"year":[2020,2020], "country":["SI","SI"], "icao":["AAAA","BBBB"],
                                 "international":[100,15], "basis":["reported","reported"],
                                 "longitude_deg":[14.5,None], "latitude_deg":[46.5,None]})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "airports.csv"
            airports.to_csv(path, index=False)
            weights, report = regional_weights(path, regions, "SI", 2020)
            self.assertEqual(weights["SI001"], 100)
            self.assertEqual(report["unlocated_passengers"], 15)
            _, report = regional_weights(path, regions, "SI", 2019)
            self.assertEqual(report["basis"], FALLBACK)
