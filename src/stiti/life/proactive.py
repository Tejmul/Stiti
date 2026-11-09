"""Proactivity: Stiti speaks first — rarely, at the right moment, and learns what he likes.

Presence: HID idle time + screen lock + frontmost app (no permissions needed).
Candidates (checked every minute):
  meeting_soon  — calendar event starting in ~10 min
  deadline      — open task due within 2 h
  break         — present & active ~2.5 h straight
  evening_wrap  — once, ~9 PM, if he's at the Mac
  followup      — "interview kal hai" → next day "How did the interview go?" (intents kind='checkin')
  habit         — habit with a cue time
Gate (report §Nudges): daily budget, quiet hours 23:00–08:00, never mid-conversation, and a
Beta-Bernoulli bandit per kind (Thompson sampling) learned from accept / dismiss / ignore.
"don't remind me about breaks" → that kind is disabled for good. User-set alarms bypass all of this.
"""
from __future__ import annotations

import random
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..config import CFG
from ..db import one, q

QUIET = (23, 8)
KINDS = ["meeting_soon", "deadline", "break", "evening_wrap", "followup", "habit"]
DISMISS_RX = re.compile(r"^\s*(not now|baad mein|later|stop|no|nahi|mat|chup|leave it|chhodo|skip)\b", re.I)
DISABLE_RX = re.compile(r"\b(don'?t|do not|stop|mat|band karo)\b.*\b(remind|nudge|bolo|batana|yaad)\w*\b.*"
                        r"\b(break|meeting|deadline|wrap|follow|habit)", re.I)
FOLLOW_RX = re.compile(r"\b(interview|exam|meeting|presentation|demo|doctor|dentist|appointment|date|trip|flight|"
                       r"match|test|result|surgery|pitch|deadline|launch|shaadi|wedding)\b", re.I)


# ---------------- presence ----------------
def idle_seconds() -> float:
    out = subprocess.run(["ioreg", "-c", "IOHIDSystem"], capture_output=True, text=True).stdout
    m = re.search(r'"HIDIdleTime" = (\d+)', out)
    return int(m.group(1)) / 1e9 if m else 0.0


def screen_locked() -> bool:
    try:
        import Quartz
        d = Quartz.CGSessionCopyCurrentDictionary()
        return bool(d and d.get("CGSSessionScreenIsLocked"))
    except Exception:
        return False


def frontmost_app() -> str | None:
    try:
        from AppKit import NSWorkspace
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        return str(app.localizedName()) if app else None
    except Exception:
        return None


@dataclass
class Presence:
    present: bool
    idle_s: float
    locked: bool
    app: str | None
    active_minutes: float    # continuous activity (gaps < 5 min)


class PresenceTracker:
    def __init__(self):
        self.active_since: float | None = None

    def sample(self) -> Presence:
        idle, locked = idle_seconds(), screen_locked()
        present = idle < 120 and not locked
        now = time.time()
        if idle > 300 or locked:
            self.active_since = None          # a real break resets the clock
        elif self.active_since is None:
            self.active_since = now - idle
        active = (now - self.active_since) / 60 if self.active_since else 0.0
        return Presence(present, idle, locked, frontmost_app(), active)


# ---------------- bandit ----------------
def _arm(kind: str) -> dict:
    row = one("SELECT alpha, beta, disabled FROM nudge_arms WHERE kind=%s", (kind,))
    if not row:
        q("INSERT INTO nudge_arms(kind) VALUES (%s) ON CONFLICT DO NOTHING", (kind,))
        row = {"alpha": 2.0, "beta": 1.0, "disabled": False}
    return row


def want(kind: str, rng: random.Random | None = None) -> bool:
    arm = _arm(kind)
    if arm["disabled"]:
        return False
    return (rng or random).betavariate(arm["alpha"], arm["beta"]) > 0.35


def feedback(nudge_id: int, response: str) -> None:
    """response: accepted | dismissed | ignored  → bandit update."""
    row = one("UPDATE nudges SET response=%s, answered_at=now() WHERE id=%s AND response IS NULL RETURNING kind",
              (response, nudge_id))
    if not row:
        return
    da, db = {"accepted": (1, 0), "dismissed": (0, 1), "ignored": (0, 0.3)}[response]
    q("""INSERT INTO nudge_arms(kind, alpha, beta) VALUES (%s, 2 + %s, 1 + %s)
         ON CONFLICT (kind) DO UPDATE SET alpha = nudge_arms.alpha + %s, beta = nudge_arms.beta + %s, updated_at=now()""",
      (row["kind"], da, db, da, db))


def disable_from_text(text: str) -> str | None:
    """'don't remind me about breaks' → permanently disable that nudge kind."""
    m = DISABLE_RX.search(text)
    if not m:
        return None
    word = m.group(3).lower()
    kind = {"break": "break", "meeting": "meeting_soon", "deadline": "deadline", "wrap": "evening_wrap",
            "follow": "followup", "habit": "habit"}[word]
    q("""INSERT INTO nudge_arms(kind, disabled) VALUES (%s, true)
         ON CONFLICT (kind) DO UPDATE SET disabled = true, updated_at = now()""", (kind,))
    return kind


def expire_unanswered(minutes: int = 3) -> None:
    for r in q("""SELECT id FROM nudges WHERE response IS NULL AND kind <> 'morning_brief'
                  AND sent_at < now() - make_interval(mins => %s)""", (minutes,)):
        feedback(r["id"], "ignored")


# ---------------- follow-ups ----------------
def maybe_followup(text: str) -> int | None:
    """'kal mera interview hai' → a check-in after it happens."""
    from ..fastpath.dates import parse_when
    m = FOLLOW_RX.search(text)
    if not m or text.rstrip().endswith("?"):
        return None
    when = parse_when(text)
    if not when:
        return None
    thing = m.group(1).lower()
    fire = when + timedelta(hours=3)
    if fire.hour >= 22 or fire.hour < 8:
        fire = (fire + timedelta(days=1 if fire.hour >= 22 else 0)).replace(hour=9, minute=30)
    dup = one("""SELECT id FROM intents WHERE kind='checkin' AND state='pending' AND payload->>'thing'=%s
                 AND fire_at BETWEEN %s AND %s""", (thing, fire - timedelta(hours=12), fire + timedelta(hours=12)))
    if dup:
        return None
    import json
    return one("""INSERT INTO intents(kind, fire_at, payload, user_set, fires_left, expires_at)
                  VALUES ('checkin', %s, %s, false, 1, %s) RETURNING id""",
               (fire, json.dumps({"say": f"How did the {thing} go?", "thing": thing}),
                fire + timedelta(days=2)))["id"]


# ---------------- candidates ----------------
def candidates(p: Presence, now: datetime | None = None) -> list[tuple[str, str, dict]]:
    now = now or datetime.now(CFG.tz)
    out: list[tuple[str, str, dict]] = []
    sent = {r["key"] for r in q("""SELECT payload->>'key' AS key FROM nudges
                                    WHERE sent_at > now() - interval '20 hours' AND payload ? 'key'""")}
    # meetings in 8–12 minutes
    try:
        from ..connectors import eventkit
        for e in eventkit.events(now + timedelta(minutes=8), now + timedelta(minutes=12)):
            key = f"meet:{e['title']}:{e['start']:%Y%m%d%H%M}"
            if not e["all_day"] and key not in sent and e["start"] >= now + timedelta(minutes=8):
                out.append(("meeting_soon", f"Heads up — {e['title']} at {e['start']:%I:%M %p}, in 10 minutes.",
                            {"key": key}))
    except Exception:
        pass
    # deadlines within 2 h
    for t in q("""SELECT id, title, due FROM tasks WHERE status='open' AND due BETWEEN now() AND now() + interval '2 hours'"""):
        key = f"due:{t['id']}"
        if key not in sent:
            out.append(("deadline", f"“{t['title']}” is due at {t['due'].astimezone(CFG.tz):%I:%M %p}. "
                                    "Want to knock it out now?", {"key": key}))
    # long focus
    if p.present and p.active_minutes >= 150:
        key = f"break:{now:%Y%m%d%H}"
        recent = one("SELECT 1 FROM nudges WHERE kind='break' AND sent_at > now() - interval '2 hours'")
        if not recent:
            out.append(("break", f"You've been at it for {int(p.active_minutes // 60)} hours straight. "
                                 "Five-minute break? Paani pee lo.", {"key": key}))
    # evening wrap-up
    if p.present and now.hour == 21 and now.minute < 40:
        key = f"wrap:{now:%Y%m%d}"
        if key not in sent:
            done = one("""SELECT count(*) n FROM tasks WHERE status='done'
                          AND created_at > now() - interval '7 days'""")["n"]
            left = one("SELECT count(*) n FROM tasks WHERE status='open'")["n"]
            out.append(("evening_wrap", f"Quick wrap-up: {done} things done this week, {left} still open. "
                                        "Anything to carry to tomorrow?", {"key": key}))
    # follow-ups (check-in intents)
    for r in q("""UPDATE intents SET state='fired', last_fired_at=now()
                  WHERE kind='checkin' AND state='pending' AND fire_at <= now()
                    AND (expires_at IS NULL OR expires_at > now()) RETURNING id, payload"""):
        out.append(("followup", r["payload"]["say"], {"key": f"checkin:{r['id']}"}))
    # habits with a cue time
    from . import habits
    for h in habits.due_prompts():
        cue_time = (h.get("cue") or "")
        m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", cue_time, re.I)
        if m:
            hr = int(m.group(1)) % 12 + (12 if m.group(3).lower() == "pm" else 0)
            if now.hour == hr and now.minute < 15:
                key = f"habit:{h['id']}:{now:%Y%m%d}"
                if key not in sent:
                    out.append(("habit", f"Time for {h['name']}.", {"key": key}))
    return out


def quiet(now: datetime) -> bool:
    return now.hour >= QUIET[0] or now.hour < QUIET[1]


def tick(p: Presence, deliver, busy: bool = False, now: datetime | None = None) -> list[tuple[int, str, str]]:
    """One proactive pass. deliver(text, kind, present) -> channel name or None. Returns [(nudge_id, kind, text)]."""
    from .brief import allowed, record
    now = now or datetime.now(CFG.tz)
    expire_unanswered()
    sent = []
    if busy:
        return sent
    for kind, text, payload in candidates(p, now):
        urgent = kind in ("meeting_soon", "deadline")
        if quiet(now) and not urgent:
            continue
        if not urgent and not allowed():
            continue
        if not want(kind):
            continue
        channel = deliver(text, kind, p.present)
        if channel:
            nid = record(kind, payload)
            q("UPDATE nudges SET channel=%s WHERE id=%s", (channel, nid))
            sent.append((nid, kind, text))
            if not urgent:
                break               # at most one non-urgent nudge per pass
    return sent
