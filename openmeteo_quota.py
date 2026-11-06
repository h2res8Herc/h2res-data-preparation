"""Shared rolling request budgets for the public Open-Meteo archive API.

Published limits: https://open-meteo.com/en/pricing (checked 6 November 2026).
Reservations count attempted HTTP requests conservatively, including retries.
SQLite transactions share the allowance across this installation's processes.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from contextlib import closing
import math
import os
from pathlib import Path
import sqlite3
import time

# Keep 10% headroom; a rolling 31-day window is conservative for monthly usage.
WINDOWS = (("minute", 60., 540.), ("hour", 3600., 4500.),
           ("day", 86400., 9000.), ("month", 31 * 86400., 270000.))
DEFAULT_DATABASE = Path(__file__).resolve().parent / ".openmeteo_quota.sqlite3"
DEFAULT_MAX_WAIT = 26 * 3600.


class OpenMeteoQuotaWaitError(ValueError):
    """Local allowance cannot recover within the configured wait budget."""


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
    if any(cost > limit for _, _, limit in WINDOWS):
        raise OpenMeteoQuotaWaitError('A single weather query exceeds the local request budget; split its dates or locations.')
    database = Path(database or os.environ.get('H2RES_OPENMETEO_QUOTA_DB') or DEFAULT_DATABASE)
    database.parent.mkdir(parents=True, exist_ok=True)
    wait = wait or wait_seconds
    clock = clock or time.time
    waited = 0.
    while True:
        with closing(sqlite3.connect(database, timeout=30.)) as connection, connection:
            connection.execute('CREATE TABLE IF NOT EXISTS requests (timestamp REAL NOT NULL, cost REAL NOT NULL)')
            connection.execute('BEGIN IMMEDIATE')
            now = clock()
            connection.execute('DELETE FROM requests WHERE timestamp <= ?', (now - max(w[1] for w in WINDOWS),))
            rows = connection.execute('SELECT timestamp, cost FROM requests ORDER BY timestamp').fetchall()
            delay, limiting, hour_used, hour_attempts = 0., '', 0., 0
            for name, window, limit in WINDOWS:
                active = [(stamp, weight) for stamp, weight in rows if stamp > now - window]
                used = sum(weight for _, weight in active)
                if name == 'hour':
                    hour_used, hour_attempts = used, len(active)
                excess = used + cost - limit
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
                connection.execute('INSERT INTO requests VALUES (?, ?)', (now, cost))
        # The transaction and its lock are released before waiting/network I/O.
        if not delay:
            print(f'[Open-Meteo] Request budget: {hour_attempts + 1} HTTP attempts, '
                  f'{hour_used + cost:.1f}/4500 estimated calls in the last hour.', flush=True)
            return cost
        if waited + delay > max_wait:
            raise OpenMeteoQuotaWaitError(
                f'Open-Meteo local {limiting} budget is near its limit; next query needs {cost:.2f} calls. '
                f'Resuming requires approximately {delay:.0f}s, beyond the remaining wait budget. '
                'Resume later using the same weather cache; completed weather is retained.')
        wait(delay, f'{limiting} request budget near limit; next query counts as {cost:.2f} calls')
        waited += delay
