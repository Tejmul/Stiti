"""Stiti engine: one `turn()` for text now, voice later.

decide (System 1) -> fast path (no LLM) | recall + compile briefing -> router (free cloud)
-> psych lint -> write episodes, turn, decisions. Works with zero API keys (degraded mode).
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime

from . import embed, router
from .brain import compiler, emotion, ingest, lessons, memory, psych
from .config import CFG
from .db import one, q
from .decide import decide
from .fastpath import handlers
from .life import brief as nudge, chunker, habits, planner
from .tools import registry

REMEMBER_RX = re.compile(r"\b(remember|ya+d ra\w*|note kar\w*|don'?t forget|mat bhool\w*)\b", re.I)
LIFE_RX = re.compile(r"\b(birthday|shaadi|wedding|job|offer|moved|shift|breakup|died|born|exam|interview|"
                     r"promotion|salary|health|hospital)\b", re.I)


NORMALIZE = [(r"\bto-?dos?\b", lambda m: "todos" if m.group(0).lower().endswith("s") else "todo"),
             (r"\ba\.m\.", lambda m: "am"), (r"\bp\.m\.", lambda m: "pm"),
             (r"\bya+d\b", lambda m: "yaad"), (r"\bmommy\b", lambda m: "mummy")]


def normalize(text: str) -> str:
    """Smooth over STT spellings so fast paths and memory see one form."""
    for rx, rep in NORMALIZE:
        text = re.sub(rx, rep, text, flags=re.I)
    return text.strip()


PLAN_RX = re.compile(r"\b(plan my day|plan (the|my) day|din plan|aaj ka plan|schedule my day|plan kar do)\b", re.I)
CAL_RX = re.compile(r"\b(calendar|schedule|meetings?|events?)\b.*\b(today|aaj|kya hai|what|my)\b|"
                    r"\b(aaj|today)\b.*\b(calendar|schedule|meetings?)\b", re.I)
MAIL_RX = re.compile(r"\b(unread|inbox|koi mail|any (new )?(mail|email)s?|check (my )?(mail|email))\b", re.I)
TOOL_HINT_RX = re.compile(r"\b(calendar|schedule|meeting|event|mail|email|inbox|open|volume|app|spotify)\b", re.I)
YES_RX = re.compile(r"^(haan|han|ha|yes|yeah|yep|ok(ay)?|kar do|do it|confirm|sure)\b", re.I)
GREET_RX = re.compile(r"^(hi|hello|hey|good morning|gm|morning|kya haal|uth gaya|i'?m up|namaste)\b", re.I)


class Engine:
    def __init__(self, channel: str = "text"):
        self.session = memory.start_session(channel)
        self.woop: psych.Woop | None = None
        self.chunker: chunker.Chunker | None = None
        self.pending: tuple | None = None        # (tool, args) awaiting his "haan"
        self.onboarding = None                    # active onboarding interview
        self.last_user_ep: int | None = None
        self.last_reply_ep: int | None = None
        self.last_mood: str | None = None

    def _llm(self, brief: str, text: str, qvec, privacy: int, use_tools: bool) -> tuple[str, dict]:
        """LLM call with an optional tool loop (≤3 rounds, risk-gated, taint-aware)."""
        msgs = [{"role": "system", "content": brief}, {"role": "user", "content": text}]
        tools = registry.select(qvec, k=5) if use_tools and privacy < 2 else []
        by_name = {t.name: t for t in tools}
        tainted = False
        info = {}
        for _ in range(3):
            info = router.complete(msgs, privacy=privacy, tools=[t.schema() for t in tools] or None)
            if not info.get("tool_calls"):
                return info["text"], info
            msgs.append({"role": "assistant", "content": info["text"] or None, "tool_calls": [
                {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}}
                for c in info["tool_calls"]]})
            for c in info["tool_calls"]:
                tool = by_name.get(c["name"])
                try:
                    args = json.loads(c["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                if tool is None:
                    res = json.dumps({"error": "unknown tool"})
                else:
                    res, needs = registry.run(tool, args, tainted)
                    tainted = tainted or tool.untrusted_output
                    if needs:
                        self.pending = (tool, args)
                        return f"Should I go ahead with {tool.name.replace('__', ' ').replace('_', ' ')}? (haan / no)", info
                msgs.append({"role": "tool", "tool_call_id": c["id"], "content": res})
            tools = [] if tainted else tools   # after untrusted content: answer, don't act
        return info.get("text") or "Done.", info

    def greet(self) -> str:
        """Called when woken with no command: offer the intro if she knows nothing yet; else the brief."""
        from .brain import onboarding
        if not onboarding.done() and not q("SELECT 1 FROM user_directives WHERE status='active' LIMIT 1"):
            return ("Haan! I don't know much about you yet — want a 3-minute intro? "
                    "Say “intro shuru karo”.")
        return nudge.morning_brief() or "Haan, bolo?"

    def turn(self, text: str, voice_emotion: tuple[str, float] | None = None) -> str:
        t0 = time.perf_counter()
        text = normalize(text)
        try:
            from .brain.mdsync import sync
            sync()                      # pick up his edits to USER.md / LESSONS.md (hash check, ~0.1 ms)
        except Exception as e:
            print(f"[mdsync] {e}")
        lat: dict[str, float] = {}
        now = datetime.now(CFG.tz)

        qvec = embed.embed_query(text)
        d = decide(text, qvec)
        lat["decide"] = d.latency_ms
        emo = emotion.fuse(text, d.get("text_emotion"), d.conf.get("text_emotion", 0.0),
                           *(voice_emotion or (None, 0.0)))
        privacy = d.privacy()
        importance = 7 if REMEMBER_RX.search(text) else 6 if LIFE_RX.search(text) else 3
        user_ep = memory.add_episode(self.session, "user", text, privacy=privacy,
                                     importance=importance, emotion=emo.as_json())
        domain = d.get("domain", "chat")
        route, reply, info, recalled_ids, lesson_ids, brief_tokens, brief = "fast_path", None, {}, [], [], None, None

        # ---- fast paths (no LLM) ----
        low = psych.minimum_viable_day(emo.label)
        from .brain import onboarding
        if self.onboarding is not None:
            reply, finished = self.onboarding.answer(text, user_ep)
            if finished:
                self.onboarding = None
        elif onboarding.START_RX.search(text):
            self.onboarding = onboarding.Onboarding()
            reply = self.onboarding.start()
        elif self.pending is not None:
            tool, args = self.pending
            self.pending = None
            if YES_RX.search(text):
                try:
                    reply = f"Done: {tool.name}. " + str(tool.fn(**args))[:200]
                except Exception as e:
                    reply = f"Couldn't do it: {type(e).__name__}."
            else:
                reply = "Okay, cancelled."
        elif self.chunker is not None:
            reply, finished = self.chunker.answer(text)
            if finished:
                self.chunker = None
        elif chunker.START_RX.search(text):
            self.chunker = chunker.Chunker(chunker.goal_from(text))
            reply = self.chunker.start()
        elif CAL_RX.search(text):
            from .connectors import eventkit
            reply = eventkit.speak_events(eventkit.today_events())
        elif MAIL_RX.search(text):
            from .connectors import mail
            reply = mail.speak_unread(mail.unread())
        elif PLAN_RX.search(text):
            plan = planner.plan_day()
            planner.accept(plan)
            reply = planner.speak_plan(plan, low_energy=low)
        elif (h := habits.handle(text)) is not None:
            reply = h
        elif GREET_RX.search(text) and (b := nudge.morning_brief(low_energy=low)):
            reply = b
        elif self.woop is not None:
            reply, result = self.woop.answer(text)
            if result:
                one("""INSERT INTO tasks(title, notes, if_then, source) VALUES (%s,%s,%s,'woop') RETURNING id""",
                    (result["wish"], f"Outcome: {result['outcome']}\nObstacle: {result['obstacle']}", result["plan"]))
                self.woop = None
        elif psych.WOOP_START.search(text):
            self.woop = psych.Woop()
            reply = self.woop.start()
        elif domain == "feedback" and d.is_("is_correction", 0.6):
            _, reply = lessons.capture(text, mood=self.last_mood,
                                       source_episode_ids=[i for i in (self.last_reply_ep, user_ep) if i])
        elif REMEMBER_RX.search(text) and not text.rstrip().endswith("?") and domain in ("memory", "chat"):
            reply = "Yaad rakh liya. 👍" if re.search(r"\b(yaad|rakhna|mat|hai)\b", text, re.I) else "Noted — I'll remember that."
        elif domain == "control":
            reply = handlers.control(text)
        elif domain == "todo":
            if psych.minimum_viable_day(emo.label) and handlers.LIST_RX.search(text):
                reply = handlers.todo_list(limit=1) + " That one's enough for today."
            else:
                reply = handlers.todo(text)
        elif domain == "time":
            reply = handlers.timeish(text)

        if reply is not None and (domain in ("todo", "time", "control") or PLAN_RX.search(text)):
            q("UPDATE episodes SET importance = 1 WHERE id = %s", (user_ep,))  # commands aren't memories

        # ---- LLM path ----
        if reply is None:
            t = time.perf_counter()
            mems = memory.recall(text, qvec, max_privacy=min(privacy, 1) if privacy < 2 else 2, k=8)
            mems = [m for m in mems if m["episode_id"] != user_ep and m["sim"] >= 0.25
                    and m.get("importance", 3) > 1]
            seeds = memory.seed_entities(text, [m["episode_id"] for m in mems])
            facts = memory.current_facts(seeds, max_privacy=min(privacy, 1))
            les = lessons.match(qvec, mood=emo.label, bucket=lessons.time_bucket(now))
            docs = ingest.recall(text, qvec, max_privacy=min(privacy, 1) if privacy < 2 else 2)
            lat["recall"] = (time.perf_counter() - t) * 1000
            recalled_ids = [m["episode_id"] for m in mems]
            lesson_ids = [l["id"] for l in les]
            talk = [r["directive"] for r in q(
                "SELECT directive FROM user_directives WHERE status='active' AND category='talk_style'")]
            loops = None
            if domain in ("todo", "time"):
                loops = handlers.todo_list() + " " + handlers.list_intents()
            brief, brief_tokens = compiler.build(
                text=text, now=now, privacy=privacy, emotion_hint=emo.hint(), tone=psych.tone(emo.label),
                recent=memory.recent_turns(self.session)[:-1], memories=mems, facts=facts, lessons=les,
                open_loops=loops, talk_directives=talk, mvd=psych.minimum_viable_day(emo.label), docs=docs)
            try:
                reply, info = self._llm(brief, text, qvec, privacy, use_tools=domain == "tool" or bool(TOOL_HINT_RX.search(text)))
                route = "llm"
                lat["llm"] = info["ms"]
            except router.NoProvider as e:
                route = "degraded"
                if privacy >= 2:
                    reply = "That sounds private, so I'm keeping it on this Mac. "
                else:
                    reply = "My thinking brain (cloud LLM) is offline right now. "
                if docs and (not mems or docs[0]["sim"] > mems[0]["sim"]) and docs[0]["sim"] >= 0.4:
                    d0 = docs[0]
                    reply += f"From your doc “{d0['title']}”: {d0['text'][:300]}"
                elif mems and mems[0]["sim"] >= 0.4:
                    m = mems[0]
                    reply += f"Here's what I remember from {m['occurred_at'].astimezone(CFG.tz):%d %b}: “{m['text']}”"
                else:
                    reply += "I can still do todos, alarms and reminders, and I'm remembering everything you say."
                info = {"error": str(e)}

        reply = psych.lint(reply)
        reply_ep = memory.add_episode(self.session, "stiti", reply, origin="agent", privacy=privacy)
        lat["total"] = (time.perf_counter() - t0) * 1000
        turn = one("""INSERT INTO turns(session_id, user_episode_id, reply_episode_id, route, provider, model, privacy,
                                        briefing, briefing_tokens, recalled, latency_ms)
                      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                   (self.session, user_ep, reply_ep, route, info.get("provider"), info.get("model"), privacy,
                    brief, brief_tokens, json.dumps({"episodes": recalled_ids, "lessons": lesson_ids}),
                    json.dumps({k: round(v, 1) for k, v in lat.items()})))
        for qn in ("domain", "text_emotion", "privacy_level", "is_correction"):
            if qn in d.answers:
                q("""INSERT INTO decisions(turn_id, question, answer, confidence, acted, laya_version)
                     VALUES (%s,%s,%s,%s,%s,%s)""",
                  (turn["id"], qn, d.answers[qn], d.conf.get(qn, 0.0), True, d.source))
        memory.touch(recalled_ids)
        lessons.mark_applied(lesson_ids)
        self.last_user_ep, self.last_reply_ep, self.last_mood = user_ep, reply_ep, emo.label
        self.last_debug = {"domain": str(domain), "domain_conf": round(d.conf.get("domain", 0), 2), "mood": str(emo.label), "mood_conf": round(emo.conf, 2),
                           "privacy": privacy, "route": route, "provider": info.get("provider"),
                           "latency_ms": {k: round(v) for k, v in lat.items()}}
        return reply
