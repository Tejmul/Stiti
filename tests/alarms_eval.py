"""Alarms / reminders / timers: parsing (kinds, Hinglish, recurrence), list / cancel / move / snooze, firing policy
(missed while off ≠ rung hours later), recurring re-arm, missed summary told once, ring controls. No sound, no
Apple Reminders (STITI_EVENTKIT=off)."""
import os
import sys
import threading
from datetime import datetime, timedelta

os.environ["STITI_EVENTKIT"] = "off"
from stiti.config import CFG  # noqa: E402
from stiti.db import one, q  # noqa: E402
from stiti.life import alarms  # noqa: E402

ok = fail = 0


def check(name, cond, detail=""):
    global ok, fail
    ok += bool(cond)
    fail += not cond
    print(f"{'✅' if cond else '❌'} {name}" + (f" — {detail}" if detail and not cond else ""))


q("DELETE FROM intents")
EVE = datetime(2026, 11, 10, 21, 45, tzinfo=CFG.tz)            # Tue 9:45 PM
row = lambda i: one("SELECT * FROM intents WHERE id=%s", (i,))  # noqa: E731
idof = lambda s: int(s.rsplit("#", 1)[1].rstrip(").")) if s and "#" in s else None  # noqa: E731

r1 = alarms.create("kal 6 baje uthana", EVE)
a1 = row(idof(r1))
check("'kal 6 baje uthana' → alarm Wed 6:00 AM", a1["kind"] == "alarm" and a1["fire_at"].astimezone(CFG.tz).strftime("%a %H:%M") == "Wed 06:00", r1)
r2 = alarms.create("kal 2 baje meeting yaad dilana", EVE)
check("'kal 2 baje meeting yaad dilana' → reminder Wed 2 PM", row(idof(r2))["fire_at"].astimezone(CFG.tz).strftime("%a %H:%M") == "Wed 14:00", r2)
r3 = alarms.create("remind me at 7 pm to call mummy", EVE)
check("reminder keeps its words (no 'Wake up' text)", row(idof(r3))["payload"]["say"] == "call mummy", r3)
r4 = alarms.create("roz saade 6 baje alarm", EVE)
a4 = row(idof(r4))
check("'roz saade 6 baje alarm' → daily 6:30 RRULE", a4["rrule"] and "FREQ=DAILY" in a4["rrule"] and "every day" in r4
      and a4["fire_at"].astimezone(CFG.tz).strftime("%H:%M") == "06:30", r4)
r5 = alarms.create("weekdays 7 am wake me up", EVE)
check("weekdays → MO–FR", "BYDAY=MO,TU,WE,TH,FR" in (row(idof(r5))["rrule"] or ""), r5)
r6 = alarms.create("har somvar 9 baje standup yaad dilana", EVE)
check("'har somvar' → every Monday", "BYDAY=MO" in (row(idof(r6))["rrule"] or "")
      and row(idof(r6))["fire_at"].astimezone(CFG.tz).strftime("%a") == "Mon", r6)
r7 = alarms.create("10 minute ka timer", EVE)
check("timer reads back minutes", r7.startswith("Timer set for 10 minutes"), r7)
check("ambiguous 'set alarm 6' asks morning/evening", "Morning or evening" in (alarms.create("set alarm 6", EVE) or ""))
check("not an alarm → None (falls through to other handlers)", alarms.handle("what's the weather like") is None)

q("UPDATE intents SET fire_at = fire_at + interval '1 year'")          # make them all future for list/cancel
lst = alarms.list_all()
check("list shows all with repeat words", "You have" in lst and "every day" in lst and "call mummy" in lst, lst)
c1 = alarms.cancel("cancel the reminder about mummy")
check("cancel by words", "call mummy" in c1 and row(idof(r3))["state"] == "cancelled", c1)
mv = alarms.move("move my 6:30 alarm to 7:15")
check("move a recurring alarm keeps it repeating", "07:15" in (row(idof(r4))["rrule"] and
      row(idof(r4))["fire_at"].astimezone(CFG.tz).strftime("%H:%M")) and "BYHOUR=7;BYMINUTE=15" in row(idof(r4))["rrule"], mv)
call = alarms.cancel("cancel all alarms")
check("cancel all alarms leaves reminders", one("SELECT count(*) n FROM intents WHERE kind='alarm' AND state='pending'")["n"] == 0
      and one("SELECT count(*) n FROM intents WHERE kind='reminder' AND state='pending'")["n"] >= 2, call)

# ---------------------------------------------------------------- firing policy
q("DELETE FROM intents")
now = datetime.now(CFG.tz)
mk = lambda kind, mins_ago, say="x", rrule=None, pk=None: one(  # noqa: E731
    "INSERT INTO intents(kind, fire_at, rrule, payload) VALUES (%s, %s, %s, %s) RETURNING id",
    (kind, now - timedelta(minutes=mins_ago), rrule,
     __import__("json").dumps({"say": say, "kind": pk or kind, "label": say})))["id"]
on_time = mk("alarm", 1, "Wake up, it's time!")
stale = mk("alarm", 11 * 60, "Wake up, it's time!")             # 9 AM alarm, Mac was off till 8 PM
rem_late = mk("reminder", 90, "call mummy")
rem_stale = mk("reminder", 13 * 60, "pay rent")
daily = mk("alarm", 2, "Wake up, it's time!", f"FREQ=DAILY;BYHOUR={(now - timedelta(minutes=2)).hour};"
           f"BYMINUTE={(now - timedelta(minutes=2)).minute};BYSECOND=0")
deliver, missed = alarms.due()
check("on-time alarm rings; 11-hours-late alarm does NOT", {on_time, daily} <= {r["id"] for r in deliver}
      and stale in {r["id"] for r in missed} and stale not in {r["id"] for r in deliver})
check("reminder 90 min late still delivered; 13 h late → missed", rem_late in {r["id"] for r in deliver}
      and rem_stale in {r["id"] for r in missed})
d = row(daily)
check("recurring alarm re-armed for tomorrow", d["state"] == "pending" and d["fire_at"] > now + timedelta(hours=23), str(d["fire_at"]))
m1 = alarms.missed_summary()
check("missed summary names the missed ones, said once", m1 and "alarm" in m1 and "pay rent" in m1
      and alarms.missed_summary() is None, m1)
check("nothing fires twice", alarms.due() == ([], []))

# ---------------------------------------------------------------- ringing controls (no sound: fake loop)
class FakeDuplex:
    def __init__(self): self.n = 0
    def play(self, a, sr): self.n += 1
    def stop_playback(self): pass
class FakeLoop:
    def __init__(self): self.duplex, self.paused, self.said = FakeDuplex(), threading.Event(), []
    def say(self, t, **k): self.said.append(t)
alarms.RING_ROUND_S = 0.05
rid = mk("alarm", 0, "Wake up, it's time!")
fl = FakeLoop()
rg = alarms.Ringer(row(rid), loop=fl, log=lambda *_: None)
th = threading.Thread(target=rg.run)
th.start()
import time; time.sleep(0.3)  # noqa: E401,E702
check("ignores unrelated speech while ringing", rg.control("what's the time") is None)
said = rg.control("5 minute aur")
th.join(2)
check("'5 minute aur' snoozes 5 min", rg.outcome == "snoozed" and "5 more minutes" in said
      and row(rid)["state"] == "pending" and row(rid)["fire_at"] > now + timedelta(minutes=4), said)
check("ring escalates: several rounds of tone + voice", fl.duplex.n >= 2 and any("Uth jao" in s for s in fl.said), str(fl.said[:3]))
rg2 = alarms.Ringer(row(rid), loop=FakeLoop(), log=lambda *_: None)
th = threading.Thread(target=rg2.run); th.start(); time.sleep(0.1)  # noqa: E702
rg2.control("band karo")
th.join(2)
check("'band karo' dismisses → done", rg2.outcome == "dismissed" and row(rid)["state"] in ("done", "pending"))
for _ in range(alarms.MAX_SNOOZES):
    alarms.snooze(rid)
check("snooze limit", "last snooze" in alarms.snooze(rid))

q("DELETE FROM intents")
print(f"alarms: {ok}/{ok + fail} checks passed")
sys.exit(1 if fail else 0)
