"""Probe Python before dependencies are installed; no GUI is opened."""
import json
import struct
import sys


def runtime_info():
    error = ''
    try:
        import tkinter
        tkinter_available = True
    except Exception as exc:
        tkinter_available = False
        error = str(exc)
    version = list(sys.version_info[:3])
    bits = struct.calcsize('P') * 8
    compatible = tuple(version[:2]) >= (3, 10) and bits == 64 and tkinter_available
    return dict(executable=sys.executable, base_executable=getattr(sys, '_base_executable', sys.executable),
                version=version, version_text='.'.join(map(str, version)), bits=bits,
                tkinter_available=tkinter_available, tkinter_error=error, compatible=compatible,
                offline_wheels=compatible and version[:2] == [3, 12])


if __name__ == '__main__':
    print(json.dumps(runtime_info()))
