"""Exercise weighted rolling budgets without network requests or real sleeps."""
from contextlib import closing, redirect_stdout
from concurrent.futures import ThreadPoolExecutor
import base64
import gzip
import io
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

import openmeteo_quota as quota


PARAMS = dict(start_date='2020-01-01', end_date='2020-12-31', hourly='shortwave_radiation', latitude=45.)


class QuotaTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.database = Path(folder.name) / 'quota.sqlite3'
        self.now = 10000000.
        self.waits = []
        output=redirect_stdout(io.StringIO());output.__enter__()
        self.addCleanup(output.__exit__,None,None,None)

    def wait(self, seconds, reason):
        self.waits.append((seconds, reason))
        self.now += seconds

    def reserve(self, params=PARAMS, **kwargs):
        return quota.reserve_request(params, database=self.database, clock=lambda:self.now, wait=self.wait, **kwargs)

    def seed(self, rows):
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute('CREATE TABLE requests (timestamp REAL NOT NULL, cost REAL NOT NULL)')
            connection.executemany('INSERT INTO requests VALUES (?, ?)', rows)

    def test_full_year_weight_and_multi_variable_location_model_weights(self):
        self.assertAlmostEqual(quota.estimated_calls(PARAMS), 366/14)
        self.assertEqual(quota.estimated_calls(dict(PARAMS,end_date='2020-01-14',
            hourly=','.join('v'+str(n) for n in range(15)),latitude=[45.,46.],models='era5,era5_land')), 6.)

    def test_croatia_86_queries_download_in_bursts_without_fixed_per_site_sleep(self):
        for _ in range(86):
            self.reserve()
        self.assertEqual(len(self.waits), 4)
        self.assertAlmostEqual(sum(s for s,_ in self.waits), 244.)
        self.assertTrue(all('minute' in reason for _,reason in self.waits))
        with closing(sqlite3.connect(self.database)) as connection:
            count,weight=connection.execute('SELECT COUNT(*), SUM(cost) FROM requests').fetchone()
        self.assertEqual(count,86)
        self.assertAlmostEqual(weight,86*366/14)

    def test_hourly_usage_from_previous_process_is_retained(self):
        self.seed([(self.now-1000.,4490.)])
        self.reserve()
        self.assertEqual(len(self.waits),1)
        self.assertEqual(self.waits[0][0],2601.)
        self.assertIn('hour',self.waits[0][1])

    def test_wait_only_until_enough_calls_expire(self):
        self.seed([(self.now-59.,20.),(self.now-30.,510.)])
        self.reserve()
        self.assertEqual(self.waits[0][0],2.)

    def test_daily_and_monthly_limits_stop_resumably_beyond_wait_budget(self):
        for label,age,cost in [('day',3700.,8990.),('month',90000.,269990.)]:
            with self.subTest(label=label):
                self.database=Path(self.database.parent)/(label+'.sqlite3')
                self.seed([(self.now-age,cost)])
                with self.assertRaisesRegex(quota.OpenMeteoQuotaWaitError,label+' budget.*same weather cache'):
                    self.reserve(max_wait=3600.)
        self.assertEqual(self.waits,[])

    def test_default_wait_recovers_the_reported_italy_daily_budget(self):
        self.seed([(self.now-(86400.-79732.),8990.)])
        self.reserve()
        self.assertEqual(len(self.waits),1)
        self.assertEqual(self.waits[0][0],79733.)
        self.assertIn('day',self.waits[0][1])

    def test_monthly_reset_beyond_default_budget_still_stops_without_reserving(self):
        self.seed([(self.now-2*86400.,269990.)])
        with self.assertRaisesRegex(quota.OpenMeteoQuotaWaitError,'month budget'):
            self.reserve()
        self.assertEqual(self.waits,[])
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM requests').fetchone()[0],1)

    def test_expired_history_does_not_delay_new_requests(self):
        self.seed([(self.now-32*86400.,1000000.)])
        self.reserve()
        self.assertEqual(self.waits,[])
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM requests').fetchone()[0],1)

    def test_simultaneous_clients_share_reservations(self):
        # Only one query fits the remaining minute budget. Transactions must
        # prevent two clients from both seeing the same unused capacity.
        self.seed([(self.now,500.)])
        def attempt(_):
            try:
                self.reserve(max_wait=0.)
                return True
            except quota.OpenMeteoQuotaWaitError:
                return False
        with ThreadPoolExecutor(max_workers=2) as workers:
            result=list(workers.map(attempt,range(2)))
        self.assertEqual(sorted(result),[False,True])

    def test_heating_counts_only_network_attempts_and_retains_cached_reader(self):
        from heating.generate_heating_inputs_standalone import RAW_CALCULATOR_GZ_B64
        from heating.paper_calculator import install_weather_budget
        source=install_weather_budget(gzip.decompress(base64.b64decode(RAW_CALCULATOR_GZ_B64)).decode())
        namespace={'__name__':'quota_test_heat_calculator'}
        exec(compile(source,'heating_calculator','exec'),namespace)
        params=dict(PARAMS,models='era5_land',hourly='temperature_2m')
        payload=Mock()
        payload.__enter__=Mock(return_value=payload);payload.__exit__=Mock(return_value=False)
        payload.read.return_value=b'{}'
        with patch.object(quota,'reserve_request') as reserve, \
             patch.object(namespace['urllib'].request,'urlopen',return_value=payload) as network, \
             patch.dict(namespace,{'_parse_open_meteo_t2m':lambda target:[1.]}):
            for _ in range(2):
                namespace['_fetch_open_meteo_t2m'](str(self.database.parent),params,2020,45.,16.,'nearest')
        reserve.assert_called_once_with(params)
        network.assert_called_once()


if __name__=='__main__':unittest.main()
