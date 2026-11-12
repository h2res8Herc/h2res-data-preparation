"""Respect Open-Meteo quotas while retaining complete reusable site weather."""
from contextlib import redirect_stdout
import datetime as dt
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('weather_rate_limits_test',ROOT/'power/VRES_distributions/build_vre_capacity_weighted_cf_from_schema_openmeteo_weighted.py')
vre=importlib.util.module_from_spec(spec);spec.loader.exec_module(vre)


class WeatherRateLimitTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.environment=patch.dict(os.environ,{'OPEN_METEO_API_KEY':'','OPENMETEO_API_KEY':'',
            'H2RES_OPENMETEO_QUOTA_DB':str(Path(folder.name)/'quota.sqlite3')})
        self.environment.start();self.addCleanup(self.environment.stop)

    def response(self,status=200,reason='',retry=None,periods=24):
        response=Mock(status_code=status)
        response.headers={} if retry is None else {'Retry-After':retry}
        response.json.return_value=({'hourly':{'time':pd.date_range('2020-01-01',periods=periods,freq='h').astype(str).tolist(),
                                                'shortwave_radiation':[100.]*periods}}
                                    if status==200 else {'error':True,'reason':reason})
        return response

    def fetch(self,**kwargs):
        return vre.fetch_openmeteo_hourly(**dict(lat=45.,lon=16.,date_from='2020-01-01',date_to='2020-01-01',
                                                timezone='UTC',want_pv=True,want_wind=False,**kwargs))

    def test_minutely_quota_waits_for_window_then_retries(self):
        with patch.object(vre.requests,'get',side_effect=[self.response(429,'Minutely API request limit exceeded'),self.response()]) as request, \
             patch.object(vre.time,'sleep') as sleep,redirect_stdout(io.StringIO()):
            frame=self.fetch()
        self.assertEqual(len(frame),24)
        self.assertEqual(request.call_count,2)
        self.assertGreaterEqual(sum(c.args[0] for c in sleep.call_args_list),60.)
        self.assertLessEqual(max(c.args[0] for c in sleep.call_args_list),30.)

    def test_retry_after_seconds_are_respected_without_shortening(self):
        with patch.object(vre.requests,'get',side_effect=[self.response(429,'Rate limit',retry='120'),self.response()]), \
             patch.object(vre.time,'sleep') as sleep,redirect_stdout(io.StringIO()):self.fetch()
        self.assertAlmostEqual(sum(c.args[0] for c in sleep.call_args_list),120.)

    def test_retry_after_http_date_and_bad_header(self):
        now=dt.datetime(2026,11,6,12,tzinfo=dt.timezone.utc)
        self.assertEqual(vre._retry_after({'Retry-After':'Fri, 06 Nov 2026 12:01:30 GMT'},now),90.)
        self.assertIsNone(vre._retry_after({'Retry-After':'unavailable'},now))

    def test_hourly_limit_uses_hour_window_then_retries(self):
        with patch.object(vre.requests,'get',side_effect=[self.response(429,'Hourly API request limit exceeded'),self.response()]) as request, \
             patch.object(vre.time,'sleep') as sleep,redirect_stdout(io.StringIO()):self.fetch()
        self.assertEqual(request.call_count,2)
        self.assertAlmostEqual(sum(c.args[0] for c in sleep.call_args_list),60.)

    def test_daily_quota_without_reset_hint_retries_without_a_full_day_pause(self):
        with patch.object(vre.requests,'get',side_effect=[self.response(429,'Daily API request limit exceeded'),self.response()]) as request, \
             patch.object(vre.time,'sleep') as sleep,redirect_stdout(io.StringIO()):
            self.fetch(max_rate_limit_wait=3600.)
        self.assertEqual(request.call_count,2)
        self.assertEqual(sum(c.args[0] for c in sleep.call_args_list),60.)

    def test_provider_can_prescribe_an_overnight_wait(self):
        with patch.object(vre.requests,'get',side_effect=[self.response(429,'Daily API request limit exceeded',retry='86400'),self.response()]) as request, \
             patch.object(vre.time,'sleep') as sleep,redirect_stdout(io.StringIO()) as output:
            frame=self.fetch()
        self.assertEqual(len(frame),24)
        self.assertEqual(request.call_count,2)
        self.assertEqual(sum(c.args[0] for c in sleep.call_args_list),86400.)
        self.assertIn('estimated resume',output.getvalue())

    def test_quota_waits_do_not_fail_at_a_former_total_time_budget(self):
        local_calls=[]
        def local_wait(params,**kwargs):
            if not local_calls:kwargs['wait'](120.,'local minute budget')
            local_calls.append(params)
        with patch.object(vre,'reserve_request',side_effect=local_wait), \
             patch.object(vre.requests,'get',side_effect=[self.response(429,'Daily quota',retry='20000'),self.response()]) as request, \
             patch.object(vre.time,'sleep') as sleep,redirect_stdout(io.StringIO()):
            self.fetch(max_rate_limit_wait=60.)
        self.assertEqual(request.call_count,2)
        self.assertEqual(sum(c.args[0] for c in sleep.call_args_list),20120.)

    def test_retry_after_is_not_shortened_by_legacy_wait_setting(self):
        with patch.object(vre.requests,'get',side_effect=[self.response(429,'Hourly quota',retry='7200'),self.response()]) as request, \
             patch.object(vre.time,'sleep') as sleep,redirect_stdout(io.StringIO()):
            self.fetch(max_rate_limit_wait=120.)
        self.assertEqual(request.call_count,2)
        self.assertEqual(sum(c.args[0] for c in sleep.call_args_list),7200.)

    def test_repeated_monthly_429_does_not_exhaust_network_retries(self):
        responses=[self.response(429,'Monthly request allowance exceeded') for _ in range(12)]+[self.response()]
        with patch.object(vre.requests,'get',side_effect=responses) as request, \
             patch.object(vre.time,'sleep') as sleep,redirect_stdout(io.StringIO()):
            frame=self.fetch(max_retries=2)
        self.assertEqual(len(frame),24)
        self.assertEqual(request.call_count,13)
        total=sum(c.args[0] for c in sleep.call_args_list)
        self.assertEqual(total,60.+120.+240.+480.+8*900.)

    def test_manual_stop_during_quota_wait_retains_previously_published_curves(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);schema=root/'schema.csv'
            pd.DataFrame(dict(new_unit_name=['IT_A'],technology='PHOT',cap_mw_old=1.,lat=45.,lon=16.,System='IT')).to_csv(schema,index=False)
            previous=root/'vre_cf_IT_2020.csv';previous.write_bytes(b'previous curves')
            with patch('sys.argv',['vre','--schema',str(schema),'--out-dir',str(root),'--country','IT',
                    '--date-from','2020-01-01','--date-to','2020-12-31']), \
                 patch.object(vre.requests,'get',return_value=self.response(429,'Daily allowance')) as request, \
                 patch.object(vre,'_wait_weather',side_effect=KeyboardInterrupt),redirect_stdout(io.StringIO()):
                with self.assertRaises(KeyboardInterrupt):vre.main()
            request.assert_called_once()
            self.assertEqual(previous.read_bytes(),b'previous curves')

    def test_customer_key_selects_official_endpoint_and_reuses_existing_public_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(vre.requests,'get',return_value=self.response()) as request,patch.object(vre.time,'sleep'),redirect_stdout(io.StringIO()):
                original=self.fetch(cache_dir=Path(folder))
                with patch.dict(os.environ,{'OPEN_METEO_API_KEY':'TEST_CUSTOMER_KEY'}):
                    cached=self.fetch(cache_dir=Path(folder))
            self.assertEqual(request.call_count,1)
            pd.testing.assert_frame_equal(original,cached)
            with patch.dict(os.environ,{'OPEN_METEO_API_KEY':'TEST_CUSTOMER_KEY'}), \
                 patch.object(vre.requests,'get',return_value=self.response()) as customer,patch.object(vre.time,'sleep'),redirect_stdout(io.StringIO()):
                self.fetch()
            self.assertEqual(customer.call_args.args[0],vre.CUSTOMER_ARCHIVE_URL)
            self.assertEqual(customer.call_args.kwargs['params']['apikey'],'TEST_CUSTOMER_KEY')
            self.assertNotIn('TEST_CUSTOMER_KEY',''.join(p.read_text() for p in Path(folder).iterdir()))

    def test_customer_error_is_permanent_and_key_is_redacted(self):
        with patch.dict(os.environ,{'OPEN_METEO_API_KEY':'TEST_PRIVATE_KEY'}), \
             patch.object(vre.requests,'get',return_value=self.response(401,'Invalid key TEST_PRIVATE_KEY')) as request:
            with self.assertRaisesRegex(RuntimeError,'HTTP 401') as raised:self.fetch()
        self.assertNotIn('TEST_PRIVATE_KEY',str(raised.exception))
        self.assertEqual(request.call_count,1)

    def test_truncated_cache_is_replaced_only_with_complete_response(self):
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder)
            with patch.object(vre.requests,'get',return_value=self.response()) as request,patch.object(vre.time,'sleep'),redirect_stdout(io.StringIO()):
                self.fetch(cache_dir=directory)
                path=next(directory.glob('openmeteo_*.csv'))
                pd.read_csv(path).iloc[:1].to_csv(path,index=False)
                restored=self.fetch(cache_dir=directory)
            self.assertEqual(request.call_count,2)
            self.assertEqual(len(restored),24)
            self.assertEqual(len(pd.read_csv(path)),24)
            self.assertEqual(list(directory.glob('.weather_*.tmp')),[])

    def test_failed_atomic_cache_write_keeps_previous_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'weather.csv';path.write_text('previous cache')
            frame=pd.DataFrame({'shortwave_radiation':[1.]},index=pd.date_range('2020-01-01',periods=1,tz='UTC'))
            with patch.object(pd.DataFrame,'to_csv',side_effect=OSError('disk full')):
                with self.assertRaisesRegex(OSError,'disk full'):vre._write_weather_cache(frame,path)
            self.assertEqual(path.read_text(),'previous cache')
            self.assertEqual(list(Path(folder).glob('.weather_*.tmp')),[])

    def test_full_year_request_has_no_fixed_pause_while_budget_is_available(self):
        with patch.object(vre.requests,'get',return_value=self.response(periods=8784)),patch.object(vre.time,'sleep') as sleep,redirect_stdout(io.StringIO()):
            frame=vre.fetch_openmeteo_hourly(45.,16.,'2020-01-01','2020-12-31','UTC',True,False)
        self.assertEqual(len(frame),8784)
        sleep.assert_not_called()

    def test_permanent_failure_stops_remaining_sites_and_preserves_previous_curves(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);schema=root/'schema.csv'
            pd.DataFrame(dict(new_unit_name=['IT_A','IT_A'],technology='PHOT',cap_mw_old=1.,lat=[45.,46.],lon=16.,System='IT')).to_csv(schema,index=False)
            previous=root/'vre_cf_IT_2020.csv';previous.write_bytes(b'previous curves')
            with patch('sys.argv',['vre','--schema',str(schema),'--out-dir',str(root),'--country','IT','--date-from','2020-01-01','--date-to','2020-12-31']), \
                 patch.object(vre,'fetch_openmeteo_hourly',side_effect=RuntimeError('HTTP 403 denied')) as request,redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError,'HTTP 403 denied'):vre.main()
            self.assertEqual(request.call_count,1)
            self.assertEqual(previous.read_bytes(),b'previous curves')
            self.assertEqual(pd.read_csv(root/'summary_IT.csv').status.tolist(),['ALL_SITES_FAILED'])


if __name__=='__main__':unittest.main()
