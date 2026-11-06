"""Custom examples describe real membership and reject unsupported geography early."""
from contextlib import redirect_stderr,redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

import generate_all_sector_inputs as runner

ROOT=Path(__file__).resolve().parents[1]
EXAMPLES=ROOT/'docs/custom_zones'
BOUNDARIES=ROOT/'power/data/NUTS_RG_20M_2021_4326_LEVL_3.geojson'


class CustomZoneMapTests(unittest.TestCase):
    def complete(self):
        return runner.read_custom_map(EXAMPLES/'HR_SI_IT_complete.csv')

    def test_complete_example_covers_three_countries_with_distinct_aggregation(self):
        mapping=self.complete()
        runner.validate_custom_map(mapping,BOUNDARIES,['HR','SI','IT'])
        self.assertEqual(mapping.groupby('country').size().to_dict(),{'HR':21,'IT':107,'SI':12})
        self.assertEqual(mapping.groupby('country').zone.nunique().to_dict(),{'HR':3,'IT':2,'SI':1})
        self.assertEqual(set(mapping.loc[mapping.zone.eq('HR_ZAGREB'),'nuts3']),{'HR050','HR065'})
        self.assertEqual(set(mapping.loc[mapping.zone.eq('HR_COASTAL'),'nuts3']),{f'HR03{i}' for i in range(1,8)})
        self.assertEqual(mapping.zone.eq('IT_NORTH').sum(),47)
        self.assertEqual(mapping.zone.eq('IT_REST').sum(),60)

    def test_partial_example_reports_the_sixty_excluded_italian_regions(self):
        mapping=runner.read_custom_map(EXAMPLES/'HR_SI_north_IT_PARTIAL_NOT_SUPPORTED.csv')
        self.assertEqual(len(mapping),80)
        self.assertEqual(mapping.zone.nunique(),5)
        with self.assertRaisesRegex(ValueError,"Partial-country.*'IT': 60"):
            runner.validate_custom_map(mapping,BOUNDARIES,['HR','SI','IT'])

    def test_blank_offshore_membership_is_not_silently_dropped(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'map.csv'
            path.write_text('country,nuts3,zone\nHR,HR050,HR_ZAGREB\nHR,,HR_OFFSHORE\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'offshore zones'):
                runner.read_custom_map(path)

    def test_invented_offshore_nuts_id_is_rejected(self):
        mapping=self.complete()
        mapping.loc[len(mapping)]=['HR','HR_SEA','HR_OFFSHORE']
        with self.assertRaisesRegex(ValueError,'unknown country/NUTS3'):
            runner.validate_custom_map(mapping,BOUNDARIES,['HR','SI','IT'])

    def test_each_source_region_has_one_target_and_zone_names_are_unique(self):
        mapping=self.complete()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'map.csv'
            pd.concat([mapping,mapping.iloc[:1].assign(zone='ANOTHER_ZONE')]).to_csv(path,index=False)
            with self.assertRaisesRegex(ValueError,'more than once'):
                runner.read_custom_map(path)
        with self.assertRaisesRegex(ValueError,'unique across model systems'):
            runner.validate_custom_map(mapping.assign(zone='COMMON'),BOUNDARIES,['HR','SI','IT'])

    def test_missing_selected_country_has_specific_diagnostic(self):
        mapping=self.complete()
        with self.assertRaisesRegex(ValueError,'no rows.*SI'):
            runner.validate_custom_map(mapping.loc[mapping.country.ne('SI')],BOUNDARIES,['HR','SI','IT'])

    def test_partial_map_stops_before_downloads_or_output_creation(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'output'
            argv=['generate_all_sector_inputs.py','--countries','HR,SI,IT','--spatial-level','custom',
                  '--zone-map',str(EXAMPLES/'HR_SI_north_IT_PARTIAL_NOT_SUPPORTED.csv'),'--out-root',str(output)]
            with patch('sys.argv',argv),patch.object(runner,'download') as download,patch.object(runner,'run') as run:
                with redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
                    self.assertEqual(runner.main(),2)
                download.assert_not_called();run.assert_not_called()
            self.assertFalse(output.exists())

    def test_selected_subset_of_complete_multi_country_map_can_validate(self):
        runner.validate_custom_map(self.complete(),BOUNDARIES,['HR'])


if __name__=='__main__':unittest.main()
