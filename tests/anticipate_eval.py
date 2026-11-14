"""Anticipating him (D39): weather, the short morning brief, meeting heads-up, reminders that don't give up,
timer vs alarm ring limits. No real network, no real calendar, fake clock.

STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp> STITI_EVENTKIT=off uv run python tests/anticipate_eval.py
"""
from __future__ import annotations

import os
import re
import sys
import time
from datetime import datetime, timedelta

db = os.environ.get("STITI_DB", "")
if not db.rstrip("/").split("/")[-1].startswith("stiti_test"):
    sys.exit(f"refusing to run against {db!r}: use a stiti_test* database")
os.environ.setdefault("STITI_LIVE_WARM", "0")
os.environ.setdefault("STITI_EVENTKIT", "off")
os.environ.pop("STITI_CITY", None)
os.environ.pop("TELEGRAM_BOT_TOKEN", None)

passed = total = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, total
    total += 1
    passed += bool(cond)
    print(f"  {'✓' if cond else '✗'} {name}" + (f" — {detail}" if detail and not cond else ""))


def sentences(text: str) -> int:
    return len([s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s])


from stiti import profile, router                                       # noqa: E402
from stiti.config import CFG                                            # noqa: E402
from stiti.connectors import eventkit, live, weather as W               # noqa: E402
from stiti.db import one, q                                             # noqa: E402
from stiti.life import alarms as A, brief as B, proactive as P          # noqa: E402

q("TRUNCATE tasks, intents, nudges, nudge_arms, reminder_nags RESTART IDENTITY CASCADE")
q("DELETE FROM owner_profile WHERE key IN ('city', 'name', 'call_me')")
profile._all.cache_clear()

# ------------------------------------------------------------------------------------------------ fake network
GEO = {"results": [{"name": "Lisbon", "latitude": 38.72, "longitude": -9.14, "country": "Portugal"}]}
TODAY = datetime.now(CFG.tz).date()


def forecast(temp=24.2, feels=24.0, code=0, hi=31.4, lo=19.0, rain=10, rain2=70, is_day=1):
    return {"current": {"time": f"{TODAY}T09:00", "temperature_2m": temp, "apparent_temperature": feels,
                        "weather_code": code, "is_day": is_day},
            "daily": {"time": [str(TODAY), str(TODAY + timedelta(days=1))], "temperature_2m_max": [hi, 27.6],
                      "temperature_2m_min": [lo, 18.2], "precipitation_probability_max": [rain, rain2],
                      "weather_code": [code, 61]}}


calls: list[str] = []
net = {"fc": forecast(), "down": False}


def fake_fetch(url: str, timeout: float = W.TIMEOUT_S) -> dict:
    calls.append(url)
    if net["down"]:
        raise OSError("offline")
    return GEO if "geocoding" in url else net["fc"]


W._fetch_json = fake_fetch
W.clear_cache()
(CFG.home / "cache" / "geo.json").unlink(missing_ok=True)
MORNING = datetime.now(CFG.tz).replace(hour=9, minute=0, second=0, microsecond=0)

print("weather: parsing + speech")
w = W.parse("Lisbon", forecast())
check("parse: current + today + tomorrow", round(w.temp) == 24 and len(w.days) == 2 and w.days[0].rain == 10
      and w.days[1].hi == 27.6)
line = W.one_liner(w, MORNING)
check("one-liner like a friend", line == "It's 24 and sunny in Lisbon, up to 31 later, no rain.", line)
check("no lists, one sentence", sentences(line) == 1 and "\n" not in line)
wet = W.parse("Lisbon", forecast(code=61, rain=80))
check("raining now → says raining, no 'no rain'", "raining" in W.one_liner(wet, MORNING)
      and "no rain" not in W.one_liner(wet, MORNING), W.one_liner(wet, MORNING))
maybe = W.parse("Lisbon", forecast(rain=60))
check("rain likely → umbrella", "umbrella" in W.one_liner(maybe, MORNING), W.one_liner(maybe, MORNING))
evening = MORNING.replace(hour=19)
check("evening: no 'up to … later'", "later" not in W.one_liner(w, evening), W.one_liner(w, evening))
r = W.speak(w, "rain", 0, MORNING)
check("will it rain today → probably not", r.startswith("Probably not") and "10%" in r, r)
r = W.speak(w, "rain", 1, MORNING)
check("kal baarish → yes, tomorrow 70%", r.startswith("Yes") and "tomorrow" in r and "70%" in r, r)
r = W.speak(W.parse("Lisbon", forecast(temp=34, feels=38, hi=36)), "heat", 0, MORNING)
check("kitni garmi → temp + feels like", r == "It's 34 in Lisbon right now, feels like 38, up to 36 later.", r)
r = W.speak(w, "now", 1, MORNING)
check("tomorrow forecast line", r == "Tomorrow in Lisbon: 18 to 28, rain likely — take an umbrella.", r)
check("0% → plain no", W._rain_answer(0, "Lisbon", "today") == "No — no rain expected in Lisbon today.")
far = W.parse("Lisbon", dict(forecast(), utc_offset_seconds=0))
check("'later' is judged on the city's own clock", "later" not in W.one_liner(far, MORNING.replace(hour=23))
      and "up to 31 later" in W.one_liner(far, MORNING.astimezone(W.timezone.utc).replace(hour=9)))
check("timeout ≤ 1.5 s, cache 30 min", W.TIMEOUT_S <= 1.5 and W.TTL_S == 1800)

print("weather: city, cache, offline")
check("no city set → timezone city, flagged as a guess", W.city() == (CFG.tz.key.split("/")[-1].replace("_", " "), False))
os.environ["STITI_CITY"] = "Porto"
check("STITI_CITY used", W.city() == ("Porto", True))
os.environ.pop("STITI_CITY")
profile.set("city", "Lisbon", "test")
check("profile city wins", W.city() == ("Lisbon", True))
calls.clear()
w1 = W.get()
check("first get fetches geocode + forecast", w1 is not None and len(calls) == 2, str(calls))
w2 = W.get()
check("second get within 30 min → cache, no fetch", w2 is w1 and len(calls) == 2)
check("geocode saved on disk", "lisbon" in (CFG.home / "cache" / "geo.json").read_text())
w1.fetched_at -= W.TTL_S + 5
net["fc"] = forecast(temp=26)
w3 = W.get()
check("after 30 min → refetch (forecast only, geocode cached)", w3 is not None and round(w3.temp) == 26
      and len(calls) == 3, str(calls))
net["down"] = True
w3.fetched_at -= W.TTL_S + 5
w4 = W.get()
check("offline with a recent copy → the stale copy", w4 is w3)
W.clear_cache()
check("offline, nothing cached → None (no exception)", W.get() is None)
check("offline answer is honest", W.answer("what's the weather") == "I can't reach the weather right now.")
n0 = len(calls)
check("cached() never touches the network", W.cached() is None and len(calls) == n0)
net["down"] = False
net["fc"] = forecast()

print("weather: fast path routing (no LLM)")
for t in ("what's the weather", "mausam kaisa hai", "will it rain today", "bahar kitni garmi hai", "kal baarish hogi?",
          "how hot is it outside", "do I need an umbrella today", "weather in Porto tomorrow",
          "Porto mein mausam kaisa hai", "what's the temperature right now"):
    check(f"trigger: {t!r}", W.detect(t) is not None)
for t in ("I'm feeling under the weather", "remind me to carry an umbrella at 5 pm", "what is the temperature of the sun",
          "I love the rain", "add buy umbrella to my todo", "Rahul is a fair-weather friend", "how was your day"):
    check(f"not weather: {t!r}", W.detect(t) is None)
check("named city picked up", W.detect("weather in Porto tomorrow").place == "Porto"
      and W.detect("Porto mein mausam kaisa hai").place == "Porto" and W.detect("how's the weather in the evening").place is None)
for t, c in (("my city is Lisbon", "Lisbon"), ("set my city to new york", "New York"), ("I live in Porto", "Porto"),
             ("main Lisbon mein rehta hoon", "Lisbon"), ("I live in a small flat", None), ("I am in a meeting", None)):
    check(f"city from {t!r} → {c}", W.city_from_text(t) == c, str(W.city_from_text(t)))

from stiti.engine import Engine                                          # noqa: E402

llm_calls: list = []
orig_complete = router.complete
router.complete = lambda *a, **k: llm_calls.append(a) or {"text": "LLM reply", "provider": "fake", "model": "fake"}
try:
    e = Engine("text")
    check("spec_block holds a weather ask (not speculated)", e.spec_block("what's the weather") == "action")
    check("spec_block holds 'my city is …'", e.spec_block("my city is Lisbon") == "action")
    W.clear_cache()
    acks: list[str] = []
    rep = e.turn("what's the weather", now=MORNING, on_ack=acks.append)
    check("engine: weather answered by code", rep.startswith("It's 24 and sunny in Lisbon") and not llm_calls, rep)
    check("engine: cold cache → 'let me look that up' ack", acks == ["web"], str(acks))
    acks.clear()
    rep = e.turn("will it rain tomorrow?", now=MORNING, on_ack=acks.append)
    check("engine: rain tomorrow from cache, no ack", "70%" in rep and acks == [] and not llm_calls, rep)
    check("engine: route fast_path", (e.last_debug or {}).get("route") == "fast_path", str(e.last_debug))
    rep = e.turn("I live in Porto")
    check("engine: city set by voice", "Lisbon" in rep and profile.get("city") == "Lisbon", rep)   # fake geocoder → Lisbon
    profile.set("city", "Lisbon", "test")
    n = one("SELECT count(*) n FROM intents")["n"]
    rep = e.turn("remind me to carry an umbrella tomorrow at 9 am")
    check("engine: umbrella reminder is a reminder, not weather", "chance" not in rep
          and one("SELECT count(*) n FROM intents")["n"] == n + 1, rep)
finally:
    router.complete = orig_complete

print("morning brief: ≤ 3 sentences, never waits on the network")
EV = [{"title": "Standup", "start": MORNING + timedelta(minutes=30), "end": MORNING + timedelta(minutes=45), "all_day": False},
      {"title": "Design review", "start": MORNING + timedelta(hours=5), "end": MORNING + timedelta(hours=6), "all_day": False},
      {"title": "Gym", "start": MORNING + timedelta(hours=9), "end": MORNING + timedelta(hours=10), "all_day": False},
      {"title": "Holiday", "start": MORNING.replace(hour=0), "end": MORNING.replace(hour=23), "all_day": True}]
q("TRUNCATE tasks, intents, nudges RESTART IDENTITY CASCADE")
q("INSERT INTO tasks(title) VALUES ('call the plumber'), ('send the report'), ('buy milk')")
q("""INSERT INTO intents(kind, fire_at, payload) VALUES ('reminder', %s, '{"say":"pay rent","kind":"reminder"}')""",
  (MORNING + timedelta(hours=3),))
wx = W.parse("Lisbon", forecast())
full = B.morning_brief(MORNING, name="Sam", events=lambda now: EV, weather=lambda: wx, headline=lambda: "Rain delays the city marathon")
print("    →", full)
check("full brief: greeting + weather in one sentence",
      full.startswith("Good morning, Sam — it's 24 and sunny in Lisbon, up to 31 later, no rain."), full)
check("full brief: first 2 events only, all-day skipped", "Standup at 9:30" in full and "Design review at 2" in full
      and "Gym" not in full and "Holiday" not in full, full)
check("full brief: to-do + reminder count", "3 to-dos and a reminder" in full, full)
check("full brief: one headline", "In the news: Rain delays the city marathon." in full, full)
check("full brief: ≤ 3 sentences", sentences(full) <= 3, str(sentences(full)))
check("once a day only", B.morning_brief(MORNING, events=lambda now: EV, weather=lambda: wx) is None)
q("TRUNCATE nudges")
bare = B.morning_brief(MORNING, events=lambda now: [], weather=lambda: None, headline=lambda: None)
print("    →", bare)
check("no calendar / weather / news → still short and useful", bare.startswith("Good morning")
      and "3 to-dos" in bare and "first up, call the plumber" in bare and sentences(bare) <= 3, bare)
q("TRUNCATE nudges")
low = B.morning_brief(MORNING, low_energy=True, events=lambda now: EV, weather=lambda: wx, headline=lambda: "X happens today here")
check("low energy: one thing, no news", "Just one thing matters today: call the plumber." in low and "news" not in low, low)
q("TRUNCATE nudges")
q("UPDATE tasks SET status='done'")
q("UPDATE intents SET state='done'")
empty = B.morning_brief(MORNING, events=lambda now: [], weather=lambda: None, headline=lambda: None)
check("empty day said in one line", "open day" in empty and sentences(empty) <= 2, empty)
q("TRUNCATE nudges")
calls.clear()
W.clear_cache()
net["down"] = True
t0 = time.perf_counter()
off = B.morning_brief(MORNING, events=lambda now: [])          # real defaults: weather/headline from caches only
check("offline: brief skips weather silently, no fetch, fast", off is not None and "It's" not in off and not calls
      and time.perf_counter() - t0 < 0.5, off)
net["down"] = False
live._cache[f"{live.GN}?{live.GN_Q}"] = (time.time(), [live.Item("Markets close higher after a quiet week - Reuters", "Reuters", "u")])
check("cached headline read without network", live.cached_headline() == "Markets close higher after a quiet week - Reuters")
live.clear_cache()
check("no cached news → no headline", live.cached_headline() is None)

print("meeting heads-up")
NOW = datetime.now(CFG.tz).replace(hour=14, minute=50, second=0, microsecond=0)
evs = [{"title": "Design review", "start": NOW + timedelta(minutes=10), "all_day": False},
       {"title": "Later sync", "start": NOW + timedelta(minutes=40), "all_day": False},
       {"title": "Company holiday", "start": NOW + timedelta(minutes=10), "all_day": True},
       {"title": "Now-ish", "start": NOW + timedelta(seconds=30), "all_day": False}]
hs = P.meeting_headsups(evs, NOW, set())
check("only the timed event ~10 min away", [t for t, _ in hs] == ["Heads-up — Design review in 10 minutes."], str(hs))
check("already announced → skipped", P.meeting_headsups(evs, NOW, {P.meeting_key(evs[0])}) == [])
check("caught a bit late → says the real minutes", P.meeting_headsups(evs, NOW + timedelta(minutes=6), set())[0][0]
      == "Heads-up — Design review in 4 minutes.")
q("TRUNCATE tasks, intents, nudges, nudge_arms RESTART IDENTITY CASCADE")
orig_eq = eventkit.events_quiet
eventkit.events_quiet = lambda start, end: [e for e in evs if start - timedelta(minutes=1) <= e["start"] <= end]
said: list = []
deliver = lambda text, kind, present: said.append((kind, text)) or "voice"     # noqa: E731
pres = P.Presence(present=True, idle_s=2, locked=False, app="Code", active_minutes=20)
try:
    P.tick(pres, deliver, now=NOW)
    check("tick: heads-up delivered through the nudge path", ("meeting_soon", "Heads-up — Design review in 10 minutes.") in said,
          str(said))
    P.tick(pres, deliver, now=NOW + timedelta(minutes=1))
    check("never twice for the same event", sum(k == "meeting_soon" for k, _ in said) == 1, str(said))
    check("all-day event never announced", not any("holiday" in t for _, t in said))
    said.clear()
    q("TRUNCATE nudges")
    check("busy (mid-conversation) → waits", P.tick(pres, deliver, busy=True, now=NOW) == [] and not said)
    P.disable_from_text("don't remind me about meetings")
    P.tick(pres, deliver, now=NOW)
    check("'don't remind me about meetings' is respected", not said, str(said))
finally:
    eventkit.events_quiet = orig_eq
check("in_call() is a cheap bool", isinstance(P.in_call(), bool))

print("reminders that don't give up")
q("TRUNCATE intents, reminder_nags RESTART IDENTITY CASCADE")
T0 = datetime.now(CFG.tz).replace(microsecond=0)


def mk(say: str, heard: str | None = None) -> dict:
    payload = {"say": say, "label": say, "kind": "reminder", "heard": heard or f"remind me to {say}"}
    import json
    rid = one("INSERT INTO intents(kind, fire_at, payload, state) VALUES ('reminder', %s, %s, 'done') RETURNING id",
              (T0, json.dumps(payload)))["id"]
    return {"id": rid, "kind": "reminder", "payload": payload}


r1 = mk("call mom")
n1 = A.nag_start(r1, "voice", T0)
check("not important by default", not A.is_important(r1["payload"]))
check("nothing due at +1 min", A.nags_due(T0 + timedelta(minutes=1)) == [])
d = A.nags_due(T0 + timedelta(minutes=2))
check("repeat due at +2 min", [x["id"] for x in d] == [n1])
check("2nd delivery text", A.nag_text(d[0]) == "Reminder again: call mom.", A.nag_text(d[0]))
A.nag_sent(n1, "voice", T0 + timedelta(minutes=2))
check("nothing due at +6 min", A.nags_due(T0 + timedelta(minutes=6)) == [])
d = A.nags_due(T0 + timedelta(minutes=7))
check("3rd delivery at +2 then +5 min", [x["id"] for x in d] == [n1])
check("3rd = last nudge", A.nag_text(d[0]) == "Last nudge on this one — call mom.", A.nag_text(d[0]))
A.nag_sent(n1, "notification", T0 + timedelta(minutes=7))
row = one("SELECT sent, next_at, channels, state FROM reminder_nags WHERE id=%s", (n1,))
check("max 3 deliveries, then no next repeat", row["sent"] == 3 and row["next_at"] is None and row["state"] == "open")
check("channels logged per delivery", row["channels"] == ["voice", "voice", "notification"], str(row["channels"]))
check("nothing more ever due", A.nags_due(T0 + timedelta(minutes=60)) == [])
check("…and it's closed as gave_up", one("SELECT state FROM reminder_nags WHERE id=%s", (n1,))["state"] == "gave_up")

r2 = mk("pay the electricity bill", "zaroor remind me to pay the electricity bill at 6")
check("'zaroor' → important", A.is_important(r2["payload"]))
check("'must' / 'don't let me forget' → important", A.IMPORTANT_RX.search("I must submit the form")
      and A.IMPORTANT_RX.search("don't let me forget the keys"))
gaps = [A.nag_gap(k, True) for k in range(1, 8)]
check("important schedule: +2, +5, then every 10 min ×3, then stop",
      [g and int(g.total_seconds() // 60) for g in gaps] == [2, 5, 10, 10, 10, None, None], str(gaps))
check("normal schedule: +2, +5, stop", [A.nag_gap(k, False) and int(A.nag_gap(k, False).total_seconds() // 60)
                                        for k in range(1, 5)] == [2, 5, None, None])
n2 = A.nag_start(r2, "voice", T0)
t, texts = T0, []
for _ in range(10):
    due = A.nags_due(t + timedelta(minutes=10))
    if not due:
        break
    t = due[0]["next_at"]
    texts.append(A.nag_text(due[0]))
    A.nag_sent(n2, "voice", t)
check("important: 6 deliveries in all", one("SELECT sent FROM reminder_nags WHERE id=%s", (n2,))["sent"] == 6)
check("important lines then 'last nudge'", texts[2].startswith("This one's important") and texts[-1].startswith("Last nudge"),
      str(texts))

r3 = mk("take the medicine")
n3 = A.nag_start(r3, "voice", T0)
A.nag_defer(n3, T0 + timedelta(minutes=2))
check("defer (away) doesn't count", one("SELECT sent FROM reminder_nags WHERE id=%s", (n3,))["sent"] == 1
      and A.nags_due(T0 + timedelta(minutes=2, seconds=30)) == [])
check("plain chat is not an ack", A.ack("ok so tell me what is the weather like today", ref=T0 + timedelta(minutes=1)) is None)
rep = A.ack("ok got it", via="voice", ref=T0 + timedelta(seconds=40))
st = one("SELECT state, ack_via, ack_latency_s FROM reminder_nags WHERE id=%s", (n3,))
check("'ok got it' stops it", rep == "Okay, I won't remind you again." and st["state"] == "acked", str(rep))
check("ack channel + latency logged", st["ack_via"] == "voice" and abs(st["ack_latency_s"] - 40) < 1, str(st))
check("acked → never repeats", A.nags_due(T0 + timedelta(minutes=30)) == [])
check("'ok' with nothing open → not an ack", A.ack("ok", ref=T0 + timedelta(minutes=1)) is None)
r4 = mk("water the plants")
n4 = A.nag_start(r4, "voice", T0)
check("too long after (asleep window 90 s) → not an ack",
      A.ack("haan", ref=T0 + timedelta(seconds=120), window_s=A.NAG_ACK_ASLEEP_S) is None)
check("'ho gaya' → 'Nice, done.'", A.ack("ho gaya", ref=T0 + timedelta(seconds=60)) == "Nice, done.")
for t in ("ok", "okay", "done", "got it", "haan", "theek hai", "Okay Stiti, got it", "thanks"):
    check(f"ack word: {t!r}", A.ack_matches(t))
r5 = mk("stretch")
A.nag_start(r5, "voice", datetime.now(CFG.tz))
e2 = Engine("text")
check("spec_block holds an ack while a reminder is open", e2.spec_block("got it") == "action")
rep = e2.turn("got it")
check("typed 'got it' (web / Telegram / terminal) stops it", rep == "Okay, I won't remind you again."
      and one("SELECT state, ack_via FROM reminder_nags WHERE intent_id=%s", (r5["id"],)) == {"state": "acked", "ack_via": "text"},
      rep)
r6 = mk("lock the door")
A.nag_start(r6, "voice", datetime.now(CFG.tz))
check("menu click stops every open one", A.ack_all("click") == 1)

print("app wiring: deliver → nag_start, repeats respect presence (fake app, no menubar)")
from types import SimpleNamespace                                        # noqa: E402

from stiti.app import StitiApp                                           # noqa: E402

q("TRUNCATE intents, reminder_nags RESTART IDENTITY CASCADE")
out: list = []
fake = SimpleNamespace(_deliver=lambda text, kind, present: out.append((kind, text, present)) or ("voice" if present else None),
                       _busy_speaking=lambda: False, _ring=lambda row: None, loop=None)
import json as _json                                                     # noqa: E402
one("INSERT INTO intents(kind, fire_at, payload) VALUES ('reminder', now() - interval '10 seconds', %s) RETURNING id",
    (_json.dumps({"say": "check the oven", "label": "check the oven", "kind": "reminder"}),))
orig_quiet = A.quiet_now
A.quiet_now = lambda t=None: False
try:
    StitiApp._fire(fake, True)
    nag = one("SELECT id, sent, channels FROM reminder_nags")
    check("delivered reminder starts a nag", out and out[0][1] == "Reminder: check the oven" and nag and nag["sent"] == 1, str(out))
    q("UPDATE reminder_nags SET next_at = now() - interval '1 second'")
    out.clear()
    StitiApp._nag(fake, False)
    check("away → repeat waits, not counted", not out and one("SELECT sent FROM reminder_nags")["sent"] == 1)
    q("UPDATE reminder_nags SET next_at = now() - interval '1 second'")
    fake._busy_speaking = lambda: True
    StitiApp._nag(fake, True)
    check("she's mid-sentence → waits (≤ 2 min)", not out)
    fake._busy_speaking = lambda: False
    StitiApp._nag(fake, True)
    check("present → repeated through the same delivery path", out == [("reminder", "Reminder again: check the oven.", True)]
          and one("SELECT sent FROM reminder_nags")["sent"] == 2, str(out))
finally:
    A.quiet_now = orig_quiet

print("ring limits: timer 5 min, alarm 10 min")
check("timer limit 300 s", A.ring_limit_s({"kind": "alarm", "payload": {"kind": "timer"}}) == 300)
check("alarm limit 600 s", A.ring_limit_s({"kind": "alarm", "payload": {"kind": "alarm"}}) == 600)
rid = one("""INSERT INTO intents(kind, fire_at, payload, state) VALUES ('alarm', now(), '{"kind":"timer","say":"Timer done!"}',
             'fired') RETURNING id""")["id"]
orig = (dict(A.RING_MAX_S), A.RING_ROUND_S, A.subprocess.run)
A.RING_MAX_S["timer"], A.RING_ROUND_S = 0.3, 0.05
played: list = []
A.subprocess.run = lambda args, **k: played.append(args[0])
logs: list[str] = []
try:
    t0 = time.perf_counter()
    outcome = A.Ringer({"id": rid, "kind": "alarm", "payload": {"kind": "timer", "say": "Timer done!"}}, log=logs.append).run()
    check("unanswered timer stops at its limit", outcome == "missed" and time.perf_counter() - t0 < 1.5 and played, outcome)
    check("ring log has latency + channel", logs and re.search(r"missed after \d+ s .*via mac-say", logs[-1]), str(logs))
finally:
    A.RING_MAX_S.clear()
    A.RING_MAX_S.update(orig[0])
    A.RING_ROUND_S, A.subprocess.run = orig[1], orig[2]

q("DELETE FROM owner_profile WHERE key='city'")
print(f"\n{passed}/{total} passed")
sys.exit(0 if passed == total else 1)
