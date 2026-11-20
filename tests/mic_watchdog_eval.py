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
MIC = {"id": 89}                                  # the fake "macOS default input" CoreAudio id
D._default_input_id = lambda: MIC["id"]
TR = {89: "bltn", 120: "ccwd", 117: "blue", 200: "usb "}      # fake CoreAudio transport types per device id
D._transport = lambda i: TR.get(i)
D.mic_mode = lambda: MODE["v"]
MODE = {"v": "auto"}
BUILTIN = {"v": (4, "MacBook Pro Microphone")}
D.builtin_mic = lambda: BUILTIN["v"]


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

# ---- a reopen that doesn't bring sound back → restart the process (2026-11-11, CoreAudio err -50) ----
dx = make()
feed(dx, True, t0 + 0.1)
check("no reopen yet → never 'failed'", not dx.reopen_failed(t0 + 100))
D.time.monotonic = lambda: t0 + 10.0
dx.heal(t0 + 10.0)
D.time.monotonic = _real_mono
dx._opened_at = t0 + 10.0
check("just reopened → give it a few seconds", not dx.reopen_failed(t0 + 12.0))
check("6 s after the reopen, still silent → failed", dx.reopen_failed(t0 + 17.0))
feed(dx, True, t0 + 13.0)
check("real sound after the reopen → recovered", not dx.reopen_failed(t0 + 20.0))

import tempfile as _tf                                            # noqa: E402
from stiti.config import CFG                                      # noqa: E402
from stiti.voice import loop as L                                 # noqa: E402
(CFG.home / "logs" / "mic_restarts").unlink(missing_ok=True)
now = 1_000_000.0
check("first mic restart allowed", L._may_restart(now))
check("second allowed", L._may_restart(now + 60))
check("third within 10 min refused (no restart loop on a muted mic)", not L._may_restart(now + 120))
check("allowed again after the window", L._may_restart(now + 700))

# ---- macOS switched the default mic (2026-11-11: lid closed → iPhone mic → lid opened, she stayed on the iPhone) ----
MIC["id"] = 89
dx = make()
feed(dx, True, t0 + 0.1)
check("stream remembers the mic it opened on", dx._dev_id == 89)
check("same default mic → healthy", dx.health(t0 + 2.5) is None)
MIC["id"] = 120                                   # lid closed: macOS moved to the iPhone Continuity mic
feed(dx, True, t0 + 3.0)                          # the old stream still delivers (quiet) sound — no other alarm
check("checked at most every 2 s (no ask 0.5 s later)", dx.health(t0 + 3.0) is None)
why = dx.heal(t0 + 5.0)
check("default mic changed → heal() reopens", why is not None and why.startswith(D.SWITCHED) and dx.reopens == 1,
      str(why))
check("… on the new default mic", dx._dev_id == 120 and dx.stream.active)
check("a switch is not a dead-mic streak (no backoff)", dx._streak == 0)
MIC["id"] = 89                                    # lid opened: back to the MacBook mic, only 3 s later
feed(dx, True, t0 + 7.5)
why = dx.heal(t0 + 8.0)
check("switching back reopens at once, ignoring the 30 s gap", why is not None and dx.reopens == 2 and dx._dev_id == 89,
      str(why))
check("then healthy again", dx.health(t0 + 10.5) is None and dx.heal(t0 + 13.0) is None and dx.reopens == 2)
MIC["id"] = None                                  # CoreAudio can't tell (no mic / not macOS) → never a false switch
feed(dx, True, t0 + 15.5)
check("unknown default mic → no reopen", dx.health(t0 + 16.0) is None)
MIC["id"] = 89
dx = make()
MIC["id"] = None
dx2 = make()                                      # opened while there was no default mic at all …
MIC["id"] = 89                                    # … then one appeared
feed(dx2, True, t0 + 0.1)
check("opened with no mic, then a mic appears → reopen", dx2.health(t0 + 3.0) == D.SWITCHED)

# ---- D45: a Bluetooth headset is the default mic (he wears AirPods) → listen on the Mac's own mic ----
print("headset as the default mic")
opened = []
_FS = FakeStream.__init__


def _spy_init(self, *a, **k):
    opened.append(k.get("device"))
    _FS(self, *a, **k)


FakeStream.__init__ = _spy_init
MIC["id"] = 117                                   # AirPods are macOS's default input
dx = make()
check("AirPods default → the stream opens on the Mac's own mic, sound stays on the default output",
      opened[-1] == (4, None) and dx._pinned and dx._on_builtin and dx.mic_name == "MacBook Pro Microphone", str(opened[-1]))
feed(dx, True, t0 + 0.1)
MIC["id"] = 89                                    # macOS flips the default to the MacBook mic …
check("default flips headset → Mac mic: no reopen (she is on the Mac's mic already)",
      dx.health(t0 + 2.5) is None and dx.heal(t0 + 2.6) is None and dx.reopens == 0)
MIC["id"] = 117                                   # … and back (this ping-pong caused 4 reopens on 2026-11-18)
feed(dx, True, t0 + 4.0)
check("…and back to the headset: still no reopen", dx.health(t0 + 5.0) is None and dx.reopens == 0)
MIC["id"] = 200                                   # he plugs in a USB mic and macOS selects it
feed(dx, True, t0 + 7.0)
why = dx.heal(t0 + 8.0)
check("a wired mic becomes the default → reopen on it (not pinned any more)",
      why is not None and why.startswith(D.SWITCHED) and opened[-1] is None and not dx._pinned, f"{why} {opened[-1]}")
MIC["id"] = 89
dx = make()
check("Mac mic is the default → plain default stream, marked as the Mac's mic", opened[-1] is None and dx._on_builtin
      and not dx._pinned)
feed(dx, True, t0 + 0.1)
MIC["id"] = 117                                   # AirPods connect later and take the default
check("AirPods connect later → she stays on the Mac's mic, no reopen", dx.health(t0 + 2.5) is None and dx.reopens == 0)
MIC["id"] = 117
dx = make()
check("pinned again on a fresh start", dx._pinned)
why = None
for k in range(1, 80):                            # the Mac's own mic goes silent (lid closed): pure zeros
    feed(dx, False, t0 + k * 0.5)
    why = why or dx.heal(t0 + k * 0.5)
check("the pinned Mac mic goes dead → reopen on macOS's default (the headset), pin off for a while",
      why is not None and opened[-1] is None and not dx._pinned and dx._no_pin_until > t0, f"{why} {opened[-1]}")
MODE["v"] = "default"
dx = make()
check("STITI_MIC=default → follow macOS (headset mic), never pinned", opened[-1] is None and not dx._pinned)
MODE["v"] = "auto"
BUILTIN["v"] = None
dx = make()
check("no Mac mic in the device list (desktop Mac) → default", opened[-1] is None and not dx._pinned)
BUILTIN["v"] = (4, "MacBook Pro Microphone")
FakeStream.__init__ = _FS
MIC["id"] = 89

from stiti.voice import coreaudio as CA                           # noqa: E402
check("transport type of the real default mic is a 4-letter code or None",
      (lambda t: t is None or len(t) == 4)(CA.transport(CA.default_input_id())))
real = CA.default_input_id()
check("CoreAudio query answers on this Mac (int) or None elsewhere, never raises",
      real is None or (isinstance(real, int) and real > 0), repr(real))

# ---- the loop wires it in ----
src = open(os.path.join(os.path.dirname(__file__), "..", "src", "stiti", "voice", "loop.py")).read()
check("voice loop calls heal() on idle ticks", "d.heal()" in src and "_tutor_active()" in src)
check("voice loop restarts (exit 75) when a reopen fails", "d.reopen_failed()" in src and "os._exit(75)" in src)

print(f"mic watchdog: {passed}/{total} checks passed")
sys.exit(0 if passed == total else 1)
