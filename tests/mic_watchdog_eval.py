"""Mic watchdog eval (headless: no sound device, PortAudio is faked).

2026-11-11 bug: Stiti.app ran 12 h with a dead mic stream (no callbacks, no error), so everything he said — including
his to-do list — was never heard. Duplex.health()/heal() must notice a stalled or digitally-silent mic, reopen it on
the current devices, back off while it stays dead, and never touch a healthy stream.
"""
from __future__ import annotations

import os
import sys
import tempfile

import numpy as np

os.environ.setdefault("STITI_HOME", tempfile.mkdtemp())

from stiti.voice import duplex as D                                    # noqa: E402

passed = total = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, total
    total += 1
    passed += bool(cond)
    print(f"  {'✓' if cond else '✗'} {name}" + (f" — {detail}" if detail and not cond else ""))


class FakeStream:
    made = 0

    def __init__(self, *a, **k):
        FakeStream.made += 1
        self.active, self.closed, self.latency = False, False, (0.01, 0.01)

    def start(self): self.active = True
    def abort(self): self.active = False
    def close(self): self.closed = True


class FakeSD:
    inits = 0
    Stream = FakeStream

    @staticmethod
    def _terminate(): pass

    @classmethod
    def _initialize(cls): cls.inits += 1


class FakeAPM:
    def set_stream_delay_ms(self, ms): pass


D.sd = FakeSD                                     # never opens a real device


def make() -> D.Duplex:
    dx = D.Duplex.__new__(D.Duplex)
    dx.on_mic, dx.aec, dx.apm = (lambda x: None), True, FakeAPM()
    dx._init_playback()
    dx.stream = dx._new_stream()
    dx.__enter__()
    return dx


def feed(dx: D.Duplex, sound: bool, at: float) -> None:
    """One audio callback at monotonic time `at` (frames != BLOCK → the APM is skipped)."""
    D.time.monotonic = lambda: at
    try:
        n = 96
        mic = (np.full((n, 1), 0.01, dtype=np.float32) if sound else np.zeros((n, 1), dtype=np.float32))
        dx._cb(mic, np.zeros((n, 1), dtype=np.float32), n, None, None)
    finally:
        D.time.monotonic = _real_mono


_real_mono = D.time.monotonic
t0 = _real_mono()

# ---- healthy stream is left alone ----
dx = make()
feed(dx, True, t0 + 1.0)
check("healthy mic → health() is None", dx.health(t0 + 1.5) is None)
check("healthy mic → heal() does nothing", dx.heal(t0 + 1.5) is None and dx.reopens == 0)
check("a quiet room (low but non-zero signal) is healthy", (feed(dx, True, t0 + 40), dx.health(t0 + 41))[1] is None)

# ---- stalled stream (no callbacks: Mac woke up, device vanished) ----
dx = make()
feed(dx, True, t0 + 1.0)
check("2 s without callbacks is still fine", dx.health(t0 + 3.0) is None)
why = dx.health(t0 + 5.0)
check("4 s without callbacks → stalled", why is not None and "no audio" in why, str(why))
old, inits = dx.stream, FakeSD.inits
why = dx.heal(t0 + 5.0)
check("heal() reopens a stalled stream", why is not None and dx.reopens == 1)
check("old stream aborted + closed", old.closed and not old.active)
check("new stream started", dx.stream is not old and dx.stream.active)
check("PortAudio re-initialised (follows the current default mic)", FakeSD.inits == inits + 1)

# ---- stopped stream ----
dx = make()
feed(dx, True, t0 + 1.0)
dx.stream.active = False
check("inactive stream → 'stopped'", "stopped" in (dx.health(t0 + 1.2) or ""))

# ---- digitally silent mic ----
dx = make()
feed(dx, True, t0 + 0.5)
for i in range(1, 32):
    feed(dx, False, t0 + 0.5 + i)
check("29 s of pure zeros is not yet flagged", (dx.health(t0 + 29.0)) is None)
why = dx.health(t0 + 32.0)
check("31 s of pure zeros → flagged", why is not None and "silence" in why, str(why))
feed(dx, True, t0 + 32.5)
check("one real sound clears the silence flag", dx.health(t0 + 32.6) is None)

# ---- backoff while it stays dead, reset when it comes back ----
dx = make()
feed(dx, True, t0 + 0.1)
D.time.monotonic = lambda: t0 + 5.0
first = dx.heal(t0 + 5.0)
D.time.monotonic = _real_mono
check("first dead check reopens at once", first is not None and dx.reopens == 1)
# after a reopen the 3 s grace must NOT count as recovery
check("grace window after reopen is not 'healthy'", dx.health(t0 + 6.0) is None and dx._streak == 1
      and (dx.heal(t0 + 6.0) is None and dx._streak == 1))
dx._opened_at = t0 + 5.0                          # pin (the reopen stamped real time)
check("still dead 10 s later → waits (30 s gap)", dx.heal(t0 + 15.0) is None and dx.reopens == 1)
check("still dead 31 s later → reopens again", dx.heal(t0 + 36.0) is not None and dx.reopens == 2)
dx._opened_at = t0 + 36.0
check("then waits 60 s, not 30", dx.heal(t0 + 70.0) is None and dx.heal(t0 + 97.0) is not None and dx.reopens == 3)
dx._opened_at = t0 + 97.0
feed(dx, True, t0 + 98.0)
dx.heal(t0 + 98.5)
check("real sound after reopen → streak resets", dx._streak == 0)
gaps = [min(D.REOPEN_EVERY_S * 2 ** max(k - 1, 0), D.REOPEN_MAX_S) for k in range(12)]
check("backoff capped at 10 min", max(gaps) == D.REOPEN_MAX_S)

# ---- reopen failure is reported, never raised ----
dx = make()
feed(dx, True, t0 + 0.1)


class Boom(FakeStream):
    def start(self): raise RuntimeError("no input device")


FakeSD.Stream = Boom
try:
    why = dx.heal(t0 + 10.0)
finally:
    FakeSD.Stream = FakeStream
check("failed reopen → reason says so, no exception", why is not None and "reopen failed" in why, str(why))

# ---- the loop wires it in ----
src = open(os.path.join(os.path.dirname(__file__), "..", "src", "stiti", "voice", "loop.py")).read()
check("voice loop calls heal() on idle ticks", "d.heal()" in src and "_tutor_active()" in src)

print(f"mic watchdog: {passed}/{total} checks passed")
sys.exit(0 if passed == total else 1)
