"""Bounded retries for Windows directory publication locks."""
from pathlib import Path
import time


def failure_details(error,phase):
    """Keep the failing operation and native error fields when str() has no path."""
    import traceback
    result=dict(error_type=type(error).__name__,error=str(error),phase=phase,
                traceback=''.join(traceback.format_exception(type(error),error,error.__traceback__)))
    for name in ('winerror','errno','filename','filename2'):
        value=getattr(error,name,None)
        if value is not None:result[name]=str(value) if name.startswith('filename') else value
    return result


def replace_with_retry(source: Path, destination: Path, attempts=7):
    for attempt in range(attempts):
        try:
            return source.replace(destination)
        except OSError as error:
            if getattr(error, "winerror", None) not in (5, 32, 33) or attempt == attempts - 1:
                raise
            time.sleep(min(0.2 * 2 ** attempt, 2.0))
