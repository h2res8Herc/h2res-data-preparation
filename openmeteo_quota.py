"""Run-scoped estimates and resumable retries for public Open-Meteo requests.

Published limits: https://open-meteo.com/en/pricing (checked 6 November 2026).
Reservations count attempted HTTP requests conservatively, including retries.
SQLite transactions share estimates between the sectors of one preparation run.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from contextlib import closing, contextmanager
from email.utils import parsedate_to_datetime
import math
import os
from pathlib import Path
import sqlite3
import time
import urllib.error
import urllib.request
import uuid

# Day/month estimates are informational. Only short windows proactively pace
# requests; actual server rejections determine longer quota recovery.
WINDOWS = (("minute", 60., 540.), ("hour", 3600., 4500.),
           ("day", 86400., 9000.), ("month", 31 * 86400., 270000.))
DEFAULT_DATABASE = Path(__file__).resolve().parent / ".openmeteo_quota.sqlite3"
DEFAULT_MAX_WAIT = 0.
_PROCESS_RUN_ID = uuid.uuid4().hex


def current_run_id():
    return os.environ.get('H2RES_OPENMETEO_RUN_ID') or _PROCESS_RUN_ID


@contextmanager
def quota_run(*, inherit=True):
    """Start at zero for a top-level run; child country/sector jobs join it."""
    previous=os.environ.get('H2RES_OPENMETEO_RUN_ID')
    identity=previous if inherit and previous else uuid.uuid4().hex
    os.environ['H2RES_OPENMETEO_RUN_ID']=identity
    try:
        yield identity
    finally:
        if previous is None:os.environ.pop('H2RES_OPENMETEO_RUN_ID',None)
        else:os.environ['H2RES_OPENMETEO_RUN_ID']=previous


class OpenMeteoQuotaWaitError(ValueError):
    """Compatibility marker; current quota paths wait rather than raise this."""


def estimated_calls(params):
    days = (date.fromisoformat(params['end_date']) - date.fromisoformat(params['start_date'])).days + 1
    if days < 1:
        raise ValueError('Weather end date precedes start date')
    def count(value):
        return len(value) if isinstance(value, (list, tuple)) else len(str(value).split(','))
    return (max(1., days / 14.) * max(1., count(params.get('hourly', '')) / 10.)
            * count(params.get('models', 'best_match')) * count(params.get('latitude', '')))


def wait_seconds(seconds, reason):
    print(f'[Open-Meteo] {reason}; waiting {seconds:g}s. Completed weather stays cached.', flush=True)
    if seconds >= 3600:
        print(resume_message(seconds), flush=True)
    remaining = seconds
    elapsed = 0.
    while remaining > 0:
        step = min(30., remaining)
        time.sleep(step)
        remaining -= step
        elapsed += step
        if remaining > 0 and elapsed >= 60:
            print(f'[Open-Meteo] Request budget reset: {remaining:g}s remaining.', flush=True)
            elapsed = 0.


def resume_message(seconds):
    resume = (datetime.now(timezone.utc) + timedelta(seconds=seconds)).astimezone().isoformat(timespec='seconds')
    return (f'[Open-Meteo] Paused for quota recovery; estimated resume {resume}. '
            'Leave the application running to continue automatically, or stop and resume later with the same cache.')


def reserve_request(params, *, database=None, max_wait=DEFAULT_MAX_WAIT, wait=None, clock=None):
    """Reserve a weighted public HTTP attempt, waiting only when a budget is full.

    Call immediately before the network request, after checking the weather cache.
    No coordinates, URLs, credentials or weather data are stored in the ledger.
    """
    cost = estimated_calls(params)
    if not math.isfinite(max_wait) or max_wait < 0:
        raise ValueError('Invalid Open-Meteo quota wait budget')
    identity=current_run_id()
    database = Path(database or os.environ.get('H2RES_OPENMETEO_QUOTA_DB') or DEFAULT_DATABASE)
    database.parent.mkdir(parents=True, exist_ok=True)
    wait = wait or wait_seconds
    clock = clock or time.time
    while True:
        with closing(sqlite3.connect(database, timeout=30.)) as connection, connection:
            connection.execute('CREATE TABLE IF NOT EXISTS run_requests (run_id TEXT NOT NULL, timestamp REAL NOT NULL, cost REAL NOT NULL)')
            connection.execute('CREATE INDEX IF NOT EXISTS openmeteo_run_time ON run_requests(run_id,timestamp)')
            connection.execute('BEGIN IMMEDIATE')
            now = clock()
            connection.execute('DELETE FROM run_requests WHERE timestamp <= ?', (now - max(w[1] for w in WINDOWS),))
            rows = connection.execute('SELECT timestamp, cost FROM run_requests WHERE run_id=? ORDER BY timestamp',(identity,)).fetchall()
            delay, limiting, hour_used, hour_attempts = 0., '', 0., 0
            usage={}
            for name, window, limit in WINDOWS:
                active = [(stamp, weight) for stamp, weight in rows if stamp > now - window]
                used = sum(weight for _, weight in active)
                usage[name]=used
                if name == 'hour':
                    hour_used, hour_attempts = used, len(active)
                if name not in {'minute','hour'}:continue
                excess = used + cost - max(limit,cost)
                if excess <= 1e-8:
                    continue
                expired = 0.
                for stamp, weight in active:
                    expired += weight
                    if expired + 1e-8 >= excess:
                        candidate = max(0., stamp + window - now) + 1.
                        if candidate > delay:
                            delay, limiting = candidate, name
                        break
            if not delay:
                connection.execute('INSERT INTO run_requests VALUES (?, ?, ?)', (identity,now,cost))
        # The transaction and its lock are released before waiting/network I/O.
        if not delay:
            print(f'[Open-Meteo] This run: {len(rows)+1} HTTP attempts / {sum(w for _,w in rows)+cost:.1f} estimated calls; '
                  f'last hour {hour_used+cost:.1f}/4500. Day/month estimates: '
                  f'{usage["day"]+cost:.1f}/{usage["month"]+cost:.1f} (informational).', flush=True)
            return cost
        if max_wait>0:delay=min(delay,max_wait)
        wait(delay, f'{limiting} request budget near limit; next query counts as {cost:.2f} calls')


def retry_after(headers, now=None):
    value=(headers or {}).get('Retry-After')
    if value is None:value=(headers or {}).get('retry-after')
    if value is None:return None
    try:seconds=float(value)
    except (ValueError,TypeError):
        try:
            reset=parsedate_to_datetime(value)
            if reset.tzinfo is None:reset=reset.replace(tzinfo=timezone.utc)
            seconds=(reset-(now or datetime.now(timezone.utc))).total_seconds()
        except (ValueError,TypeError,OverflowError):return None
    return max(1.,seconds) if math.isfinite(seconds) else None


def quota_retry_delay(attempt,headers=None):
    prescribed=retry_after(headers)
    return prescribed if prescribed is not None else min(60.*2**min(max(attempt-1,0),4),900.)


def openmeteo_urlopen(request,params,*,timeout=180,opener=None,wait=None):
    """Heating transport: retry HTTP 429 indefinitely, with the same request."""
    opener=opener or urllib.request.urlopen
    wait=wait or wait_seconds
    attempt=0
    while True:
        reserve_request(params)
        try:
            return opener(request,timeout=timeout)
        except urllib.error.HTTPError as error:
            if error.code!=429:raise
            attempt+=1
            delay=quota_retry_delay(attempt,error.headers)
            error.close()
            wait(delay,f'HTTP 429 quota response; automatic retry {attempt}')
