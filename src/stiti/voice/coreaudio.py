"""Which mic is macOS's default input right now? (CoreAudio via ctypes — microseconds, no PortAudio re-init.)

PortAudio reads the device list once, so an open stream never notices that macOS switched the default mic. 2026-11-11:
he closed the lid on the external monitor → the built-in mic switched off (CoreAudio err -50) → the watchdog reopened
on the then-default iPhone Continuity mic → the lid opened, macOS went back to the MacBook mic, but Stiti stayed on the
far-away iPhone (quiet, not silent, so the watchdog was happy) and never heard “Hey Stiti” again.
Duplex compares this id with the one it opened on and reopens when they differ.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import sys

_SYSTEM_OBJECT = 1                         # kAudioObjectSystemObject
_DEFAULT_INPUT = 0x64496E20                # 'dIn ' kAudioHardwarePropertyDefaultInputDevice
_SCOPE_GLOBAL = 0x676C6F62                 # 'glob'
_ELEMENT_MAIN = 0


class _Addr(ctypes.Structure):
    _fields_ = [("selector", ctypes.c_uint32), ("scope", ctypes.c_uint32), ("element", ctypes.c_uint32)]


_lib = None
_failed = False


def _load():
    global _lib, _failed
    if _lib is None and not _failed:
        try:
            if sys.platform != "darwin":
                raise OSError("not macOS")
            _lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreAudio") or
                                           "/System/Library/Frameworks/CoreAudio.framework/CoreAudio")
            _lib.AudioObjectGetPropertyData.restype = ctypes.c_int32
        except OSError:
            _failed = True
    return _lib


def default_input_id() -> int | None:
    """CoreAudio id of the current default input device; None if unknown (not macOS, no device, any error)."""
    lib = _load()
    if lib is None:
        return None
    addr = _Addr(_DEFAULT_INPUT, _SCOPE_GLOBAL, _ELEMENT_MAIN)
    dev = ctypes.c_uint32(0)
    size = ctypes.c_uint32(ctypes.sizeof(dev))
    try:
        err = lib.AudioObjectGetPropertyData(ctypes.c_uint32(_SYSTEM_OBJECT), ctypes.byref(addr), ctypes.c_uint32(0),
                                             None, ctypes.byref(size), ctypes.byref(dev))
    except Exception:
        return None
    return int(dev.value) if err == 0 and dev.value else None
