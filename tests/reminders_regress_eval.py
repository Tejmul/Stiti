"""Reminders are saved, ring, and are never lost (owner, 2026-11-20: "the reminders and all, it should remind me, it is
not doing that"). Offline: fake LLM, fake voice loop, no banners, no Apple Reminders, real clock, made-up content.

Root causes this guards:
  1. after "What's it for?", his NEXT request ("remind me at 10 pm to …", "do I have any alarms?") was swallowed as the
     first reminder's note — no second reminder; the wait also lived only in process memory (lost on restart);
  2. a reminder was NOT spoken after his usual "bye" (silenced → banner only), when the keyboard was idle ("away"),
     or 23:00–07:00 — at the time he chose; nags waited for keyboard activity and gave up silently;
  3. a delivery error / a restart mid-ring left rows 'fired' forever; the checker started only after the models
     loaded and one failing step (a missing table) skipped the rest every tick;
  4. a reminder only shown as a banner (lesson, call, muted) or missed while the Mac was off vanished — now "You
     missed: …" at the next chance, once.

STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp> STITI_EVENTKIT=off python tests/reminders_regress_eval.py
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import datetime, timedelta
from types import SimpleNamespace

db = os.environ.get("STITI_DB", "")
if not db.rstrip("/").split("/")[-1].startswith("stiti_test"):
    sys.exit(f"refusing to run against {db!r}: use a stiti_test* database")
os.environ.setdefault("STITI_LIVE_WARM", "0")
os.environ["STITI_EVENTKIT"] = "off"
os.environ.pop("TELEGRAM_BOT_TOKEN", None)

passed = total = 0


def check(name: str, cond, detail: str = "") -> None:
    global passed, total
    total += 1
    passed += bool(cond)
    print(f"  {'✓' if cond else '✗'} {name}" + (f" — {detail}" if detail and not cond else ""))


from stiti import profile, router                                        # noqa: E402
from stiti.config import CFG                                             # noqa: E402
from stiti.db import one, q                                              # noqa: E402
from stiti.life import alarms as A, proactive as P                       # noqa: E402

llm_calls: list[str] = []


def fake_complete(msgs, **kw):
    llm_calls.append(msgs[-1]["content"])
    return {"text": "Sure, I'll remind you.", "provider": "fake", "model": "fake", "ms": 1}


def fake_stream(msgs, **kw):
    llm_calls.append(msgs[-1]["content"])
    yield "Sure, I'll remind you."


router.complete, router.stream = fake_complete, fake_stream
from stiti.engine import Engine                                          # noqa: E402

profile.set("name", "Kiran")
profile.set("pronouns", "he")


def reset() -> None:
    q("TRUNCATE intents, reminder_nags, tasks RESTART IDENTITY CASCADE")
    A._last.update(id=None, t=0.0, await_label=False)
    llm_calls.clear()


def intents() -> list[dict]:
    return q("SELECT id, kind, fire_at, rrule, state, payload FROM intents ORDER BY id")


def n_intents() -> int:
    return one("SELECT count(*) n FROM intents")["n"]


def local(r: dict) -> datetime:
    return r["fire_at"].astimezone(CFG.tz)


TOMORROW = (datetime.now(CFG.tz) + timedelta(days=1)).date()

# ------------------------------------------------------------------------------------------------ 1. saved
print("1. requests reach alarms.add — through the whole engine")
reset()
e = Engine("voice")
cases = [
    ("remind me tomorrow at 9 about the interview", "reminder", (TOMORROW, 9, 0), "interview"),
    ("set an alarm for 6 am tomorrow", "alarm", (TOMORROW, 6, 0), None),
    ("kal 2 baje yaad dilana", "reminder", (TOMORROW, 14, 0), None),
    ("can you remind me tomorrow at 10 am to call the bank", "reminder", (TOMORROW, 10, 0), "call the bank"),
    ("remind me in 10 minutes to check the oven", "reminder", None, "check the oven"),
    ("wake me up tomorrow at 7", "alarm", (TOMORROW, 7, 0), None),
    ("Give me a reminder tomorrow morning at 8 for the exam.", "reminder", (TOMORROW, 8, 0), "exam"),
    ("remind me tomorrow at noon to submit the form", "reminder", (TOMORROW, 12, 0), "submit the form"),  # was 9 AM
]
for text, kind, when, label in cases:
    A.drop_label_wait()
    before = n_intents()
    r = e.turn(text)
    rows = intents()
    new = rows[-1] if len(rows) > before else None
    ok = new is not None and len(rows) == before + 1 and new["kind"] == kind
    if ok and when:
        ok = (local(new).date(), local(new).hour, local(new).minute) == when
    if ok and label:
        ok = label in (new["payload"].get("label") or "")
    check(f"{text!r} → one {kind}" + (f" '{label}'" if label else ""), ok and not llm_calls, f"{r} | {new and new['payload']}")
    llm_calls.clear()

print("questions about reminders LIST them, never create one")
A.drop_label_wait()
for text in ("what reminders do I have?", "what about the reminders?", "do I have any alarms?",
             "Can you tell me about the reminders I have today?", "any reminders for tomorrow?", "show my alarms"):
    before = n_intents()
    r = e.turn(text)
    check(f"{text!r} → listed, nothing created", n_intents() == before and ("interview" in r or "alarm" in r.lower()), r)

print("after “What's it for?” a new request or a question is never swallowed as the note")
reset()
e = Engine("voice")
r1 = e.turn("set a reminder for tomorrow 9 am")
check("no note → she asks what it's for", r1.rstrip().endswith("?") and A.awaiting_label(), r1)
r2 = e.turn("remind me tomorrow at 10 pm to take my medicine")
rows = intents()
check("…a new request makes a SECOND reminder", len(rows) == 2 and "medicine" in (rows[1]["payload"].get("label") or ""),
      f"{r2} | {[x['payload'].get('label') for x in rows]}")
check("…and the first one did not get it as its note", not rows[0]["payload"].get("label"), str(rows[0]["payload"]))
e.turn("set a reminder for tomorrow at 11 am")
before = n_intents()
r3 = e.turn("do I have any alarms?")
check("…a question about them is answered, not saved as a note",
      n_intents() == before and not intents()[-1]["payload"].get("label") and "medicine" in r3, r3)
e.turn("set a reminder for tomorrow at noon")
r4 = e.turn("Call mom")
check("…a plain answer still becomes the note", intents()[-1]["payload"].get("label") == "Call mom", r4)

print("the open “What's it for?” survives a restart (the app restarts often)")
reset()
A.create("remind me tomorrow at 4 pm")
A._last.update(id=None, t=0.0, await_label=False)          # a fresh process
check("awaiting after restart (kept in the row)", A.awaiting_label())
A.set_label("to submit the form")
check("…his answer becomes the note", intents()[-1]["payload"].get("label") == "submit the form"
      and not A.awaiting_label() and "await_label" not in intents()[-1]["payload"], str(intents()[-1]["payload"]))

print("the note can come before the command; questions are never notes")
reset()
r = A.create("just note it down in my list and remind me tomorrow at 10 pm")
check("'… and remind me at 10' keeps the words before it", intents()[-1]["payload"].get("label") == "note it down in my list",
      f"{r} | {intents()[-1]['payload']}")
reset()
r = A.create("Can you set a reminder tomorrow at 10 p.m.?")
check("'Can you set a reminder …?' has no note 'Can you'", not intents()[-1]["payload"].get("label"), r)
reset()
r = A.create("please set a reminder for tomorrow 7 pm to go to the gym")
check("'… for 7 pm to go to the gym' → note 'go to the gym'", intents()[-1]["payload"].get("label") == "go to the gym", r)
reset()
r = A.create("remind me tomorrow at 9 am")
check("a nameless reminder still says when he set it", intents()[-1]["payload"]["say"].startswith("the reminder you set at"),
      intents()[-1]["payload"]["say"])

print("a request the classifier guesses wrong still reaches the alarm code")
reset()
import stiti.engine as E_mod                                             # noqa: E402
orig_decide = E_mod.decide


def chat_decide(text, qvec):
    d = orig_decide(text, qvec)
    d.answers["domain"] = "chat"
    return d


E_mod.decide = chat_decide
try:
    e = Engine("text")

    def reminders_at() -> list[int]:
        return [local(x).hour for x in intents() if x["kind"] in ("reminder", "alarm")]

    r = e.turn("Okay, I have an exam tomorrow, so keep a reminder for tomorrow at 7 am")
    check("'…, so keep a reminder for tomorrow at 7 am' (judged chat) → a 7 AM reminder, no LLM",
          reminders_at() == [7] and not llm_calls, f"{r} | {reminders_at()} | {llm_calls[:1]}")
    llm_calls.clear()
    r = e.turn("can you set an alarm for tomorrow 5:30 am")
    check("'can you set an alarm …' (judged chat) → the alarm, no LLM", sorted(reminders_at()) == [5, 7] and not llm_calls,
          f"{r} | {reminders_at()}")
    r = e.turn("remind me what I said about the exam")
    check("'remind me what I said' (no time) is NOT a reminder", len(reminders_at()) == 2, r)
finally:
    E_mod.decide = orig_decide

# ------------------------------------------------------------------------------------------------ 2. ring
print("2. delivery: his reminder is SAID, even after 'bye', with an idle keyboard, at night")
import stiti.app as app_mod                                              # noqa: E402
from stiti.app import StitiApp                                           # noqa: E402

banners: list[str] = []
app_mod.subprocess = SimpleNamespace(Popen=lambda args, **k: banners.append(args[-1]), run=lambda *a, **k: None)
P.in_call = lambda: False
said: list[tuple[str, dict]] = []


class FakeLoop:
    def __init__(self):
        self.paused, self.silenced, self.awake, self.duplex = threading.Event(), False, False, None
        self.engine = SimpleNamespace(last_nudge=None)

    def say(self, text, mood="calm", *, nudge=False):
        if self.silenced and nudge:
            return
        said.append((text, {"nudge": nudge}))


class FakeApp:
    SCHED_TICK_S, BOOT_WAIT_S, MISSED_CHECK_S = 0.05, 0, 0.05
    for _n in ("_fire", "_fire_one", "_deliver", "_nag", "_step", "_tell_missed", "_busy_speaking", "_scheduler",
               "_start_scheduler", "_scheduler_watchdog"):
        locals()[_n] = getattr(StitiApp, _n)
    _weather = staticmethod(lambda: None)
    _mail_scan = staticmethod(lambda: None)

    def __init__(self):
        self.loop, self.stop, self.rang = FakeLoop(), threading.Event(), []

    def _ring(self, row):
        self.rang.append(row["id"])

    def _health(self):
        pass

    def _sync_reminders(self):
        raise RuntimeError("Reminders app unreachable")          # a failing step must not stop the others

    def _sleep_due(self, now, busy):
        return False

    def _nap_due(self, busy):
        return False

    def _bg(self, fn):
        pass


def wait_said(n: int = 1, s: float = 1.0) -> None:
    t = time.time()
    while len(said) < n and time.time() - t < s:
        time.sleep(0.01)


def due_reminder(say_text: str, *, mins_ago: float = 0.2, by: str | None = None, user_set: bool = True) -> int:
    p = {"say": say_text, "label": say_text, "kind": "reminder"} | ({"by": by} if by else {})
    return one("""INSERT INTO intents(kind, fire_at, payload, user_set) VALUES ('reminder', now() - make_interval(secs => %s),
                  %s, %s) RETURNING id""", (mins_ago * 60, json.dumps(p), user_set))["id"]


app = FakeApp()
reset()
app.loop.silenced = True                                     # he said "bye" earlier
due_reminder("call the bank")
orig_quiet = A.quiet_now
A.quiet_now = lambda t=None: True                            # and it's 11:30 PM
try:
    app._fire(False)                                         # keyboard idle for an hour ("not present")
    wait_said()
    check("said out loud after 'bye', keyboard idle, late night", said and said[0][0] == "Reminder: call the bank"
          and said[0][1]["nudge"] is False, str(said))
    check("…banner too", any("call the bank" in b for b in banners), str(banners))
    check("…and it is NOT marked missed (he heard it)", not A.missed_summary(mark=False))
    nag = one("SELECT channels FROM reminder_nags")
    check("…its repeat is armed (nag)", nag and nag["channels"] == ["voice"], str(nag))
    said.clear()
    due_reminder("leave for the exam", by="noticed")       # one he said yes to (D49: 90 min before an 8 AM exam)
    app._fire(False)
    wait_said()
    check("a reminder he said yes to (D49) is spoken at its time too, night or not", said
          and "leave for the exam" in said[0][0], str(said))
finally:
    A.quiet_now = orig_quiet
said.clear()
q("TRUNCATE intents, reminder_nags RESTART IDENTITY CASCADE")
r = app._deliver("Time for a break?", "break", True)
check("her OWN nudges still respect 'bye' (banner only)", r == "notification" and not said, f"{r} {said}")
app.loop.silenced = False

print("repeats (nags): an idle keyboard is not 'away'; a locked screen is")
reset()
due_reminder("drink water")
A.quiet_now = lambda t=None: False
try:
    app._fire(False)
    wait_said()
    said.clear()
    q("UPDATE reminder_nags SET next_at = now() - interval '1 second'")
    app._nag(False, False)
    wait_said()
    check("keyboard idle → repeated anyway", said and "drink water" in said[0][0]
          and one("SELECT sent FROM reminder_nags")["sent"] == 2, str(said))
    said.clear()
    q("UPDATE reminder_nags SET next_at = now() - interval '1 second'")
    app._nag(False, True)
    time.sleep(0.05)
    check("screen locked → waits (not counted)", not said and one("SELECT sent FROM reminder_nags")["sent"] == 2)
finally:
    A.quiet_now = orig_quiet

print("in a lesson / on a call / muted → banner now, “You missed: …” at the next chance, once")
reset()
P.in_call = lambda: True
due_reminder("pay the hostel fee")
A.quiet_now = lambda t=None: False
try:
    app._fire(True)
    time.sleep(0.05)
finally:
    P.in_call = lambda: False
    A.quiet_now = orig_quiet
check("on a call: not spoken over it", not said, str(said))
m = A.missed_summary(mark=False)
check("…kept as unheard", m and m.startswith("You missed:") and "pay the hostel fee" in m, m)
g = Engine("voice").greet()
check("the wake greeting says it first", "You missed:" in g and "hostel fee" in g, g)
check("…only once", A.missed_summary(mark=False) is None and "You missed" not in Engine("voice").greet())
reset()
app.loop.paused.set()                                        # "Listening" off in the menu
due_reminder("call grandma")
app._fire(True)
app.loop.paused.clear()
check("muted: kept for later too", "call grandma" in (A.missed_summary(mark=False) or ""))
app.loop.awake = True
app._tell_missed()
wait_said()
check("…told while she's awake with him (scheduler path)", said and "You missed:" in said[-1][0] and "grandma" in said[-1][0],
      str(said))
app.loop.awake = False
said.clear()

print("missed while the Mac was off → told, not silently expired")
reset()
stale = one("""INSERT INTO intents(kind, fire_at, payload) VALUES ('reminder', now() - interval '13 hours',
               '{"say": "submit the assignment", "label": "submit the assignment", "kind": "reminder"}') RETURNING id""")["id"]
alarm = one("""INSERT INTO intents(kind, fire_at, payload) VALUES ('alarm', now() - interval '3 hours',
               '{"say": "Wake up, it''s time!", "kind": "alarm"}') RETURNING id""")["id"]
deliver, missed = A.due()
check("13 h late reminder and 3 h late alarm → missed, not rung", {stale, alarm} == {r["id"] for r in missed} and not deliver)
m = A.missed_summary()
check("…told: 'You missed: … reminder (submit the assignment)' + the alarm", m and m.startswith("You missed:")
      and "submit the assignment" in m and "alarm" in m, m)
check("…once", A.missed_summary() is None)

print("a delivery that fails is not lost; a restart mid-ring is recovered")
reset()
rid = due_reminder("book the cab")
orig_nag_start = A.nag_start
A.nag_start = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("relation reminder_nags does not exist"))
try:
    app._fire(True)
finally:
    A.nag_start = orig_nag_start
st = one("SELECT state, payload FROM intents WHERE id=%s", (rid,))
check("a failing step after delivery → row done, not stuck 'fired'", st["state"] == "done", st["state"])
check("…and kept to tell", "book the cab" in (A.missed_summary(mark=False) or ""))
reset()
fresh = one("""INSERT INTO intents(kind, fire_at, payload, state, last_fired_at) VALUES ('alarm', now() - interval '4 minutes',
               '{"say": "Wake up, it''s time!", "kind": "alarm"}', 'fired', now() - interval '4 minutes') RETURNING id""")["id"]
old = one("""INSERT INTO intents(kind, fire_at, payload, state, last_fired_at) VALUES ('alarm', now() - interval '3 hours',
             '{"say": "Wake up, it''s time!", "kind": "alarm"}', 'fired', now() - interval '3 hours') RETURNING id""")["id"]
again, gone = A.recover_stuck()
check("cut off 4 min ago → fires again", one("SELECT state FROM intents WHERE id=%s", (fresh,))["state"] == "pending"
      and again == 1)
check("cut off 3 h ago → expired + told as missed", one("SELECT state FROM intents WHERE id=%s", (old,))["state"] == "expired"
      and gone == 1 and "alarm" in (A.missed_summary(mark=False) or ""))

print("the checker: runs every few seconds, survives a failing step, restarts if it dies")
reset()
said.clear()
orig_tick, orig_tracker = P.tick, P.PresenceTracker
P.tick = lambda *a, **k: []
P.PresenceTracker = lambda: SimpleNamespace(sample=lambda: SimpleNamespace(present=True, locked=False))
orig_nags_due = A.nags_due
A.nags_due = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("relation reminder_nags does not exist"))
app2 = FakeApp()
try:
    app2._start_scheduler()
    time.sleep(0.2)
    due_reminder("stretch", mins_ago=0)
    t0 = time.time()
    while not said and time.time() - t0 < 2:
        time.sleep(0.02)
    check("a reminder that falls due is said within a tick, though another step keeps failing",
          said and said[0][0] == "Reminder: stretch", str(said))
    check("heartbeat is fresh", time.time() - app2._sched_beat < 1)
    app2.stop.set()
    app2._sched_thread.join(2)
    app2.stop.clear()
    check("watchdog restarts a dead checker", app2._scheduler_watchdog() and app2._sched_thread.is_alive())
    app2.stop.set()
    app2._sched_thread.join(2)
finally:
    A.nags_due, P.tick, P.PresenceTracker = orig_nags_due, orig_tick, orig_tracker
check("the menubar app starts the checker before the models load",
      StitiApp.__init__.__code__.co_names.index("_start_scheduler") < StitiApp.__init__.__code__.co_names.index("_boot"))

print(f"\n{passed}/{total} passed")
sys.exit(0 if passed == total else 1)
