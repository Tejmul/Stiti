"""She keeps the conversation going (2026-11-20, docs/research/conversation_continuity.md).

His four complaints, all offline (no mic, no LLM — the router is faked, PortAudio is faked):
  1. she stops listening mid-conversation  → the mic watchdog never restarts during a conversation and stops its
     restart loop when a fresh process doesn't help; a conversation keeps her awake longer; right after she dozes
     off a follow-up carries on without the wake word; "bye Stiti" inside a long sentence isn't a goodbye;
  2. she loses the thread                  → a restart resumes the same session + state; follow-ups ("why?", "and that
     one?") get the thread; RECENT keeps the last three exchanges under the token budget + an earlier-gist;
  3. she doesn't keep it going             → one beat (a follow-up question or a building sentence) under strict rules;
     "tell me more" about a topic continues it instead of "that's most of what I know".
Made-up world only (Ravi / Lakeview / Orbitly).

STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp> python tests/conversation_continuity_eval.py
"""
from __future__ import annotations

import os
import stat
import sys
import time

db = os.environ.get("STITI_DB", "")
if not db.rstrip("/").split("/")[-1].startswith("stiti_test"):
    sys.exit(f"refusing to run against {db!r}: use a stiti_test* database")
os.environ.setdefault("STITI_LIVE_WARM", "0")
os.environ.setdefault("STITI_EVENTKIT", "off")

import numpy as np                                                       # noqa: E402

passed = total = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, total
    total += 1
    passed += bool(cond)
    print(f"  {'✓' if cond else '✗'} {name}" + (f" — {detail}" if detail and not cond else ""))


from stiti.config import CFG                                             # noqa: E402

# ------------------------------------------------------------------ 1. the mic watchdog never kills a conversation
print("1. mic watchdog: no restart mid-conversation, no restart loop")
from stiti.voice import duplex as D                                      # noqa: E402
from stiti.voice import loop as L                                        # noqa: E402
from stiti.voice import wake                                             # noqa: E402

ok = L.mic_restart_ok
check("awake (in a conversation) → never restart", not ok(True, 999, True, None))
check("asleep but his last turn was 60 s ago → wait", not ok(False, 60, True, None))
check("idle for 3 min, mic heard before (the CoreAudio -50 case) → restart allowed", ok(False, 180, True, None))
check("a fresh process that never heard a sound, last restart 5 min ago → no restart (2026-11-18 loop)",
      not ok(False, 999, False, 300))
check("…but after 30 min it may try again", ok(False, 999, False, 31 * 60))
check("never heard and no restart before → one try", ok(False, 999, False, None))
logs = CFG.home / "logs"
logs.mkdir(parents=True, exist_ok=True)
(logs / "mic_restarts").write_text(f"{time.time() - 300}")
check("last restart read back from the stamps file", 290 < (L._last_restart_ago() or 0) < 400)
(logs / "mic_restarts").unlink()
check("no stamps file → None", L._last_restart_ago() is None)


class _FS:
    def __init__(self, *a, **k): self.active, self.latency = False, (0.01, 0.01)
    def start(self): self.active = True
    def abort(self): self.active = False
    def close(self): pass


class _SD:
    Stream = _FS
    @staticmethod
    def _terminate(): pass
    @staticmethod
    def _initialize(): pass
    @staticmethod
    def query_devices(kind=None): return {"name": "fake mic"}


class _APM:
    def set_stream_delay_ms(self, ms): pass


D.sd = _SD
MIC = {"id": 89}
D._default_input_id = lambda: MIC["id"]
D._transport = lambda i: {89: "bltn", 200: "usb "}.get(i)
D.mic_mode = lambda: "auto"
D.builtin_mic = lambda: None
_mono = D.time.monotonic


def make():
    dx = D.Duplex.__new__(D.Duplex)
    dx.on_mic, dx.aec, dx.apm = (lambda x: None), True, _APM()
    dx._init_playback()
    dx.stream = dx._new_stream()
    dx.__enter__()
    return dx


def feed(dx, sound: bool, at: float) -> None:
    D.time.monotonic = lambda: at
    try:
        n = 96
        mic = np.full((n, 1), 0.01, np.float32) if sound else np.zeros((n, 1), np.float32)
        dx._cb(mic, np.zeros((n, 1), np.float32), n, None, None)
    finally:
        D.time.monotonic = _mono


t0 = _mono()
dx = make()
check("a fresh stream has heard nothing yet", not dx.heard_once)
feed(dx, True, t0 + 0.5)
check("…then real sound → heard_once", dx.heard_once)
MIC["id"] = 200                                   # he plugs in a USB headset: macOS switches the default mic
D.time.monotonic = lambda: t0 + 3.0
why = dx.heal(t0 + 3.0)
D.time.monotonic = _mono
dx._opened_at = t0 + 3.0
check("a default-mic switch reopens", why is not None and why.startswith(D.SWITCHED) and dx.reopens == 1, str(why))
for k in range(1, 20):
    feed(dx, False, t0 + 3.0 + k * 0.5)           # the new mic sends zeros while it changes mode
check("…7 s of zeros after a SWITCH is not 'reopen failed' (it killed the app mid-conversation)",
      not dx.reopen_failed(t0 + 10.5) and dx.dead_reopens == 0)
MIC["id"] = 200
dx = make()
feed(dx, True, t0 + 0.1)
D.time.monotonic = lambda: t0 + 40.0
dx._zero_since = t0 + 5.0                         # dead for 35 s
why = dx.heal(t0 + 40.0)
D.time.monotonic = _mono
dx._opened_at = t0 + 40.0
check("a DEAD mic reopen still counts", why is not None and dx.dead_reopens == 1 and dx.reopen_failed(t0 + 47.0))
src = open(os.path.join(os.path.dirname(__file__), "..", "src", "stiti", "voice", "loop.py")).read()
check("the loop asks mic_restart_ok before exiting", "mic_restart_ok(self.awake" in src and "os._exit(75)" in src)

# ------------------------------------------------------------------ stay awake while a conversation is going
print("1b. stay awake")
T = L.AWAKE_TIMEOUT_S
check("just woken / one-off command → the short window", L.awake_window(0, "Set for 7.") == T)
check("a conversation (2+ turns since the wake) → longer window", L.awake_window(2, "Fair point.") == max(T, L.CONVO_AWAKE_S))
check("she just asked him something → longer window", L.awake_window(1, "Which city?") == max(T, L.CONVO_AWAKE_S))
check("should_sleep uses the window it's given", not L.should_sleep(True, False, T + 5, False, False, timeout=T + 30)
      and L.should_sleep(True, False, T + 31, False, False, timeout=T + 30))
now = 1000.0
check("dozed off: 'and why is that?' carries on", L.carries_on("And why is that?", now, now + 60, False))
check("dozed off: 'what about Pune?' carries on", L.carries_on("What about Pune?", now, now + 60, False))
check("dozed off: her name anywhere carries on", L.carries_on("okay Stiti one more thing", now, now + 60, False))
check("dozed off: talking to someone else does not", not L.carries_on("Can you pass me the charger", now, now + 60, False))
check("after the drowsy window → wake word needed again", not L.carries_on("And why is that?", now, now - 1, False))
check("after 'bye' / 'stop' (silenced) → never", not L.carries_on("And why is that?", now, now + 60, True))
long_line = ("bye and then I told him the whole plan about the internship and the course and bye Stiti was what I "
             "said to my friend when we were leaving the room after the class ended")
check("'bye Stiti' in the middle of a long sentence is not a goodbye", not wake.is_sleep(long_line))
check("…at the end of a long sentence it is", wake.is_sleep("okay that is all for today I think so bye Stiti"))
check("…and 'bye Stiti' alone still is", wake.is_sleep("Bye Stiti."))

# ------------------------------------------------------------------ 2. the thread
print("2. the thread: follow-ups resolve")
from stiti.brain import thread as TH                                     # noqa: E402

th = TH.update(TH.Thread(), "Should I take the Orbitly offer in Pune or stay in Lakeview?",
               "Pune pays more, Lakeview is closer to home.", follow=False, domain="chat", route="llm",
               strategy="SOLVE")
check("a real question starts a thread", th.topic.startswith("Should I take") and th.turns == 0 and th.live())
check("…its names are in play", {"Orbitly", "Pune", "Lakeview"} <= set(th.terms), str(th.terms))
for t in ("why?", "And that one?", "the second one", "What about Pune?", "tell me more", "aur?", "kyun?",
          "but is it worth it?", "how come?", "which one?"):
    check(f"follow-up: {t!r}", TH.is_followup(t, th))
for t in ("set an alarm for 6", "What is the capital of France?", "I had dal for lunch today with my roommates",
          "How is the weather in Chennai today?"):
    check(f"not a follow-up: {t!r}", not TH.is_followup(t, th))
check("a thread older than 10 min is over", not TH.is_followup("why?", th, now=th.at + TH.THREAD_S + 1))
th2 = TH.update(th, "set an alarm for 6", "Set for 6.", follow=False, domain="time", route="fast_path", strategy="DO")
check("a command in the middle doesn't end the thread", th2 == th)
th3 = TH.update(th, "why?", "Because the Orbitly team builds the product you like.", follow=True, domain="chat",
                route="llm", strategy="ANSWER")
check("a follow-up continues it (turns + 1, last answer kept)", th3.topic == th.topic and th3.turns == 1
      and th3.last_a.startswith("Because"))
check("naming something in play is the same topic", TH.same_topic("Is Lakeview cheaper to live in?", th3))
th4 = TH.update(th3, "I watched a great movie yesterday about space travel", "Nice.", follow=False, domain="chat",
                route="llm", strategy="ACKNOWLEDGE")
check("a new subject starts a new thread", th4.topic.startswith("I watched") and th4.turns == 0)
check("recall query for a follow-up = topic + names + his words",
      TH.query(th3, "why?").startswith("Should I take the Orbitly offer") and TH.query(th3, "why?").endswith("why?"))
b = TH.block(th3, "why?")
check("the [THREAD] block says what 'it' refers to", "[THREAD" in b and "Orbitly offer" in b and "Because the Orbitly" in b)
check("…and stays small (≤ 120 tokens)", len(b) // 4 <= 120, str(len(b) // 4))
check("thread survives JSON (restart)", TH.Thread.from_dict(th3.as_dict()) == th3)
check("'what do you know about me' is a personal topic", TH.is_personal("Okay, what do you know about me?"))
check("'explain B-trees' is not", not TH.is_personal("Explain how a B-tree works"))

# ------------------------------------------------------------------ 3. one beat
print("3. one beat — rules")
beat = TH.beat
base = dict(th=th3, follow=True, her_last=["Pune pays more.", "Because the team is good."], his_last=["x y z w v", "why?"])
check("in a running thread, chatty turn → 'ask'", beat(strategy="ANSWER", text="but is it worth moving for?", **base) == "ask")
check("her last reply asked something → 'build' (never two questions in a row)",
      beat(strategy="ANSWER", text="but is it worth moving for?", **{**base, "her_last": ["Which city do you prefer?"]}) == "build")
check("a question in any of her last three → no new question (≤ 1 in 4)",
      beat(strategy="ACKNOWLEDGE", text="yeah I think the team matters most to me",
           **{**base, "her_last": ["Which city?", "Okay.", "Fair."]}) == "build")
fresh = TH.Thread()
check("first statement of a new topic → no beat (no interview after every statement)",
      beat(strategy="ACKNOWLEDGE", text="I'm preparing for placements and making projects.", th=fresh, follow=False,
           her_last=[], his_last=[]) is None)
check("he tells a story (≥ 15 words) → one beat",
      beat(strategy="ACKNOWLEDGE", th=fresh, follow=False, her_last=[], his_last=[],
           text="So today I finally finished the parser for my compiler project and it handled every test case") == "ask")
check("terse ('ok cool') → none", beat(strategy="ACKNOWLEDGE", text="ok cool", **base) is None)
check("his last two lines terse → none",
      beat(strategy="ANSWER", text="and the other one then?", **{**base, "his_last": ["ok", "hmm sure"]}) is None)
check("annoyed → none", beat(strategy="ANSWER", text="just answer the question, stop asking me things", **base) is None)
check("angry voice → none", beat(strategy="ANSWER", text="but is it worth moving for?", mood="angry", mood_conf=0.8, **base) is None)
check("a command / QUIET / REPAIR turn → none", all(beat(strategy=s, text="but is it worth moving for?", **base) is None
                                                    for s in ("DO", "QUIET", "REPAIR", "CRISIS", "SOLVE", "LISTEN")))
check("recap / fetch / tools / flow (blocked) → none", beat(strategy="ANSWER", text="but is it worth it?", blocked=True, **base) is None)
check("she was just cut off → none", beat(strategy="ANSWER", text="but is it worth it?", interrupted=True, **base) is None)
check("his rule 'don't ask questions' → none",
      beat(strategy="ANSWER", text="but is it worth it?", directives=["Don't ask questions"], **base) is None)

# ------------------------------------------------------------------ 4. the briefing keeps the conversation
print("4. briefing: RECENT survives the budget")
from datetime import datetime                                            # noqa: E402

from stiti import profile, router                                        # noqa: E402
from stiti.brain import compiler, strategy                               # noqa: E402
from stiti.db import q                                                   # noqa: E402

profile.set("name", "Ravi")
now_dt = datetime.now(CFG.tz)
recent = []
for i in range(5):
    recent.append({"id": 100 + 2 * i, "speaker": "user", "text": f"Point {i}: tell me about the Orbitly offer part {i} "
                   + "and what it means for my plan " * 3})
    recent.append({"id": 101 + 2 * i, "speaker": "stiti", "text": f"Answer {i}: " + "Pune pays more but the rent is "
                   "higher and the commute is long, so it evens out over a year. " * 5})
mems = [{"episode_id": 900 + i, "occurred_at": now_dt, "text": "An old memory line about something else entirely " * 4}
        for i in range(3)]
facts = [{"fact_id": i, "valid": None, "fact_text": f"fact {i}"} for i in range(2)]
s = strategy.make("ANSWER")
brief, toks = compiler.build(text="why?", now=now_dt, privacy=1, emotion_hint="calm", tone="warm", recent=recent,
                             memories=mems, facts=facts, lessons=[], open_loops=None, talk_directives=[], mvd=False,
                             strategy=s, thread=TH.block(th3, "why?"),
                             earlier=["I left Orbitly in September and want a new job by March"])
rec = brief.split("[RECENT CONVERSATION]\n")[1].split("\n\n")[0].splitlines()
check("within the budget", toks <= CFG.briefing_token_budget, f"{toks}")
check("RECENT keeps ≥ 6 lines (the last three exchanges)", len(rec) >= compiler.RECENT_KEEP, str(len(rec)))
check("…the newest exchange in full", rec[-1].startswith("You: Answer 4") and "evens out" in rec[-1])
check("memories go before RECENT does", "An old memory line" not in brief or len(rec) == len(recent))
check("[THREAD] sits after RECENT", brief.index("[THREAD") > brief.index("[RECENT CONVERSATION]"))
small, _ = compiler.build(text="hi", now=now_dt, privacy=1, emotion_hint="calm", tone="warm", recent=recent[-4:],
                          memories=[], facts=[], lessons=[], open_loops=None, talk_directives=[], mvd=False, strategy=s,
                          earlier=["I left Orbitly in September and want a new job by March"])
check("the earlier gist is there when it fits", "[EARLIER IN THIS CONVERSATION" in small and "left Orbitly" in small)
t = time.perf_counter()
for _ in range(20):
    compiler.build(text="why?", now=now_dt, privacy=1, emotion_hint="calm", tone="warm", recent=recent, memories=mems,
                   facts=facts, lessons=[], open_loops=None, talk_directives=[], mvd=False, strategy=s,
                   thread=TH.block(th3, "why?"), earlier=["x y z"])
ms_build = (time.perf_counter() - t) * 1000 / 20
t = time.perf_counter()
for _ in range(1000):
    TH.is_followup("and that one?", th3)
    TH.update(th3, "and that one?", "Because.", follow=True, domain="chat", route="llm", strategy="ANSWER")
    beat(strategy="ANSWER", text="and that one?", **base)
ms_thread = (time.perf_counter() - t) * 1000 / 1000
print(f"   (latency: compiler.build with a full RECENT {ms_build:.2f} ms; thread + beat per turn {ms_thread:.3f} ms)")
check("thread + beat cost < 0.5 ms a turn", ms_thread < 0.5, f"{ms_thread:.3f} ms")
check("compiler.build < 25 ms", ms_build < 25, f"{ms_build:.1f} ms")

# ------------------------------------------------------------------ 5. the engine: follow-ups, more, beat, restart
print("5. engine")
from stiti.brain import memory, norepeat                                 # noqa: E402
from stiti.engine import Engine                                          # noqa: E402

seen, script = [], []


def fake(msgs, **kw):
    seen.append(msgs[0]["content"])
    return {"text": script.pop(0) if script else "Okay.", "provider": "fake", "model": "fake", "ms": 1}


orig = router.complete
router.complete = fake
try:
    e = Engine("text")
    script.append("A B-tree is a balanced search tree that keeps keys sorted in wide nodes, so lookups touch few disk pages.")
    r1 = e.turn("Explain what a B-tree is in simple words")
    check("first answer", "balanced search tree" in r1, r1)
    check("…starts a thread", e.thread.topic.startswith("Explain what a B-tree"), e.thread.topic)
    script.append("Because each node holds many keys, the tree stays very short, so it reads far fewer blocks.")
    r2 = e.turn("and why is it faster than a binary tree?")
    b2 = seen[-1]
    check("'and why is it…' is a follow-up", e.last_debug.get("follow") is True, str(e.last_debug))
    check("…the briefing names the topic in [THREAD]", "[THREAD" in b2 and "B-tree" in b2.split("[THREAD")[1][:300])
    n = len(seen)
    script.append("Inserts split a full node in two and push the middle key up, so the tree grows from the root.")
    r3 = e.turn("tell me more")
    b3 = seen[-1] if len(seen) > n else ""
    check("'tell me more' about a topic → the LLM continues it (no 'that's most of what I know')",
          len(seen) == n + 1 and r3 != norepeat.HONEST["english"] and "split a full node" in r3, r3)
    check("…with a MORE-on-this-topic thread block", "He wants MORE on this same topic" in b3)
    check("…marked topic_more", e.last_debug.get("topic_more") is True)
    script.append("Deletes borrow a key from a sibling or merge two nodes. Are you revising this for an exam?")
    r4 = e.turn("and what happens when you delete a key from it?")
    b4 = seen[-1]
    check("a running thread lets one beat through", e.last_beat == "ask" and "keep the conversation going" in b4,
          str(e.last_beat))
    check("…the briefing allows one question", "Questions: at most one" in b4)
    check("…the follow-up question is kept", r4.endswith("?") and r4.count("?") == 1, r4)
    script.append("Mostly in databases and file systems. Do you use Postgres for your project?")
    r5 = e.turn("okay and where are they used in real life?")
    check("right after a question → no second question in a row", "?" not in r5 and e.last_beat in ("build", None), r5)
    script.append("Because it's simpler.")
    r6 = e.turn("and?")
    check("a bare 'and?' right after an answer goes on (not 'Mm?')", r6 not in ("Mm?", "Okay.", "Cool.", "Mm-hm."), r6)
    # a command in the middle doesn't break the thread
    topic = e.thread.topic
    e.turn("set a timer for 5 minutes")
    check("a timer in the middle keeps the thread", e.thread.topic == topic)

    # ---- personal "what else" still ends honestly (D36 unchanged) ----
    q("""INSERT INTO briefing_cache(key, content, tokens) VALUES ('standing_profile', %s, 20)
         ON CONFLICT (key) DO UPDATE SET content = EXCLUDED.content""", ("- Ravi is a final-year student at Lakeview.",))
    p = Engine("text")
    script.append("You're a final-year student at Lakeview.")
    p.turn("What do you know about me?")
    n = len(seen)
    r = p.turn("what else?")
    check("'what else' about HIM with nothing new → honest line, no LLM (D36 unchanged)",
          r == norepeat.HONEST["english"] and len(seen) == n, r)

    # ---- a restart in the middle of a conversation picks it up again ----
    print("5b. restart → same conversation")
    v1 = Engine("voice", resume=True)
    check("first start: a new session", not v1.resumed)
    script.append("Orbitly pays more, but Lakeview keeps you near your family.")
    v1.turn("Should I take the Orbitly offer or stay in Lakeview?")
    script.append("Mostly the rent: Pune is about a third more.")
    v1.turn("why is Pune more expensive?")
    f = CFG.home / "conversation.json"
    check("state saved after the turn, private (0600)", f.exists() and stat.S_IMODE(f.stat().st_mode) == 0o600)
    v2 = Engine("voice", resume=True)                      # the app restarted (watchdog / update)
    check("restart within 15 min → same session", v2.resumed and v2.session == v1.session, f"{v2.session} {v1.session}")
    check("…the thread is back", v2.thread.topic == v1.thread.topic and v2.thread.turns == v1.thread.turns)
    check("…what she said is back (no repeats, 'what else' works)", len(v2.said.live()) == len(v1.said.live()) > 0
          and v2.said.anchor is not None)
    check("…her last reply is back", v2.last_reply_text == v1.last_reply_text)
    script.append("Because the offer letter says relocation is paid only for the first month.")
    v2.turn("and the other one?")
    b = seen[-1]
    check("…the next turn sees the conversation from before the restart in RECENT",
          "Orbitly offer or stay in Lakeview" in b.split("[RECENT CONVERSATION]")[1][:1500])
    check("…and resolves the follow-up against it", "[THREAD" in b and "Orbitly" in b.split("[THREAD")[1][:400],
          f"{v2.last_debug} {b.split('[THREAD')[1][:300] if '[THREAD' in b else ''}")
    q("UPDATE episodes SET occurred_at = occurred_at - interval '20 minutes' WHERE session_id = %s", (v2.session,))
    v3 = Engine("voice", resume=True)
    check("20 min later → a new conversation", not v3.resumed and v3.session != v2.session)
    check("…with an empty head", not v3.thread.topic and not v3.said.live())
    t = Engine("text")
    check("text / web engines never resume", not t.resumed and t.session != v3.session)
finally:
    router.complete = orig

print(f"\nconversation continuity: {passed}/{total} checks passed")
sys.exit(0 if passed == total else 1)
