"""Exercise weighted rolling budgets without network requests or real sleeps."""
from contextlib import closing, redirect_stdout
from concurrent.futures import ThreadPoolExecutor
import base64
import gzip
import io
import os
from pathlib import Path
import sqlite3
import tempfile
import subprocess
import sys
import unittest
from urllib.error import HTTPError
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
            connection.execute('CREATE TABLE run_requests (run_id TEXT NOT NULL, timestamp REAL NOT NULL, cost REAL NOT NULL)')
            connection.executemany('INSERT INTO run_requests VALUES (?, ?, ?)',
                                   [(quota.current_run_id(),stamp,cost) for stamp,cost in rows])

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
            count,weight=connection.execute('SELECT COUNT(*), SUM(cost) FROM run_requests').fetchone()
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

    def test_day_and_month_estimates_do_not_impose_long_local_waits(self):
        for label,age,cost in [('day',3700.,8990.),('month',90000.,269990.)]:
            with self.subTest(label=label):
                self.database=Path(self.database.parent)/(label+'.sqlite3')
                self.seed([(self.now-age,cost)])
                self.reserve(max_wait=3600.)
        self.assertEqual(self.waits,[])

    def test_new_run_starts_at_zero_and_child_sectors_share_its_id(self):
        with quota.quota_run(inherit=False) as old:
            self.seed([(self.now,269990.)])
            with quota.quota_run(inherit=False) as new:
                self.assertNotEqual(old,new)
                self.reserve()
                with quota.quota_run():self.assertEqual(quota.current_run_id(),new)
                child=subprocess.check_output([sys.executable,'-c',
                    'import openmeteo_quota; print(openmeteo_quota.current_run_id())'],text=True)
                self.assertEqual(child.strip(),new)
            self.assertEqual(quota.current_run_id(),old)
        self.assertEqual(self.waits,[])

    def test_old_installation_wide_table_does_not_affect_a_new_run(self):
        with closing(sqlite3.connect(self.database)) as connection,connection:
            connection.execute('CREATE TABLE requests (timestamp REAL,cost REAL)')
            connection.execute('INSERT INTO requests VALUES (?,?)',(self.now,270000.))
        self.reserve()
        self.assertEqual(self.waits,[])

    def test_short_window_wait_rechecks_instead_of_failing_at_old_timeout(self):
        self.seed([(self.now,530.)])
        self.reserve(max_wait=10.)
        self.assertGreater(len(self.waits),1)
        self.assertTrue(all(seconds<=10 for seconds,_ in self.waits))

    def test_expired_history_does_not_delay_new_requests(self):
        self.seed([(self.now-32*86400.,1000000.)])
        self.reserve()
        self.assertEqual(self.waits,[])
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM run_requests').fetchone()[0],1)

    def test_simultaneous_clients_share_reservations(self):
        # Only one query fits the remaining minute budget. Transactions must
        # prevent two clients from both seeing the same unused capacity.
        self.seed([(self.now,500.)])
        class Waiting(Exception):pass
        def attempt(_):
            try:
                quota.reserve_request(PARAMS,database=self.database,clock=lambda:self.now,
                    wait=lambda seconds,reason:(_ for _ in ()).throw(Waiting()))
                return True
            except Waiting:
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

    def test_heating_http_429_retries_past_old_limits_and_honors_reset_header(self):
        errors=[HTTPError('https://archive-api.open-meteo.com',429,'limit',{'Retry-After':'7200'},None) for _ in range(10)]
        response=object();opener=Mock(side_effect=[*errors,response]);wait=Mock()
        with patch.object(quota,'reserve_request') as reserve:
            actual=quota.openmeteo_urlopen('request',PARAMS,opener=opener,wait=wait)
        self.assertIs(actual,response)
        self.assertEqual(reserve.call_count,11)
        self.assertEqual(wait.call_count,10)
        self.assertTrue(all(c.args[0]==7200 for c in wait.call_args_list))

    def test_heating_outer_reader_does_not_give_up_after_five_429_responses(self):
        from heating.paper_weather import request_series
        errors=[HTTPError('https://archive-api.open-meteo.com',429,'limit',{},None) for _ in range(7)]
        reader=Mock(side_effect=[*errors,[1.,2.]])
        with patch('heating.paper_weather.wait_seconds') as wait:
            result=request_series(reader,'cache',16.,45.,2020)
        self.assertEqual(result,[1.,2.])
        self.assertEqual(reader.call_count,8)
        self.assertEqual(wait.call_count,7)

    def test_heating_non_quota_errors_and_manual_stop_are_not_swallowed(self):
        with patch.object(quota,'reserve_request'):
            opener=Mock(side_effect=HTTPError('https://archive-api.open-meteo.com',403,'denied',{},None))
            with self.assertRaises(HTTPError):quota.openmeteo_urlopen('request',PARAMS,opener=opener)
            opener.assert_called_once()
            opener=Mock(side_effect=HTTPError('https://archive-api.open-meteo.com',429,'limit',{},None))
            with self.assertRaises(KeyboardInterrupt):
                quota.openmeteo_urlopen('request',PARAMS,opener=opener,wait=Mock(side_effect=KeyboardInterrupt))


if __name__=='__main__':unittest.main()
