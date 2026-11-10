"""Stiti engine: one `turn()` for text now, voice later.

decide (System 1) -> fast path (no LLM) | recall + compile briefing -> router (free cloud)
-> psych lint -> write episodes, turn, decisions. Works with zero API keys (degraded mode).
"""
from __future__ import annotations

import json
import os
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
from .connectors import live
from .connectors.mac import music_fastpath
from .tools import registry

def _tutor_request(text: str):
    from .tutor import voice_request
    return voice_request(text)


def _names_his_person(words: str) -> bool:
    """Do these words name a person in his life? Then they're never sent to a search engine (live.detect)."""
    return bool(one("""SELECT 1 AS x FROM entities WHERE merged_into IS NULL AND kind IN ('person', 'self') AND (
                         word_similarity(lower(name), lower(%(w)s)) >= 0.6
                         OR EXISTS (SELECT 1 FROM unnest(aliases) a WHERE word_similarity(lower(a), lower(%(w)s)) >= 0.6))
                       LIMIT 1""", {"w": words}))


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
TOOL_HINT_RX = re.compile(r"\b(calendar|schedule|meeting|event|mail|email|inbox|open|volume|app|spotify|"
                          r"web|internet|online|google|look ?up|website)\b", re.I)
YES_RX = re.compile(r"^(haan|han|ha|yes|yeah|yep|ok(ay)?|kar do|do it|confirm|sure)\b", re.I)
GREET_RX = re.compile(r"^(hi|hello|hey|good morning|gm|morning|kya haal|uth gaya|i'?m up|namaste)\b", re.I)


class Engine:
    def __init__(self, channel: str = "text"):
        self.session = memory.start_session(channel)
        self.woop: psych.Woop | None = None
        self.chunker: chunker.Chunker | None = None
        self.pending: tuple | None = None        # (tool, args) awaiting his "haan"
        self.onboarding = None                    # active onboarding interview
        self.last_nudge: tuple[int, float] | None = None   # (nudge_id, sent_time) for feedback
        self.ended = False                                  # text/Telegram: he said bye
        self.clarify = None                                 # asking what he meant after "nahi/galat"
        self.last_action: dict | None = None                # last fast-path write (for undo)
        self.last_turn_id: int | None = None
        self.last_lesson_ids: list[int] = []
        self.last_reply_text: str | None = None
        self.last_user_text: str | None = None
        self.last_route: str | None = None
        self.last_interrupted = False                       # set by the voice loop on barge-in
        self._offline_said_at = 0.0
        self.last_user_ep: int | None = None
        self.last_reply_ep: int | None = None
        self.last_mood: str | None = None
        self.streamed = False                               # last reply was already delivered via on_delta
        self.live_last: tuple | None = None                 # (LiveResult, next item index, time) for "want more?"
        if os.getenv("STITI_LIVE_WARM", "1") != "0":
            live.warm()                                     # news caches filled in the background, once per process

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

    def turn(self, text: str, voice_emotion: tuple[str, float] | None = None, *,
             on_delta=None, on_ack=None) -> str:
        """One turn. on_delta(str) streams an LLM reply as it is written (then self.streamed is True);
        on_ack(kind) fires the moment a slow action starts ("calendar", "mail", "plan", "tools") so the
        voice can say "ek sec, dekhti hoon" instantly instead of dead air."""
        t0 = time.perf_counter()
        self.streamed = False
        ack = on_ack or (lambda kind: None)
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
        live_job, live_res, live_from = None, None, 0       # live internet info (connectors/live.py)

        # ---- fast paths (no LLM) ----
        low = psych.minimum_viable_day(emo.label)
        from .brain import onboarding
        from .life import proactive
        if self.last_nudge and time.time() - self.last_nudge[1] < 180:      # his reaction to her nudge
            proactive.feedback(self.last_nudge[0], "dismissed" if proactive.DISMISS_RX.match(text) else "accepted")
            self.last_nudge = None
        disabled_kind = proactive.disable_from_text(text)
        if domain in ("chat", "memory") and privacy < 2:
            proactive.maybe_followup(text)
        from .brain import keythings
        learned = keythings.capture(text, user_ep) if domain not in ("todo", "time", "control") else []
        from .brain import learning
        from .voice.wake import is_stop
        undo = bool(learning.UNDO_RX.match(text)) and self.last_route == "fast_path" and self.last_action is not None
        corrected = undo or d.is_("is_correction", 0.6)
        learning.score_lessons(self.last_lesson_ids, corrected)
        learning.mark_outcome(self.last_turn_id, "corrected" if corrected else "confirmed")
        inferred_ack = None if d.is_("is_correction", 0.6) else \
            learning.infer_from_turn(text, self.last_reply_text, interrupted=self.last_interrupted)
        if self.clarify is not None:
            reply, self.clarify = self.clarify.answer(text), None
        elif undo:
            note = learning.undo_last(self.last_action)
            self.clarify = learning.Clarify(self.last_user_text or "", note)
            reply = self.clarify.question()
        elif inferred_ack:
            reply = inferred_ack
        elif is_stop(text) and self.onboarding is None and self.chunker is None and self.woop is None:
            from .farewell import farewell
            reply, self.ended = farewell(text, self.last_mood), True
        elif disabled_kind:
            reply = f"Okay — no more {disabled_kind.replace('_', ' ')} reminders from me."
        elif self.onboarding is not None:
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
        elif (tr := _tutor_request(text)) is not None:
            from .tutor import launch
            reply = launch(*tr)
        elif (self.live_last and time.time() - self.live_last[2] < 300 and live.MORE_RX.match(text)
              and re.search(r"\b(more|aur)\b", self.last_reply_text or "", re.I)):
            live_res, live_from, _ = self.live_last             # "want more?" → "haan": next items, no refetch
            if live_from >= len(live_res.items):
                reply, live_res = "That's everything I found for now.", None
        elif privacy < 2 and not corrected and (lreq := live.detect(text, known=_names_his_person)) is not None:
            ack("web")                      # "ek sec, internet pe dekhti hoon" while sources load in parallel
            live_job = live.start(lreq)     # only his extracted words leave the Mac; recall runs meanwhile
        elif CAL_RX.search(text):
            ack("calendar")
            from .connectors import eventkit
            reply = eventkit.speak_events(eventkit.today_events())
        elif (m := music_fastpath(text)) is not None:
            reply = m
        elif MAIL_RX.search(text):
            ack("mail")
            from .connectors import mail
            reply = mail.speak_unread(mail.unread())
        elif PLAN_RX.search(text):
            ack("plan")
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
        elif learned and len(text.split()) <= 14 and self.onboarding is None:
            reply = "Noted 👍 — " + ", ".join(learned) + "."
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
            if live_job is not None:
                try:
                    live_res = live_job.result(timeout=live.BUDGET_S + 1.5)
                except Exception:
                    live_res = live.LiveResult(lreq, [], datetime.now(CFG.tz), 0.0, [], ["all"])
                lat["live_fetch"] = live_res.ms
            if live_res is not None:                    # fetched facts → briefing; the LLM only words them
                block = live.block(live_res, start_at=live_from)
                brief += "\n\n" + block
                brief_tokens = (brief_tokens or 0) + len(block) // 4
            use_tools = live_res is None and (domain == "tool" or bool(TOOL_HINT_RX.search(text)))
            try:
                if on_delta is not None and not use_tools:      # stream: she starts talking at the first clause
                    info = {}
                    for piece in router.stream([{"role": "system", "content": brief}, {"role": "user", "content": text}],
                                               privacy=privacy, info=info):
                        self.streamed = True
                        on_delta(piece)
                    reply = info["text"]
                    lat["first_token"] = info.get("first_ms", 0)
                else:
                    if use_tools:
                        ack("tools")
                    reply, info = self._llm(brief, text, qvec, privacy, use_tools=use_tools)
                route = "llm"
                lat["llm"] = info["ms"]
            except router.NoProvider as e:
                route = "degraded"
                if privacy >= 2:
                    reply = "That sounds private, so I'm keeping it on this Mac. "
                elif time.time() - self._offline_said_at > 3600:
                    reply = "My thinking brain (cloud LLM) is offline right now. "
                    self._offline_said_at = time.time()
                else:
                    reply = ""
                if live_res is not None:                # no LLM: read the top headlines out directly
                    reply += live.speak(live_res, start_at=live_from)
                elif docs and (not mems or docs[0]["sim"] > mems[0]["sim"]) and docs[0]["sim"] >= 0.4:
                    d0 = docs[0]
                    reply += f"From your doc “{d0['title']}”: {d0['text'][:300]}"
                elif mems and mems[0]["sim"] >= 0.4:
                    m = mems[0]
                    reply += f"Here's what I remember from {m['occurred_at'].astimezone(CFG.tz):%d %b}: “{m['text']}”"
                elif reply:
                    reply += "I can still do todos, alarms and reminders, and I'm remembering everything you say."
                else:
                    reply = "Hmm, that one I can't answer right now — but I've noted it."
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
        m = re.search(r"\((task )?#(\d+)\)", reply)
        self.last_action = ({"type": "task" if m.group(1) else "intent", "id": int(m.group(2))}
                            if m and route == "fast_path" else None)
        self.last_turn_id, self.last_lesson_ids = turn["id"], lesson_ids
        self.last_reply_text, self.last_user_text, self.last_route = reply, text, route
        self.last_interrupted = False
        self.live_last = (live_res, live_from + 3, time.time()) if live_res is not None and live_res.items else None
        self.last_user_ep, self.last_reply_ep, self.last_mood = user_ep, reply_ep, emo.label
        self.last_debug = {"domain": str(domain), "domain_conf": round(d.conf.get("domain", 0), 2), "mood": str(emo.label), "mood_conf": round(emo.conf, 2),
                           "privacy": privacy, "route": route, "provider": info.get("provider"),
                           "latency_ms": {k: round(v) for k, v in lat.items()},
                           "live": None if live_res is None else {
                               "kind": live_res.req.kind, "query": live_res.req.query, "items": len(live_res.items),
                               "ok": live_res.ok, "failed": live_res.failed}}
        return reply
