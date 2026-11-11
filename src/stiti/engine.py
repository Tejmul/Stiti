"""Stiti engine: one `turn()` for text now, voice later.

decide (System 1) -> fast path (no LLM) | recall + compile briefing -> router (free cloud)
-> psych lint -> write episodes, turn, decisions. Works with zero API keys (degraded mode).
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import date, datetime

from . import embed, router
from .brain import compiler, emotion, gate, ingest, lessons, memory, psych, strategy, turnmark
from .config import CFG
from . import db
from .db import one, q
from .decide import decide
from .fastpath import handlers
from .life import brief as nudge, chunker, habits, planner
from .connectors import live
from .connectors.mac import music_fastpath
from .tools import registry

def _awaiting_label() -> bool:
    from .life import alarms
    return alarms.awaiting_label()


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
# "ek sec", "ruko", "let me think", "hold on": he is thinking — she says NOTHING (ElevenLabs skip_turn)
HOLD_RX = re.compile(r"^\s*(hey stiti[, ]+)?(ek (sec|second|min|minute)|ek second ruko|ruko|ruk jao|ruko zara|wait|wait a (sec|second|minute)|"
                     r"one (sec|second|minute)|just a (sec|second|minute)|give me a (sec|second|minute)|hold on|hang on|"
                     r"let me think|soch(ne do| ke batata hoon| ke batati hoon| raha hoon| rahi hoon)|"
                     r"hmm+,? let me think)[.!…, ]*$", re.I)
# "Not yet / nothing / that's it" right after her "Anything else?" — he's done asking, not leaving
TEACH_ASK_S = 90.0      # after "what should I teach you?", his next short line is the topic …
COMMAND_RX = re.compile(r"\b(add|remind\w*|alarms?|to-?do|todos?|tasks?|delete|list|timers?)\b", re.I)   # … unless a command
CANCEL_ASK_RX = re.compile(r"^\W*(never ?mind|cancel|leave it|forget it|no|nahi|rehne do|chhodo|nothing)\W*$", re.I)
NOTHING_RX = re.compile(r"^\s*(no|nope|nah|nahi|nahin|not yet|ok|okay|alright|nothing|nothing else|that'?s (it|all)( for now)?|bas|bas itna|"
                        r"no thanks|no thank you|all good|i'?m good|abhi nahi|kuch nahi|that'?s it for now|nope that'?s it)[.!]*\s*$", re.I)
ASKED_NAME_RX = re.compile(r"\b(?:about|remember|yaad hai|of)\s+(?P<name>[A-Z][a-z]{2,20})\b")


_last_hello = ""
SPEC_DOMAINS = ("chat", "memory")       # only plain LLM chat turns are ever started speculatively (D29)


class NotSpeculable(Exception):
    """This turn can't be started before he has surely finished (a fast path / action / flow): run it normally."""


def hello(name: str | None, now: datetime | None = None) -> str:
    """A short, human hello on wake — never the same twice in a row."""
    import random
    global _last_hello
    now = now or datetime.now(CFG.tz)
    n = f" {name}" if name else ""
    if now.hour < 5:
        opts = [f"Hey{n}, still up?", f"Hey{n}. Late night?"]
    elif now.hour < 12:
        opts = [f"Morning{n}! How are you?", f"Hey{n}, good morning. What's up?"]
    elif now.hour < 17:
        opts = [f"Hey{n}, how are you?", f"Hi{n}! What's up?", f"Hey{n}. What's on your mind?"]
    else:
        opts = [f"Hey{n}, how was your day?", f"Hi{n}! How's it going?", f"Hey{n}. What's up?"]
    pick = random.choice([o for o in opts if o != _last_hello] or opts)
    _last_hello = pick
    return pick


class Engine:
    NotSpeculable = NotSpeculable

    def __init__(self, channel: str = "text"):
        self.channel = channel
        self.session = memory.start_session(channel)
        self.last_marker: str | None = None                # ● ◐ ○ the LLM opened its last reply with (turnmark.py)
        self.incomplete_at = 0.0                            # when a reply was last dropped as ◐/○
        self._spec = False                                  # inside a speculative turn (D29)
        self._held: db.Held | None = None                   # its uncommitted DB writes
        self._snap: dict | None = None                      # engine state before it
        self.woop: psych.Woop | None = None
        self.chunker: chunker.Chunker | None = None
        self.teach_ask_at = 0.0                             # she asked "what should I teach you?" (tutor launch)
        self.pending: tuple | None = None        # (tool, args) awaiting his "haan"
        self.onboarding = None                    # active onboarding interview
        self.last_nudge: tuple[int, float] | None = None   # (nudge_id, sent_time) for feedback
        self.ended = False                                  # text/Telegram: he said bye
        self.last_offer: tuple[str, float] | None = None   # ("intro", time) — what "turn this off" refers to
        self.last_card: dict | None = None                  # on-screen card for the last turn (cards.py)
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
        self.skip_turn = False                              # last turn was a hold ("ek sec"): the voice loop stays silent
        self.last_strategy: strategy.Strategy | None = None
        self.last_reply_full: str | None = None             # before a barge-in truncated it (learning signal)
        self.crisis_at = 0.0
        self.nudged: float | None = None                    # when she last pushed back (late night) — once per session
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

    def _voice_active(self) -> None:
        """He's talking to her: the STT cloud second opinion may run (never while she's asleep — D27)."""
        if self.channel == "voice":
            from .voice import stt
            stt.mark_active()

    def greet(self) -> str:
        """Called when woken with no command. Like a person: "Hey Tejmul, how are you?" (the daily brief once a
        morning). The intro is offered only if she really knows nothing about him, at most once a week, and never
        again once he says "turn this off" (owner: she kept asking on every wake)."""
        from . import profile
        self._voice_active()
        if self._should_offer_intro():
            profile.set("intro_offered_at", datetime.now(CFG.tz).date().isoformat(), "system")
            self.last_offer = ("intro", time.time())
            return ("Hey! I don't know much about you yet. Whenever you like, say “intro shuru karo” "
                    "and we'll do a quick intro. Or say “turn this off”.")
        name = profile.call() if profile.get("name") else None
        brief = nudge.morning_brief(name=name)
        return brief or hello(name)

    INTRO_OFF_RX = re.compile(r"\b(turn (it |this |that )?off|switch (it |this |that )?off|band (karo|kar do|kardo)|"
                              r"stop asking|don'?t ask (me )?(again|that|this)|mat (pucho|poocho)|no more intro)\b", re.I)
    INTRO_ON_RX = re.compile(r"\b(turn|switch) (the )?intro (offer )?(back )?on\b", re.I)

    def _intro_switch(self, text: str) -> str | None:
        """"Hey Stiti, turn this off" right after the intro offer (or "turn off the intro" any time)."""
        from . import profile
        if self.INTRO_ON_RX.search(text):
            profile.set("intro_offer", "on", "owner_edit")
            return "Okay, I'll offer the intro again sometime."
        recent = self.last_offer and self.last_offer[0] == "intro" and time.time() - self.last_offer[1] < 300
        if self.INTRO_OFF_RX.search(text) and (recent or re.search(r"\bintro", text, re.I)):
            profile.set("intro_offer", "off", "owner_edit")
            self.last_offer = None
            return "Done. I won't ask about the intro again."
        return None

    @staticmethod
    def _unknown_name(text: str, user_ep: int) -> str | None:
        """"Remember what I told you about Riya?" and Riya appears nowhere in the brain → "Riya" (else None)."""
        m = ASKED_NAME_RX.search(text)
        if not m or m.group("name").lower() in ("what", "that", "this", "the", "my", "when", "yesterday", "today"):
            return None
        name = m.group("name")
        if gate.entities_in([name]) or one("""SELECT 1 AS x FROM episodes WHERE id <> %s AND speaker='user'
                                                 AND text ~* %s LIMIT 1""", (user_ep, rf"\m{re.escape(name)}\M")):
            return None
        return name

    @staticmethod
    def _should_offer_intro() -> bool:
        from . import profile
        from .brain import onboarding
        if profile.get("intro_offer") == "off" or onboarding.done() or profile.get("name"):
            return False
        knows = one("""SELECT count(*) n FROM facts f JOIN entities e ON e.id=f.subj_id
                       WHERE e.kind='self' AND upper_inf(f.recorded)""")["n"]
        if knows >= 3 or q("SELECT 1 FROM user_directives WHERE status='active' LIMIT 1"):
            return False
        last = profile.get("intro_offered_at")
        return not last or (datetime.now(CFG.tz).date() - date.fromisoformat(last)).days >= 7

    def truncate_last_reply(self, heard_text: str) -> None:
        """After a barge-in: keep only what he actually HEARD of her last reply (OpenAI conversation.item.truncate /
        ElevenLabs agent_response_correction), so her memory never claims he heard the rest. Called by the voice loop."""
        heard = (heard_text or "").strip()
        if self.last_reply_ep is None or self.last_reply_text is None or heard == self.last_reply_text.strip():
            return
        self.last_reply_full = self.last_reply_full or self.last_reply_text
        text = f"{heard} —(cut off)" if heard else "—(cut off before she spoke)"
        vec = embed.embed_docs([text])[0]
        q("UPDATE episodes SET text = %s, embedding = %s WHERE id = %s", (text, vec, self.last_reply_ep))
        self.last_reply_text = text
        self.last_interrupted = True

    def _hold(self, text: str) -> str:
        """"ek sec" / "let me think": store his words, say nothing, keep every other state as it was."""
        memory.add_episode(self.session, "user", text, importance=1)
        self.skip_turn = True
        self.last_debug = {"route": "hold", "strategy": "QUIET"}
        return ""

    # ---------------- speculative turns (D29: LiveKit preemptive generation / Pipecat SpeculationGate) ----------------
    def spec_block(self, text: str) -> str | None:
        """Why this text must NOT be started speculatively (None = it's a plain chat turn). Pure checks only — no
        writes — so a fast path / action / flow / correction never runs before he has surely finished."""
        from . import farewell as bye
        from .brain import instructions, learning, onboarding
        from .life import habits, proactive
        from .voice.wake import is_stop
        t = normalize(text)
        now = time.time()
        if self._held is not None or self._spec:
            return "busy"
        if any(x is not None for x in (self.pending, self.clarify, self.onboarding, self.chunker, self.woop)):
            return "flow"
        if (self.last_nudge and now - self.last_nudge[1] < 180) or (self.nudged and now - self.nudged < 900):
            return "nudge"
        if self.last_interrupted:
            return "learning"                       # "she was cut off" feeds a brevity lesson (writes LESSONS.md)
        if self.live_last and live.MORE_RX.match(t):
            return "live"
        checks = (HOLD_RX.match(t), strategy.is_crisis(t), learning.UNDO_RX.match(t), learning.SHORTER_RX.search(t),
                  strategy.CONFUSION_RX.search(t), NOTHING_RX.match(t), is_stop(t), bye.is_bye(t),
                  proactive.DISABLE_RX.search(t), self.INTRO_OFF_RX.search(t), self.INTRO_ON_RX.search(t),
                  onboarding.START_RX.search(t), chunker.START_RX.search(t), psych.WOOP_START.search(t),
                  CAL_RX.search(t), MAIL_RX.search(t), PLAN_RX.search(t), GREET_RX.search(t), REMEMBER_RX.search(t),
                  TOOL_HINT_RX.search(t), habits.NEW_RX.search(t), habits.DONE_RX.search(t),
                  re.search(r"\b(habits?|alarm|remind|timer|todos?|task)\b", t, re.I))
        if any(checks):
            return "action"
        from .connectors.mac import MUSIC_RX
        if (MUSIC_RX.search(t) or instructions.parse(t) or _tutor_request(t) is not None or _awaiting_label()
                or time.time() - self.teach_ask_at < TEACH_ASK_S):
            return "action"
        if live.detect(t, known=_names_his_person) is not None:
            return "live"
        return None

    def _speculate(self, text: str, voice_emotion, on_delta, now) -> str:
        """Run the turn with every DB write held in one transaction and the engine state snapshotted. The caller
        then calls speculation_commit() (it was right: the turn is stored exactly as a normal one) or
        speculation_discard() (he went on talking: no episode, no turn, no lesson score, state as before)."""
        why = self.spec_block(text)
        if why:
            raise NotSpeculable(why)
        snap = {k: v for k, v in vars(self).items() if k not in ("session", "last_nudge")}
        held = db.Held()
        self._spec = True
        try:
            with held:
                reply = self.turn(text, voice_emotion, on_delta=on_delta, on_ack=lambda kind: None, now=now)
        except BaseException:
            self._spec = False
            held.rollback()
            self._restore(snap)
            raise
        self._spec = False
        self._held, self._snap = held, snap
        return reply

    def speculation_commit(self) -> None:
        h, self._held, self._snap = self._held, None, None
        if h is not None:
            h.commit()

    def speculation_discard(self) -> None:
        h, snap = self._held, self._snap
        if h is None:
            return
        try:
            h.rollback()
        finally:
            self._restore(snap)

    def _restore(self, snap: dict | None) -> None:
        if snap is not None:
            for k in [k for k in vars(self) if k not in snap and k not in ("session", "last_nudge")]:
                delattr(self, k)
            vars(self).update(snap)
        self._held = self._snap = None

    def _incomplete(self, user_ep: int, mark: str) -> str:
        """◐ / ○: he hadn't finished. Say nothing; the voice loop keeps his words and joins what he says next
        (that joined turn stores the whole thought, so this fragment is kept out of recall)."""
        q("UPDATE episodes SET importance = 1 WHERE id = %s", (user_ep,))
        self.last_marker, self.skip_turn, self.incomplete_at = mark, True, time.time()
        self.last_turn_id, self.last_lesson_ids = None, []      # scored once already; the joined turn won't redo it
        self.last_debug = {"route": "incomplete", "marker": mark, "strategy": "QUIET"}
        return ""

    def turn(self, text: str, voice_emotion: tuple[str, float] | None = None, *,
             on_delta=None, on_ack=None, now: datetime | None = None, speculative: bool = False) -> str:
        """One turn. on_delta(str) streams an LLM reply as it is written (then self.streamed is True);
        on_ack(kind) fires the moment a slow action starts ("calendar", "mail", "plan", "tools") so the
        voice can say "ek sec, dekhti hoon" instantly instead of dead air. Returns "" with self.skip_turn=True for a
        hold phrase ("ek sec", "let me think"): say nothing. `now` is for tests (the clock of this turn).
        speculative=True (voice, D29): run it before he has surely finished — raises NotSpeculable for anything but a
        plain chat turn, and holds every DB write until speculation_commit() / speculation_discard()."""
        if speculative:
            return self._speculate(text, voice_emotion, on_delta, now)
        t0 = time.perf_counter()
        self.last_marker = None
        self.streamed = False
        self.skip_turn = False
        self.last_used = None           # what the brain handed the LLM this turn (web "memory receipts")
        psych.set_policy(None)          # the voice loop's StreamLint picks up this turn's strategy once it's chosen
        ack = on_ack or (lambda kind: None)
        text = normalize(text)
        self._voice_active()
        if HOLD_RX.match(text):
            return self._hold(text)
        try:
            from .brain.mdsync import sync
            if not self._spec:          # (a speculative turn leaves his files alone)
                sync()                  # pick up his edits to USER.md / LESSONS.md (hash check, ~0.1 ms)
        except Exception as e:
            print(f"[mdsync] {e}")
        lat: dict[str, float] = {}
        now = now or datetime.now(CFG.tz)
        crisis = strategy.is_crisis(text)       # self-harm words: local script, no LLM, never leaves the Mac

        qvec = embed.embed_query(text)
        d = decide(text, qvec)
        lat["decide"] = d.latency_ms
        emo = emotion.fuse(text, d.get("text_emotion"), d.conf.get("text_emotion", 0.0),
                           *(voice_emotion or (None, 0.0)))
        privacy = 2 if crisis else d.privacy()
        if self._spec and (crisis or privacy >= 2 or str(d.get("domain", "chat")) not in SPEC_DOMAINS
                           or d.is_("is_correction", 0.5)):
            raise NotSpeculable(f"domain {d.get('domain')}")
        importance = 7 if REMEMBER_RX.search(text) else 6 if LIFE_RX.search(text) else 3
        user_ep = memory.add_episode(self.session, "user", text, privacy=privacy,
                                     importance=importance, emotion=emo.as_json())
        domain = d.get("domain", "chat")
        route, reply, info, recalled_ids, lesson_ids, brief_tokens, brief = "fast_path", None, {}, [], [], None, None
        live_job, live_res, live_from = None, None, 0       # live internet info (connectors/live.py)

        if self.teach_ask_at and (COMMAND_RX.search(text) or domain in ("todo", "time")):
            self.teach_ask_at = 0.0     # he moved on to a command: drop the pending "what should I teach you?"
        # ---- fast paths (no LLM) ----
        from . import cards
        cards.take()                                    # forget a change noted outside a turn (scheduler, web)
        low = psych.minimum_viable_day(emo.label)
        from .brain import instructions, onboarding
        from .life import proactive
        if self.last_nudge and time.time() - self.last_nudge[1] < 180:      # his reaction to her nudge
            proactive.feedback(self.last_nudge[0], "dismissed" if proactive.DISMISS_RX.match(text) else "accepted")
            self.last_nudge = None
        disabled_kind = proactive.disable_from_text(text)
        if domain in ("chat", "memory") and privacy < 2:
            proactive.maybe_followup(text)
        from .brain import keythings
        learned = keythings.capture(text, user_ep) if domain not in ("todo", "time", "control") and not crisis else []
        from .brain import learning
        from .voice.wake import is_stop
        after_offer = bool(re.search(r"anything else\?\s*$", self.last_reply_text or "", re.I)) and bool(NOTHING_RX.match(text))
        from .voice import vocab
        # "no, I said Tejmul" / "spell it T-E-J-M-U-L" / "add Zonuly to your vocabulary": she misheard a WORD (D27) —
        # learn it for the ears; it's not an undo of her last action and not a lesson about how she talks
        taught = None if crisis else vocab.parse(text, self.last_user_text)
        undo = not taught and bool(learning.UNDO_RX.match(text)) and self.last_route == "fast_path" and self.last_action is not None \
            and not after_offer
        # "I didn't understand / what language is this" right after her reply = an implicit correction (REPAIR)
        confused = self.last_reply_text is not None and bool(strategy.CONFUSION_RX.search(text)) \
            and domain not in ("todo", "time") and not crisis
        corrected = (undo or d.is_("is_correction", 0.6) or confused) and not crisis
        learning.score_lessons(self.last_lesson_ids, corrected)
        learning.mark_outcome(self.last_turn_id, "corrected" if corrected else "confirmed")
        inferred_ack = None if d.is_("is_correction", 0.6) or crisis or taught else \
            learning.infer_from_turn(text, self.last_reply_full if self.last_interrupted and self.last_reply_full
                                     else self.last_reply_text, interrupted=self.last_interrupted)

        # ---- the reply strategy: decided HERE, by the brain, before any LLM (D25) ----
        talk = [r["directive"] for r in q(
            "SELECT directive FROM user_directives WHERE status='active' AND category='talk_style' ORDER BY id")]
        rule_saved = False
        if confused and strategy.is_hinglish(self.last_reply_text or "") and not strategy.is_hinglish(text) \
                and strategy.directive_language(talk) != "english":
            # her Hinglish lost him and he speaks English: the evidence is clear — English from now on, saved now
            instructions.apply(instructions.parse("talk in English"), [i for i in (self.last_reply_ep, user_ep) if i])
            talk = [r["directive"] for r in q(
                "SELECT directive FROM user_directives WHERE status='active' AND category='talk_style' ORDER BY id")]
            rule_saved = True
        elif confused:
            learning.note_confusion(text)

        def pick(dom: str) -> strategy.Strategy:
            s = strategy.choose(text, domain=dom, mood=emo.label, mood_conf=emo.conf, arousal=emo.arousal,
                                corrected=corrected, last_reply=self.last_reply_text, directives=talk,
                                crisis_recent=time.time() - self.crisis_at < 1800,
                                pending_offer=(self.last_reply_text or "").rstrip().endswith("?"),
                                voice_mood=bool(emo.voice_label) and emo.voice_conf >= 0.5)
            s.allow_promise = rule_saved
            return s

        strat = pick(domain)
        from . import farewell as bye
        if crisis:
            reply = strategy.crisis_reply(strat.lang)
            self.crisis_at = time.time()
        elif after_offer:
            reply = "Okay, I'm here." if strat.lang == "english" else "Theek hai, main yahin hoon."
        elif taught:
            vocab.add(taught.term, taught.heard, taught.source)
            reply = vocab.confirm(taught)
        elif self.clarify is not None:
            reply, self.clarify = self.clarify.answer(text), None
        elif undo:
            note = learning.undo_last(self.last_action)
            self.clarify = learning.Clarify(self.last_user_text or "", note)
            reply = self.clarify.question()
        elif inferred_ack:
            reply = inferred_ack
        elif (is_stop(text) or bye.is_bye(text)) and self.onboarding is None and self.chunker is None and self.woop is None:
            reply, self.ended = bye.farewell(text, self.last_mood, now), True
        elif self.nudged and time.time() - self.nudged < 900 and self.last_strategy is not None \
                and self.last_strategy.name == "NUDGE" and not re.search(r"\b(alarm|remind|timer|todo)\b", text, re.I):
            reply = strategy.nudge_followup(now)        # one warning only — then "As you wish."
            strat = strategy.make("DO", strat.lang)
        elif disabled_kind:
            reply = f"Okay — no more {disabled_kind.replace('_', ' ')} reminders from me."
        elif switched := self._intro_switch(text):
            reply = switched
        elif _awaiting_label() and len(text.split()) <= 12 and not bye.is_bye(text):
            from .life import alarms           # she just asked "What's it for?" about a reminder
            reply = alarms.set_label(text)
        elif domain not in ("todo", "time") and (inst := instructions.parse(text)):
            reply = instructions.apply(inst, [i for i in (self.last_reply_ep, user_ep) if i])
            strat = strategy.make("REPAIR" if corrected else "DO", strat.lang)
        elif strat.name == "QUIET" and self.onboarding is None and self.chunker is None and self.woop is None \
                and self.pending is None:
            reply = strategy.quiet_reply(text, strat.lang, self.last_reply_text)
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
            from .tutor import ASK_TOPIC, launch
            reply = launch(*tr)
            self.teach_ask_at = time.time() if reply == ASK_TOPIC else 0.0
        elif (time.time() - self.teach_ask_at < TEACH_ASK_S and len(text.split()) <= 10
              and (domain != "control" or CANCEL_ASK_RX.match(text))):
            from .tutor import launch
            self.teach_ask_at = 0.0             # "what should I teach you?" → "lexical analysis" (or "never mind")
            reply = ("Okay, another time." if NOTHING_RX.match(text) or re.search(r"\b(never ?mind|cancel|leave it|"
                     r"rehne do|chhodo)\b", text, re.I) else launch(text.strip(" .?!")))
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
            _, reply = lessons.capture(text, mood=self.last_mood, lang=strat.lang,
                                       source_episode_ids=[i for i in (self.last_reply_ep, user_ep) if i])
        elif learned and len(text.split()) <= 14 and self.onboarding is None:
            reply = "Noted — " + ", ".join(learned) + "."
        elif REMEMBER_RX.search(text) and not text.rstrip().endswith("?") and domain in ("memory", "chat"):
            reply = "Yaad rakh liya." if re.search(r"\b(yaad|rakhna|mat|hai)\b", text, re.I) else "Noted — I'll remember that."
        elif domain == "control":
            reply = handlers.control(text)
        elif domain == "todo":
            if psych.minimum_viable_day(emo.label) and handlers.LIST_RX.search(text):
                reply = handlers.todo_list(limit=1) + " That one's enough for today."
            else:
                reply = handlers.todo(text)
        elif domain == "time":
            reply = handlers.timeish(text)

        if reply is None and strat.name == "DO":     # the classifier said todo/time but no fast path took it: talk
            strat = pick("chat")
        if reply is None and live_job is None and live_res is None and self.nudged is None and not crisis \
                and strat.name in ("ACKNOWLEDGE", "BANTER", "ANSWER", "SOLVE") and (nf := strategy.nudge_fact(now)):
            from . import profile                     # late night + an early event: say the one fact, once
            reply = strategy.nudge_text(nf, now, profile.call() if profile.get("name") else None)
            strat, self.nudged = strategy.make("NUDGE", strat.lang), time.time()
        if live_job is not None or live_res is not None:     # live news/web: read it out, may offer "want more?"
            strat = strategy.make("ANSWER", strat.lang, max_words=90, ask=True, callbacks=False)

        if reply is not None and (domain in ("todo", "time", "control") or PLAN_RX.search(text)):
            q("UPDATE episodes SET importance = 1 WHERE id = %s", (user_ep,))  # commands aren't memories

        # ---- LLM path ----
        if reply is None:
            t = time.perf_counter()
            mems = memory.recall(text, qvec, max_privacy=min(privacy, 1) if privacy < 2 else 2, k=8)
            mems = [m for m in mems if m["episode_id"] != user_ep and m["sim"] >= 0.25
                    and m.get("importance", 3) > 1]
            recent = memory.recent_turns(self.session)[:-1]
            asked = strategy.asks_about_past(text, domain)
            # G1–G8: only memories a friend would bring up right now reach the LLM (no random "interview?" quizzes)
            mems, strat.avoid_terms, _ = gate.filter_memories(
                mems, text=text, recent_texts=[r["text"] for r in recent if r["speaker"] == "user"][-2:],
                asked=asked, mood=emo.label, now=now, cap=3 if strat.callbacks else 1)
            seeds = memory.seed_entities(text, [m["episode_id"] for m in mems])
            facts = memory.current_facts(seeds, max_privacy=min(privacy, 1))
            les = lessons.match(qvec, mood=emo.label, bucket=lessons.time_bucket(now))
            docs = ingest.recall(text, qvec, max_privacy=min(privacy, 1) if privacy < 2 else 2)
            lat["recall"] = (time.perf_counter() - t) * 1000
            recalled_ids = [m["episode_id"] for m in mems]
            lesson_ids = [l["id"] for l in les]
            self.last_used = {
                "memories": len(mems),          # a count only: past conversations are never sent to a UI
                "facts": [f["fact_text"] for f in facts[:8]],
                "docs": list(dict.fromkeys(f"{x['title']}" + (f" › {x['section'].split(' > ')[-1]}" if x.get("section") else "")
                                           for x in docs))[:4],
                "lessons": [l.get("guidance", "") for l in les[:4]]}
            loops = None                                 # open loops only when he's talking about them (no random
            if domain in ("todo", "time") and re.search(   # "you have a reminder at 4" in small talk)
                    r"\b(todos?|tasks?|reminders?|alarms?|kaam|list|plan|pending|deadline|due)\b", text, re.I):
                loops = handlers.todo_list() + " " + handlers.list_intents()
            unknown = self._unknown_name(text, user_ep) if asked else None
            if unknown and any(re.search(rf"\b{unknown}\b", x["text"], re.I) for x in docs):
                unknown = None
            if unknown:                                  # honest about a memory gap — no LLM, nothing invented
                reply = (f"{unknown} ke baare mein mere paas kuch nahi hai." if strat.lang == "hinglish"
                         else f"Nothing about {unknown} in my memory.")
                live_job = None
        if self._spec and (reply is not None or live_job is not None or live_res is not None):
            raise NotSpeculable("not a plain chat turn")         # (only DB writes so far: rolled back)
        mark = None
        if reply is None:
            # voice: the LLM also says whether he had finished (● ◐ ○). Not on the web, not for tools, not for a
            # question, and not twice in a row (a weak model that always says ◐ must never silence her)
            tools_turn = live_job is None and live_res is None and (domain == "tool" or bool(TOOL_HINT_RX.search(text)))
            markers = (self.channel == "voice" and on_delta is not None and not text.rstrip().endswith("?")
                       and time.time() - self.incomplete_at > 30 and not tools_turn)
            brief, brief_tokens = compiler.build(
                text=text, now=now, privacy=privacy, emotion_hint=emo.hint(), tone=psych.tone(emo.label),
                recent=recent, memories=mems, facts=facts, lessons=les,
                open_loops=loops, talk_directives=talk, mvd=psych.minimum_viable_day(emo.label), docs=docs,
                strategy=strat, rule_saved=rule_saved, wins=gate.wins(min(privacy, 1)) if strat.reframe else None,
                markers=markers)
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
            if self._spec and (use_tools or on_delta is None):
                raise NotSpeculable("tools")
            psych.set_policy(strat)                     # StreamLint enforces this turn's shape on the spoken stream
            try:
                if on_delta is not None and not use_tools:      # stream: she starts talking at the first clause
                    info = {}
                    ms = turnmark.MarkerStream()             # the marker is never spoken: strip it as it streams
                    for piece in router.stream([{"role": "system", "content": brief}, {"role": "user", "content": text}],
                                               privacy=privacy, info=info):
                        piece = ms.feed(piece)
                        if ms.incomplete:
                            break                            # ◐ / ○: stop the LLM, say nothing
                        if piece:
                            self.streamed = True
                            on_delta(piece)
                    tail = "" if ms.incomplete else ms.flush()
                    if tail and not ms.incomplete:
                        self.streamed = True
                        on_delta(tail)
                    mark = ms.marker
                    reply = "" if ms.incomplete else info["text"]
                    lat["first_token"] = info.get("first_ms", 0)
                else:
                    if use_tools:
                        ack("tools")
                    reply, info = self._llm(brief, text, qvec, privacy, use_tools=use_tools)
                route = "llm"
                lat["llm"] = info.get("ms", 0.0)
            except router.NoProvider as e:
                route = "degraded"
                if privacy >= 2:
                    reply = "That sounds private, so I'm keeping it on this Mac. "
                elif time.time() - self._offline_said_at > 3600:
                    reply = "My head's a bit foggy right now, so I can't think that one through. "
                    self._offline_said_at = time.time()
                else:
                    reply = ""
                if strat.name == "REPAIR":
                    reply = ("Sorry about that. English from now on." if rule_saved
                             else "Sorry — let me keep it simpler. Say that once more?")
                elif live_res is not None:              # no LLM: read the top headlines out directly
                    reply += live.speak(live_res, start_at=live_from)
                elif docs and (not mems or docs[0]["sim"] > mems[0]["sim"]) and docs[0]["sim"] >= 0.4:
                    d0 = docs[0]
                    reply += f"From your doc “{d0['title']}”: {d0['text'][:300]}"
                elif mems and mems[0]["sim"] >= 0.4:
                    m = mems[0]
                    reply += f"Here's what I remember from {m['occurred_at'].astimezone(CFG.tz):%d %b}: “{m['text']}”"
                elif reply:
                    reply += "I can still handle your to-dos, alarms and reminders, and I'll remember what you said."
                else:
                    reply = "Hmm, that one I can't answer right now — but I've noted it."
                info = {"error": str(e)}

        if route == "llm":
            m2, reply = turnmark.split(reply or "")
            mark = mark or m2
            if turnmark.is_incomplete(mark) and markers:
                return self._incomplete(user_ep, mark)
            self.last_marker = mark
        if route == "llm" and not (self.pending is not None and reply.startswith("Should I go ahead")):
            reply = psych.enforce(reply, strat, user_text=text)   # strategy shape, banned tics, machine-talk — in code
            if mems and not strategy.asks_about_past(text, domain):
                gate.mark_volunteered(reply, mems)      # G4 clocks start only for memories she actually used
        else:
            reply = psych.lint(reply, user_text=text)
        m = re.search(r"\((task )?#(\d+)\)", reply)   # ids stay internal (undo); never spoken or shown
        self.last_action = ({"type": "task" if m.group(1) else "intent", "id": int(m.group(2))}
                            if m and route == "fast_path" else None)
        reply = psych.EMOJI.sub("", re.sub(r"\s*\((task |lesson )?#?L?\d+\)", "", reply)).strip()
        if route == "fast_path" and m and re.match(r"(Got it|Done|Timer set)\b", reply) and not reply.endswith("?"):
            reply += " Anything else?"                  # confirm-and-close: only after a completed action
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
        strategy.log(turn["id"], strat)                 # labels for a future Laya reply_strategy head
        memory.touch(recalled_ids)
        lessons.mark_applied(lesson_ids)
        self.last_turn_id, self.last_lesson_ids = turn["id"], lesson_ids
        self.last_reply_text, self.last_user_text, self.last_route = reply, text, route
        self.last_reply_full, self.last_strategy = None, strat
        self.last_interrupted = False
        self.live_last = (live_res, live_from + 3, time.time()) if live_res is not None and live_res.items else None
        try:                                    # what to SHOW on screen while she says it (desktop overlay card)
            self.last_card = cards.for_turn(text, str(domain), reply, self.last_action, live_res, live_from,
                                            event=cards.take())
        except Exception as e:
            print(f"[cards] {e}")
            self.last_card = None
        self.last_user_ep, self.last_reply_ep, self.last_mood = user_ep, reply_ep, emo.label
        self.last_debug = {"domain": str(domain), "domain_conf": round(d.conf.get("domain", 0), 2), "mood": str(emo.label), "mood_conf": round(emo.conf, 2),
                           "strategy": strat.name, "lang": strat.lang,
                           "privacy": privacy, "route": route, "provider": info.get("provider"),
                           "latency_ms": {k: round(v) for k, v in lat.items()},
                           "live": None if live_res is None else {
                               "kind": live_res.req.kind, "query": live_res.req.query, "items": len(live_res.items),
                               "ok": live_res.ok, "failed": live_res.failed}}
        return reply
