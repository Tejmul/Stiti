"""Exemplar intent/mood classifier on the already-loaded embedder (~7 ms, ~0 extra RAM).

Stiti's hot-path "System 1" until Laya fits the M2 (pilot: Laya zero-shot 13-15/30 on domain,
200-500 ms, 2.7-2.9 GB RSS with torch — see docs/DECISIONS.md D10).
Learns without training: owner-confirmed examples append to ~/.stiti/exemplars.jsonl.

D50: a few thousand PUBLIC English examples (MASSIVE / CLINC150 / PRESTO train splits, built by
scripts/build_exemplars.py into ~/.stiti/data/public_exemplars.npz with their vectors) vote next to the built-in
and owner-confirmed ones for the domain. His own examples win: they get OWNER_BONUS on their similarity. No file →
exactly the old behaviour. STITI_PUBLIC_EX=off switches the public set off.
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache

import numpy as np

from . import embed
from .config import CFG

DOMAIN_EX = {
    "todo": ["add a task to my list", "put pay electricity bill on my todo", "todo mein daal do doodh lena",
             "show my pending tasks", "list mein kya bacha hai", "what do I still need to do",
             "mark laundry as done", "ye kaam ho gaya, done kar do", "naya task: report bhejna",
             "remove buy shoes from my list", "kaunse kaam pending hain", "naa list lo milk add cheyyi",
             "ఆ పని అయిపోయింది"],
    "time": ["wake me up at 7", "alarm laga do 5:30 ka", "remind me tomorrow morning to call the bank",
             "yaad dila dena shaam ko dawai leni hai", "set a timer for 15 minutes", "20 minute ka timer",
             "remind me in an hour to drink water", "parso subah 8 baje alarm", "cancel my 6 am alarm",
             "kal subah yaad dilana meeting hai", "saayantram 5 ki gurthu cheyyi", "సాయంత్రం ఐదు గంటలకు గుర్తు చేయి"],
    "memory": ["what did I tell you about my brother", "when is Priya's wedding",
               "maine pichli baar kya kaha tha project ke baare mein", "do you remember my favourite food",
               "who is Rahul", "what happened at office last Monday", "mere dost ka naam kya tha jo Delhi gaya",
               "what did I say yesterday about the gym", "kab hai papa ka birthday", "where did I keep my passport"],
    "chat": ["I had such a long day", "aaj mood off hai", "tell me something interesting",
             "I'm really excited about the trip", "kya lagta hai tumhe, I should switch jobs?",
             "explain how black holes work", "yaar bahut bore ho raha hoon", "I can't believe she said that",
             "kuch motivational bolo", "how are you doing today", "what's a good book to read",
             "bas aise hi baat karne ka mann tha",
             # life updates with people + days (2026-11-11: these went to tool / time / memory / control)
             "my uncle is coming over this weekend", "my brother's wedding is next month",
             "dad is travelling to Jaipur tomorrow", "I have a test on Friday", "my roommate got an internship today",
             "my friend got a job at Google", "I'm meeting my friends tonight", "kal ghar pe guests aa rahe hain",
             "I'm so tired of this bug", "I'm done for today, my brain is fried", "ugh this assignment is killing me",
             # Telugu / Tenglish chat
             "repu maa intiki friends vastunnaru", "naaku chala bore ga undi", "ammaku next week birthday",
             "ఈ రోజు ఆఫీస్ లో చాలా పని ఉంది", "నా ఫ్రెండ్ కి జాబ్ వచ్చింది", "మా అన్నయ్య రేపు వస్తున్నాడు", "ఈ వారం నాకు పరీక్షలు ఉన్నాయి"],
    "tool": ["what's on my calendar today", "check my email", "open chrome", "volume kam karo",
             "search google for flight prices", "read my latest mail", "play music on spotify",
             "find the pdf I downloaded yesterday", "schedule a meeting with Arjun on Friday",
             "website pe check karo weather"],
    "feedback": ["your answers are too long", "don't call me sir", "you talk too much",
                 "please stop using so many emojis", "aise baat mat karo mujhse", "tum bahut lecture dete ho",
                 "I told you not to remind me during work", "be more direct with me",
                 "jab main gusse mein hoon tab advice mat dena", "that was rude, don't do that"],
    "control": ["stop", "ruk jao", "repeat that", "phir se bolo", "louder please", "dheere bolo",
                "cancel", "chup", "say that again", "never mind", "bas bas", "pause", "aagu", "malli cheppu", "ఆపు"],
}

MOOD_EX = {
    "calm": ["okay", "fine, let's do it", "theek hai", "sounds good", "normal day", "chalo dekhte hain",
             "what are my tasks", "where does my brother live", "set an alarm for 7", "what's the weather",
             "add eggs to my list", "kab hai meeting", "tell me about black holes", "remind me to call him",
             "what did I say yesterday", "show my reminders", "kya haal hai", "open spotify"],
    "happy": ["I'm so happy today", "yay it worked", "maza aa gaya", "best day ever", "I got the offer!",
              "bahut khush hoon"],
    "stressed": ["I have so much to do and no time", "deadline sir pe hai", "I'm freaking out about tomorrow",
                 "tension ho rahi hai", "everything is piling up", "kuch samajh nahi aa raha kya karun"],
    "angry": ["this is so annoying", "bahut gussa aa raha hai", "I'm pissed off", "dimag kharab ho gaya",
              "how dare he", "irritate mat karo"],
    "sad": ["I feel so low", "mann nahi lag raha", "I miss her", "kuch accha nahi lag raha",
            "I feel lonely", "dil toot gaya"],
    "tired": ["I'm exhausted", "bahut thak gaya hoon", "so sleepy", "neend aa rahi hai",
              "long day, I'm drained", "energy nahi hai"],
}


def _load_learned() -> dict[str, list[str]]:
    p = CFG.home / "exemplars.jsonl"
    extra: dict[str, list[str]] = {}
    if p.exists():
        for line in p.read_text().splitlines():
            r = json.loads(line)
            extra.setdefault(f"{r['kind']}:{r['label']}", []).append(r["text"])
    return extra


@lru_cache(maxsize=1)
def _index():
    learned = _load_learned()
    out = {}
    for kind, table in (("domain", DOMAIN_EX), ("mood", MOOD_EX)):
        labels, texts = [], []
        for lab, exs in table.items():
            for t in exs + learned.get(f"{kind}:{lab}", []):
                labels.append(lab)
                texts.append(t)
        vecs = np.stack([v.to_numpy().astype(np.float32) for v in embed.embed_docs(texts)])
        out[kind] = (np.array(labels), vecs)
    return out


OWNER_BONUS = 0.03          # his own / built-in examples beat an equally close public one
PUBLIC_FILE = "public_exemplars.npz"


@lru_cache(maxsize=1)
def _public():
    """(labels, vectors, owner flags) of the public example set, or None (no file, switched off, or built with
    another embedder)."""
    p = CFG.home / "data" / PUBLIC_FILE
    if os.getenv("STITI_PUBLIC_EX", "on") == "off" or not p.exists():
        return None
    try:
        with np.load(p, allow_pickle=False) as z:           # arrays only: nothing in the file is ever executed
            if str(z["model"]) != embed.EMBED_MODEL:
                print(f"[intent] {p.name} was built with {z['model']}; rebuild it (scripts/build_exemplars.py)")
                return None
            labels, vecs = z["labels"], z["vecs"].astype(np.float32)
            owner = z["owner"].astype(bool) if "owner" in z.files else np.zeros(len(labels), bool)
        if vecs.ndim != 2 or vecs.shape != (len(labels), embed.DIM) or len(owner) != len(labels):
            return None
        return labels, vecs, owner          # owner = our own counterweight lines shipped in the same file
    except Exception as e:
        print(f"[intent] public examples not loaded: {type(e).__name__}: {e}")
        return None


def public_count() -> int:
    pub = _public()
    return 0 if pub is None else int((~pub[2]).sum())


# ---- who may vote (D50) ----
# The public sets are REQUESTS people make to an assistant. They say nothing about a plain statement of his life
# ("Mummy is coming home tomorrow", "My mom called me this morning") — and a pile of calendar / call / reminder
# requests sitting next to such a line would drag it into `tool` / `time`. So public command examples vote only when
# his sentence is itself shaped like a request or a question; a statement is judged by his own and the built-in
# examples, exactly as before, plus the public small-talk lines.
_LEAD = r"^\W*(?:(?:ok(?:ay)?|so|and|well|oh|hey|hi|yeah|yes|no|actually|also|btw|by the way|guess what|you know|stiti)[,!. ]+)*"
_QUESTION_RX = re.compile(_LEAD + r"(?:what|whats|what's|when|where|who|whom|whose|which|how|why|is|are|am|was|were|do|"
                          r"does|did|can|could|will|would|should|shall|have|has|had|any|may)\b", re.I)
_ASK_RX = re.compile(r"\b(?:please|can you|could you|would you|will you|remind me|wake me|let me know|tell me|show me|"
                     r"help me|make sure|don'?t forget)\b", re.I)
_I_WANT_RX = re.compile(_LEAD + r"i(?:'d| would| really| just| also)*(?: do not| don'?t)? (?:want|need|like|love|wanna|"
                        r"wish)\b", re.I)
_SUBJECT_RX = re.compile(_LEAD + r"(?:i|i'm|im|i've|ive|i'd|i'll|we|we're|we've|we'll|my|our|he|he's|she|she's|they|they're|"
                         r"it|it's|its|there|there's|the|this|that|his|her|their|today|tomorrow|yesterday|tonight|"
                         r"mom|mum|mummy|mumma|mother|dad|daddy|papa|father|grandpa|grandma|nani|nana|dadi|dada|"
                         r"bhai|bhaiya|didi|akka|anna|amma|nanna)\b", re.I)
_FINITE = (r"(?:is|are|was|were|has|have|had|got|gets|will|would|won't|can't|couldn't|didn't|doesn't|isn't|wasn't|"
           r"came|comes|went|goes|said|says|told|called|wants|wanted|needs|needed|made|gave|took|left|lost|won|"
           r"[a-z]{3,}ed)")
_NAME_RX = re.compile(r"^\W*[A-Z][a-z]+(?:'s [a-z]+)? (?:" + _FINITE + r"|[a-z]{3,}s)\b")      # "Rahul got placed …"
# "Play songs by Arijit" / "Show reminders" also start with a capital and a word ending in s: a command verb first
# means a request, never "Name + verb".
_VERBS = frozenset("""add set play show tell remind make remove delete send put start text read call create give cancel
check open get repeat take turn resume email stop schedule find display clear skip list erase bring change listen help
dial reply wake look say write notify shuffle use tune pull keep switch confirm run update cross enter continue begin
ring alert provide search undo mute pause snooze mark book order define explain describe translate spell calculate
convert please okay thanks thank sorry good let lets never dont don't move note save log tick finish plan teach
google ask answer wait hold go close lower raise increase decrease reduce""".split())


def is_statement(text: str) -> bool:
    """A plain statement ("My sister is flying in on Thursday", "I woke up at five") — not a question, not an ask."""
    t = (text or "").strip()
    if not t or t.endswith("?") or _QUESTION_RX.match(t) or _ASK_RX.search(t) or _I_WANT_RX.match(t):
        return False
    if _SUBJECT_RX.match(t):
        return True
    first = re.match(r"\W*([A-Za-z']+)", t)
    return bool(_NAME_RX.match(t)) and (first is None or first.group(1).lower() not in _VERBS)


TOP_PUBLIC = 3
PUBLIC_ON_STATEMENTS = ("chat",)        # the only label from the file that may vote on a plain statement
# The words around a to-do or a reminder say what he wants; the words INSIDE it don't ("add call the placement cell",
# "remind me to email Sam", "mark play football as done"): public "call …" / "email …" / "play …" requests must not
# pull those into `tool`. When the frame is there, only public rows of that label (and small talk) vote, and the
# frame's label gets FRAME_BONUS.
FRAME_BONUS = 0.08
FAST_LABELS, FAST_FLOOR = ("todo", "time", "control"), 0.44    # (dev set: no right command scored under 0.47)
_FRAMES = (
    ("todo", re.compile(_LEAD + r"(?:please )?add\b(?!.*\b(?:calendar|playlist|contacts?|cart|queue|schedule|alarm|"
                        r"reminders?|timer|event|meeting|appointment)\b)|"
                        r"\b(?:to|on|in|from|off) (?:my|the) (?:to-?do |todo |tasks? |shopping |grocery )?list\b|"
                        r"\bto-?dos?\b|\bmy tasks?\b|\bmark\b.{1,60}\bdone\b", re.I)),
    ("time", re.compile(r"\b(?:remind me|wake me(?: up)?|(?:set|make|create|start|cancel|delete|remove|snooze|stop|"
                        r"turn off|move|change)(?: up)? (?:an?|the|my|that|another)? ?(?:[\w:.-]+ ){0,3}(?:alarm|timer|"
                        r"reminder)s?)\b", re.I)),
)


def frame(text: str) -> str | None:
    """`todo` / `time` when his sentence is built like a to-do or an alarm / reminder / timer request, else None."""
    for label, rx in _FRAMES:
        if rx.search(text or ""):
            return label
    return None


def classify(qvec: np.ndarray, kind: str, top: int = 3, text: str | None = None) -> tuple[str, float, dict[str, float]]:
    """text = his words (only read to tell a statement from a request — see above)."""
    labels, vecs = _index()[kind]
    sims = vecs @ qvec
    pub = _public() if kind == "domain" and text is not None else None
    framed = None
    if pub is not None:
        plabels, psims = pub[0], pub[1] @ qvec + OWNER_BONUS * pub[2]
        framed = frame(text)
        if is_statement(text):
            keep = np.isin(plabels, PUBLIC_ON_STATEMENTS)
            plabels, psims = plabels[keep], psims[keep]
        elif framed:
            keep = np.isin(plabels, (framed, "chat"))
            plabels, psims = plabels[keep], psims[keep]
            sims = sims + FRAME_BONUS * (labels == framed)
            psims = psims + FRAME_BONUS * (plabels == framed)
        labels = np.concatenate([labels, plabels])
        sims = np.concatenate([sims + OWNER_BONUS, psims])
    scores = {}
    for lab in dict.fromkeys(labels):
        s = np.sort(sims[labels == lab])[::-1][:(TOP_PUBLIC if pub is not None else top)]
        scores[lab] = float(s.mean())
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    if pub is not None and not framed and ranked[0][0] in FAST_LABELS and ranked[0][1] < FAST_FLOOR:
        # nothing he could have meant as a command looks like this ("what's the difference between a list and a
        # tuple?" → todo at 0.37, and she read out his to-do list): a fast path needs examples that resemble it
        ranked = [kv for kv in ranked if kv[0] not in FAST_LABELS] + [kv for kv in ranked if kv[0] in FAST_LABELS]
    best, second = ranked[0], ranked[1]
    conf = float(1 / (1 + np.exp(-(best[1] - second[1]) * 40)))  # margin -> (0.5, 1)
    return best[0], conf, scores


def learn(kind: str, label: str, text: str) -> None:
    """Owner-confirmed example (e.g. after a correction). Takes effect on next start."""
    with open(CFG.home / "exemplars.jsonl", "a") as f:
        f.write(json.dumps({"kind": kind, "label": label, "text": text}) + "\n")
    _index.cache_clear()
