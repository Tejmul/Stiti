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
from .brain import compiler, emotion, lessons, memory, psych
from .config import CFG
from .db import one, q
from .decide import decide
from .fastpath import handlers

REMEMBER_RX = re.compile(r"\b(remember|yaad rakh\w*|note kar\w*|don'?t forget|mat bhool\w*)\b", re.I)
LIFE_RX = re.compile(r"\b(birthday|shaadi|wedding|job|offer|moved|shift|breakup|died|born|exam|interview|"
                     r"promotion|salary|health|hospital)\b", re.I)


class Engine:
    def __init__(self, channel: str = "text"):
        self.session = memory.start_session(channel)
        self.woop: psych.Woop | None = None
        self.last_user_ep: int | None = None
        self.last_reply_ep: int | None = None
        self.last_mood: str | None = None

    def turn(self, text: str, voice_emotion: tuple[str, float] | None = None) -> str:
        t0 = time.perf_counter()
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
        if self.woop is not None:
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

        if reply is not None and domain in ("todo", "time", "control"):
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
                open_loops=loops, talk_directives=talk, mvd=psych.minimum_viable_day(emo.label))
            try:
                info = router.complete([{"role": "system", "content": brief},
                                        {"role": "user", "content": text}], privacy=privacy)
                reply, route = info["text"], "llm"
                lat["llm"] = info["ms"]
            except router.NoProvider as e:
                route = "degraded"
                if privacy >= 2:
                    reply = "That sounds private, so I'm keeping it on this Mac. "
                else:
                    reply = "My thinking brain (cloud LLM) is offline right now. "
                if mems and mems[0]["sim"] >= 0.4:
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
