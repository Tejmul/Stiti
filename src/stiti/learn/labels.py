"""Emotion labels from his own words — no forms (D28).

Sources (weights are training sample weights):
  self_report  "I'm so tired", "thak gaya hoon", "tension ho rahi hai"        → +label 1.0 on that turn
  neighbour    the turns around a self-report (same session, ±2 turns, ≤3 min)  → +label 0.5
  correction   "I'm not angry", "main udaas nahi hoon", "why do you think I'm sad"
               → NOT-label 1.0 on that turn, 0.7 on the previous turn when she had read that mood
  pseudo       text mood (≥0.8) agrees with the generic voice read               → +label 0.3 (never used as truth)
  checkin      opt-in end-of-day "how was your mood today?" answer               → +label 0.2 on that day's turns
Only first-person statements count: "my mom is tired", "are you tired?", "you're angry", "if I'm late" don't.
`rebuild()` recomputes the automatic labels from scratch each night (idempotent); checkin/manual labels are kept.
"""
from __future__ import annotations

import re
from datetime import date

from ..config import CFG
from ..db import q

AUTO_SOURCES = ("self_report", "neighbour", "correction", "pseudo")
HUMAN_SOURCES = ("self_report", "neighbour", "correction", "checkin", "manual")
W = {"self_report": 1.0, "neighbour": 0.5, "correction": 1.0, "correction_prev": 0.7, "pseudo": 0.3, "checkin": 0.2}
NEIGHBOUR_TURNS, NEIGHBOUR_S = 2, 180

# mood words (EN + Hinglish). "calm" only counts with an explicit "I'm …" (see CALM_RX): "okay"/"fine" are everywhere.
LEX = {
    "tired": r"tired|exhausted|sleepy|drained|worn out|knackered|burn(?:t|ed) out|thak(?:a|i|e)?(?: (?:gaya|gayi|gaye|hua|hui))?|"
             r"thakaan|thakan|neend aa rahi|neend aa raha|so jaana hai",
    "stressed": r"stressed(?: out)?|anxious|tense|overwhelmed|nervous|worried|panicking|under (?:a lot of )?pressure|"
                r"tension(?: ho rahi| hai| mein| me)|pareshan|ghabra(?:hat|ya|yi|a raha|a rahi)|stress mein|stress me|"
                r"dar lag raha",
    "angry": r"angry|pissed(?: off)?|irritated|annoyed|frustrated|furious|fed up|gussa|gusse|chidh|naraz|"
             r"irritate ho|dimag kharab",
    "sad": r"sad|feeling low|feeling down|so low|very low|upset|depressed|lonely|heartbroken|hurt|udaas|udas|dukhi|"
           r"bura lag raha|mann nahi lag|man nahi lag|rona aa raha",
    "happy": r"happy|excited|thrilled|glad|pumped|over the moon|on top of the world|khush|maza aa (?:gaya|raha)|"
             r"mazaa aa (?:gaya|raha)|bahut accha lag raha|bohot accha lag raha",
}
MOOD_RX = {m: re.compile(rf"\b(?:{p})\b", re.I) for m, p in LEX.items()}
CALM_RX = re.compile(r"\b(?:i'?m|i am|i feel|feeling|i'?m feeling|i'?m doing)\s+(?:totally |pretty |quite |all |very )?"
                     r"(?:fine|okay|ok|good|great|relaxed|calm|chill|alright|well)\b|"
                     r"\b(?:main |mai |mein )?(?:theek|thik|chill|shaant|relaxed)\s+(?:hoon|hu|hun)\b", re.I)
FIRST_EN = re.compile(r"\b(?:i'?m|i am|i feel|i'?ve been|i was|i got|i get|makes me|making me|me so|i'?m getting|"
                      r"im|i|feeling|me)\b", re.I)
# elliptical first person: "So tired yaar.", "Exhausted.", "bahut thak gaya hoon"
ELLIPSIS = re.compile(r"^\W*(?:(?:so|very|really|too|super|totally|bahut|bohot|bht|kaafi|itna|ekdum|thoda|yaar|man|bro|ugh|"
                      r"uff|oh|god|honestly)\W+)*$", re.I)
FIRST_HI = re.compile(r"\b(?:main|mai|mein|mujhe|mujhko|mereko|apun|hoon|hu|hun)\b|"
                      r"\b(?:ho rah[ai]|aa rah[ai]|lag rah[ai]|gaya|gayi)\b", re.I)
THIRD = re.compile(r"\b(?:he|she|they|his|her|their|him|them|mom|mum|dad|papa|mummy|bhai|didi|sister|brother|friend|"
                   r"boss|use|usko|unko|uska|uski|woh|wo|vo|you|you'?re|your|tum|tu|aap|tumhe|aapko)\b", re.I)
QUESTION = re.compile(r"^\s*(?:are|am|is|do|does|did|were|why are|kya|kyun|kyu)\b|\?\s*$", re.I)
HYPO = re.compile(r"\b(?:if|agar|when you|jab tum)\b", re.I)
NEG_BEFORE = re.compile(r"(?:\b(?:not|never|no longer|nahi|nahin|nai)\b|n't)(?:\W+\w+){0,2}\W*$", re.I)
NEG_AFTER = re.compile(r"^\W*(?:\w+\W+){0,1}(?:nahi|nahin|nai)\b", re.I)    # not "na": a tag ("thak gaya na")
# "why do you think I'm angry", "kisne kaha main udaas hoon", "stop saying I'm stressed" → denial even with no "not"
DENY_RX = re.compile(r"\b(?:why do you think|why would you think|what makes you think|who said|kisne kaha|kaun bola|"
                     r"stop saying|why would i be)\b", re.I)
CLAUSE_SPLIT = re.compile(r"[,.;!?]|\b(?:but|just|bas|sirf|par|lekin|actually|balki)\b", re.I)


def _clauses(text: str) -> list[tuple[int, str]]:
    out, pos = [], 0
    for m in CLAUSE_SPLIT.finditer(text):
        out.append((pos, text[pos:m.start()]))
        pos = m.end()
    out.append((pos, text[pos:]))
    return [(p, c) for p, c in out if c.strip()]


def extract(text: str) -> list[tuple[str, int, str]]:
    """[(mood, +1|-1, evidence)] he states about HIMSELF in this text. Empty for anything else."""
    text = (text or "").strip()
    if not text:
        return []
    out: dict[str, tuple[int, str]] = {}
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sent in sentences:
        deny = bool(DENY_RX.search(sent))
        if QUESTION.search(sent) and not deny:
            continue
        if HYPO.search(sent) and not deny:
            continue
        first_in_sent = bool(FIRST_EN.search(sent) or FIRST_HI.search(sent))
        for _, clause in _clauses(sent):
            found = [(m, rx.search(clause)) for m, rx in MOOD_RX.items()]
            calm = CALM_RX.search(clause)
            if calm:
                found.append(("calm", calm))
            for mood, hit in found:
                if not hit:
                    continue
                before, after = clause[:hit.start()], clause[hit.end():]
                if THIRD.search(before) and not deny and not re.search(r"\b(?:i'?m|i am|me|main|mujhe|mujhko)\b", before, re.I):
                    continue                    # "my mom is tired", "you're angry", "tum gussa ho"
                if not (first_in_sent or ELLIPSIS.match(before)):
                    continue
                neg = bool(NEG_BEFORE.search(before) or NEG_AFTER.search(after)) or deny
                if mood == "tired" and re.search(r"neend nahi", clause, re.I):
                    neg = True
                pol = -1 if neg else 1
                if mood not in out or pol == -1:
                    out[mood] = (pol, hit.group(0))
    return [(m, p, ev) for m, (p, ev) in out.items()]


def rebuild() -> dict:
    """Recompute automatic labels for every recorded turn (seconds for thousands of rows)."""
    q("DELETE FROM emotion_labels WHERE source = ANY(%s)", (list(AUTO_SOURCES),))
    rows = q("""SELECT id, session_id, recorded_at, transcript, voice_label, fused_label, text_label, text_conf,
                       e2v_label, e2v_conf, prosody_label FROM voice_turns ORDER BY session_id NULLS FIRST, recorded_at, id""")
    ins: list[tuple] = []
    stats = {"self_report": 0, "neighbour": 0, "correction": 0, "pseudo": 0}
    reported: set[int] = set()
    found = {r["id"]: extract(r["transcript"]) for r in rows}
    for i, r in enumerate(rows):
        for mood, pol, ev in found[r["id"]]:
            if pol > 0:
                ins.append((r["id"], mood, 1, W["self_report"], "self_report", ev))
                stats["self_report"] += 1
                reported.add(r["id"])
                continue
            prev = rows[i - 1] if i > 0 else None
            read_prev = (prev is not None and prev["session_id"] == r["session_id"]
                         and (r["recorded_at"] - prev["recorded_at"]).total_seconds() <= NEIGHBOUR_S
                         and mood in (prev["fused_label"], prev["voice_label"]))
            read_now = mood in (r["fused_label"], r["voice_label"])
            src = "correction" if (read_prev or read_now) else "self_report"
            ins.append((r["id"], mood, -1, W["correction"], src, ev))
            stats[src] += 1
            if read_prev:
                ins.append((prev["id"], mood, -1, W["correction_prev"], "correction", ev))
                stats["correction"] += 1
    # neighbours of positive self-reports (his mood doesn't flip between two sentences)
    for i, r in enumerate(rows):
        pos = [(m, ev) for m, p, ev in found[r["id"]] if p > 0]
        if not pos:
            continue
        for j in range(max(0, i - NEIGHBOUR_TURNS), min(len(rows), i + NEIGHBOUR_TURNS + 1)):
            n = rows[j]
            if j == i or n["id"] in reported or n["session_id"] != r["session_id"]:
                continue
            if abs((n["recorded_at"] - r["recorded_at"]).total_seconds()) > NEIGHBOUR_S:
                continue
            for m, ev in pos:
                if not any(mm == m and pp < 0 for mm, pp, _ in found[n["id"]]):
                    ins.append((n["id"], m, 1, W["neighbour"], "neighbour", f"near: {ev}"))
                    stats["neighbour"] += 1
    # pseudo-labels: text mood and the generic voice read agree (co-training); only where he said nothing explicit
    labelled = {t[0] for t in ins}
    for r in rows:
        if r["id"] in labelled or not r["text_label"] or (r["text_conf"] or 0) < 0.8:
            continue
        agree = ((r["e2v_label"] == r["text_label"] and (r["e2v_conf"] or 0) >= 0.5)
                 or (r["prosody_label"] == r["text_label"] and r["text_label"] != "calm"))
        if agree:
            ins.append((r["id"], r["text_label"], 1, W["pseudo"], "pseudo", "text+voice agree"))
            stats["pseudo"] += 1
    if ins:
        from ..db import conn
        with conn().cursor() as cur:
            cur.executemany("""INSERT INTO emotion_labels(voice_turn_id, label, polarity, weight, source, evidence)
                               VALUES (%s,%s,%s,%s,%s,%s)""", ins)
    return stats


def daily_checkin(answer: str, day: date) -> int:
    """Opt-in end-of-day answer ("pretty stressed today", "aaj khush tha") → a weak label on that day's turns."""
    pos = [m for m, p, _ in extract(answer) if p > 0]
    if not pos:
        return 0
    rows = q("SELECT id FROM voice_turns WHERE (recorded_at AT TIME ZONE %s)::date = %s", (CFG.tz.key, day))
    for r in rows:
        q("""INSERT INTO emotion_labels(voice_turn_id, label, polarity, weight, source, evidence)
             VALUES (%s,%s,1,%s,'checkin',%s)""", (r["id"], pos[0], W["checkin"], answer[:120]))
    return len(rows)
