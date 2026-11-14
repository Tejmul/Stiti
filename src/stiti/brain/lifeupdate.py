"""Real-time life updates and corrections (D38) — written in the turn, not after a night the Mac may sleep through.

"Actually, I left MVRX Labs… my internship is done, I left in September" got "Noted. I will mark that down." and
nothing was written (2026-11-14). Now, deterministic patterns first (no LLM, ~1 ms + one embedding per fact):

  I left / quit / resigned from X · my internship at X is over · maine X chhod diya   → end his ties to X, add "left X"
  I joined X / I work at X / I'm interning at X (as a role)                          → works_at X (ends the old one)
  I moved to X / I live in X now · my sister moved to Pune                           → lives_in (functional)
  Riya is my sister · my sister's name is Riya · my friend Arjun                     → person + relation fact
  I don't play football anymore · I quit smoking · I stopped going to the gym         → end matching facts + "stopped"
  remember that … / yaad rakhna ki … / note this down: …                            → a plain fact in his words
  actually it's X, not Y · not Y, it's X                                             → the wrong fact is retracted

What the patterns can't parse but clearly is an update/correction ("actually…", "change it", "that's wrong", job /
moved / birthday words) goes to the night-job extractor for just this turn, in a background thread AFTER the reply
(never on the hot path). Her reply may only say "noted / updated" when `Update.saved` is non-empty (psych.MEMORY_CLAIM_RX).
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from datetime import datetime

from ..config import CFG
from ..db import q
from . import factstore

REL = (r"(?:mom|mother|mum|mummy|maa|ammi|dad|father|papa|daddy|abba|sister|sis|didi|brother|bro|bhai|wife|husband|"
       r"girlfriend|boyfriend|gf|bf|fiancee?|partner|son|daughter|best friend|friend|roommate|room mate|uncle|aunt|"
       r"cousin|grandma|grandmother|grandpa|grandfather|nani|nana|dadi|dada|manager|boss|mentor|teacher|cofounder|"
       r"co-founder|colleague)")
REL_CANON = {"mum": "mother", "mom": "mother", "mummy": "mother", "maa": "mother", "ammi": "mother", "dad": "father",
             "papa": "father", "daddy": "father", "abba": "father", "sis": "sister", "didi": "sister", "bro": "brother",
             "bhai": "brother", "gf": "girlfriend", "bf": "boyfriend", "room mate": "roommate", "fiance": "fiancé",
             "fiancee": "fiancée", "co-founder": "cofounder", "grandma": "grandmother", "grandpa": "grandfather"}
# a proper noun as STT writes it: capitalised words / acronyms ("MVRX Labs", "Newton School of Technology")
_CAP = r"[A-Z0-9][\w&.'-]*"
ORG = rf"(?P<x>{_CAP}(?:\s+(?:of|and|&|for|the|de)\s+{_CAP}|\s+{_CAP}){{0,4}})"
NAME = r"(?P<name>[A-Z][a-z]{1,20}(?:\s[A-Z][a-z]{1,20})?)"
PLACE = rf"(?P<x>{_CAP}(?:\s+{_CAP}){{0,2}})"
NOT_NAMES = {"I", "My", "The", "This", "That", "It", "He", "She", "They", "We", "You", "Stiti", "Actually", "Okay",
             "Ok", "So", "And", "But", "Yes", "No", "Hey", "Also", "Now", "Today", "Yesterday", "Tomorrow"}

_I = r"(?i:\bi(?:'ve| have| had)?\s+(?:just\s+|already\s+|finally\s+|recently\s+|officially\s+)?)"
LEFT = [re.compile(_I + r"(?i:left|quit|resigned from|exited|stopped working (?:at|for|with)|moved out of)\s+(?:the\s+)?" + ORG),
        re.compile(r"(?i:\bi(?:'m| am) (?:no longer|not) (?:at|with|working (?:at|for|with)|interning (?:at|with))\s+)" + ORG),
        re.compile(r"(?i:\bi (?:don'?t|do not) work (?:at|for|with)\s+)" + ORG),
        re.compile(r"(?i:\bmy (?:internship|job|work|role|time|contract) (?:at|with|in)\s+)" + ORG +
                   r"(?i:\s+(?:is|has|got)?\s*(?:done|over|ended|finished|completed))"),
        re.compile(r"(?i:\bmaine\s+)" + ORG + r"(?i:\s+(?:chhod|chod)\s*(?:diya|di|dia))")]
JOBWORD = re.compile(r"\b(intern|engineer|developer|designer|student|manager|analyst|founder|lead|scientist|"
                     r"researcher|consultant|teacher|professor|associate|executive|architect|sde|swe)\b", re.I)
JOIN = [re.compile(_I + r"(?i:joined|started (?:working |an internship |a job |my internship |my job )?(?:at|with|in)|"
                   r"got (?:a job|an internship|placed|hired) (?:at|in|with|by)|work (?:at|for)|"
                   r"(?:am|'m) (?:now )?(?:working|interning) (?:at|for|with))\s+(?:the\s+)?" + ORG +
                   r"(?i:\s+as\s+(?:an?\s+)?(?P<role>[a-z][\w -]{2,40}?))?(?=[.,!;]|\s+(?:and|from|since|in|last|this)\b|$)"),
        re.compile(r"(?i:\bi(?:'m| am) (?:now )?(?:an? )?(?P<role>[a-z][\w -]{2,30}?) (?:at|in|with)\s+)" + ORG +
                   r"(?=[.,!;]|\s+(?:and|now|since)\b|$)")]
MOVED = [re.compile(_I + r"(?i:moved|shifted|relocated)(?i: back)?\s+(?i:to|into|in)\s+" + PLACE),
         re.compile(r"(?i:\bi (?:now )?live in\s+)" + PLACE),
         re.compile(r"(?i:\bi(?:'m| am) (?:now )?(?:living|staying|based) in\s+)" + PLACE)]
REL_MOVED = re.compile(r"(?i:\bmy\s+(?P<rel>" + REL[3:-1] + r"))(?:\s+(?P<nm>[A-Z][a-z]{1,20}))?"
                       r"(?i:\s+(?:just\s+|has\s+|have\s+|recently\s+)?(?:moved|shifted|relocated)(?: back)?\s+(?:to|into)\s+)"
                       + PLACE)
REL_IS = [re.compile(NAME + r"(?i:\s+is\s+my\s+(?P<rel>" + REL[3:-1] + r"))\b"),
          re.compile(r"(?i:\bmy\s+(?P<rel>" + REL[3:-1] + r")(?:'s name is|\s+is called|\s+named|,)?\s+)" + NAME +
                     r"(?=[.,!;]|\s+(?:is|lives|works|studies|and|who|was|moved|just|got)\b|$)"),
          re.compile(NAME + r"(?i:\s+(?:meri|mera|meri)\s+(?P<rel>" + REL[3:-1] + r"|behen|bhabhi)\s+(?:hai|h)\b)")]
STOPPED = [re.compile(r"(?i:\bi\s+(?:don'?t|do not|no longer|never)\s+(?P<verb>play|do|go to|go for|eat|drink|smoke|watch|"
                      r"use|study|practice|practise|follow|work on|ride)\s+(?P<x>[a-z][\w' -]{1,30}?)\s+"
                      r"(?:anymore|any more|these days)\b)"),
           re.compile(r"(?i:\bi(?:'m| am) (?:not|no longer) (?P<verb>playing|doing|working on|eating|drinking|smoking|"
                      r"studying|learning)\s+(?P<x>[a-z][\w' -]{1,30}?)\s*(?:anymore|any more|now)?(?=[.,!;]|$))"),
           re.compile(_I + r"(?i:stopped|quit|gave up)\s+(?P<verb>playing|doing|going to|eating|drinking|smoking|"
                      r"watching|using)?\s*(?!(?:last|this|in|since|and|because|yesterday|today|ago)\b)"
                      r"(?P<x>[a-z][\w' -]{1,30}?)(?=[.,!;]|\s+(?:last|this|in|since|a|an|and|because)\b|$)"),
           re.compile(r"(?i:\bmaine\s+(?P<x>[a-z][\w' -]{1,30}?)\s+(?:khelna|karna|peena|jaana)?\s*(?:chhod|chod)\s*(?:diya|di|dia))")]
# STT often writes names in lowercase ("i left orbit labs"): accepted only when it names an org/project she knows
LEFT_LOWER = re.compile(r"(?i:\bi(?:'ve| have)?\s+(?:just\s+|already\s+|finally\s+)?(?:left|quit|resigned from)\s+"
                        r"(?:the\s+)?(?P<x>[a-z][\w&.' -]{1,40}?))(?=[.,!;]|\s+(?:in|last|this|and|change|because|so)\b|$)")
REMEMBER = re.compile(r"(?i:\b(?:please\s+)?(?:remember|yaad rakh(?:na|o|iyo)?|note (?:this|it|that) down|keep in mind|"
                      r"don'?t forget|mat bhoolna)(?:\s+that|\s+ki|\s+ke|\s*:|\s*,|\s+(?!to\b|when\b|what\b|how\b|where\b|"
                      r"who\b|why\b|me\b|it\b|this\b|that\b|the time\b|us\b|and\b|or\b|in\b|on\b)))\s*(?P<x>.{4,240})")
# Hinglish order: "kal Riya aa rahi hai, yaad rakhna" / "my locker code is 4412, remember that"
# ("…I'll tell you the list, note it down" is a to-do request, not a fact: "note it down" only counts up front)
REMEMBER_TAIL = re.compile(r"(?i)^(?P<x>(?!.*\b(?:i'll tell you|list|todo|to-do)\b).{6,240}?)[,\s]+(?:yaad rakh(?:na|o|iyo)|"
                           r"remember (?:that|this|it)|don'?t forget (?:it|that|this)|mat bhoolna)\W*$")
CORRECT = [re.compile(r"(?i:\b(?:actually|no|nahi|nope|galat|sorry)\b[, ]+(?:it'?s|it is|its|that'?s|the name is|i meant|"
                      r"it should be)\s+)(?P<new>[^,.!?]{2,60}?)(?i:,?\s+not\s+)(?P<old>[^,.!?]{2,60})"),
           re.compile(r"(?i:\bnot\s+)(?P<old>[^,.!?]{2,60}?)(?i:,?\s+(?:it'?s|it is|its|but)\s+)(?P<new>[^,.!?]{2,60})")]
CUE = re.compile(r"\b(actually|change it|update it|correct (it|that)|that'?s (wrong|not right|incorrect)|not anymore|"
                 r"no longer|galat|badal do|ab nahi|i left|i joined|i moved|i quit)\b", re.I)
LIFE = re.compile(r"\b(birthday|shaadi|wedding|engaged|married|job|offer|internship|placed|moved|shift|breakup|broke up|"
                  r"died|passed away|born|promotion|salary|new (job|role|company|house|flat|city))\b", re.I)
HYPO = re.compile(r"\b(if|should|might|may|would|could|thinking of|planning to|want to|wanna|going to|gonna|will|"
                  r"agar|shayad|before|when)\s+(?:i\s+)?$", re.I)
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                       "september", "october", "november", "december"], 1)}
MONTH_RX = re.compile(r"\b(?:in|since|from|during|around|back in|on|last)\s+(?:the\s+)?(?:(?:\d{1,2})(?:st|nd|rd|th)?\s+)?"
                      r"(?P<m>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
                      r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b(?:\s+(?P<y>20\d\d))?", re.I)
_TRAIL = re.compile(r"\s+(?:change it|update it|note it|change it down|now|today|yesterday|last \w+|this \w+|already|"
                    r"anymore|and|but|so|because|since|in)\b.*$", re.I)


@dataclass
class Update:
    saved: list[str] = field(default_factory=list)      # what she can honestly say she saved, in 2nd person
    fact_ids: list[int] = field(default_factory=list)
    ended: list[int] = field(default_factory=list)
    needs_llm: bool = False                            # an update/correction the patterns couldn't parse

    @property
    def ack(self) -> str:
        if not self.saved:
            return ""
        if len(self.saved) == 1 and self.saved[0] == "__remember__":
            return "Noted — I'll remember that."
        notes = [s for s in self.saved if s != "__remember__"]
        return "Got it — updated: " + "; ".join(notes) + "."


def _owner() -> str:
    from .. import profile
    return profile.name()


def _me() -> int:
    from .sleep import resolve_entity
    return resolve_entity(_owner(), "self")


def _month(text: str, now: datetime) -> datetime | None:
    m = MONTH_RX.search(text)
    if not m:
        return None
    mon = next(v for k, v in MONTHS.items() if k.startswith(m["m"].lower()[:3]))
    year = int(m["y"]) if m["y"] else (now.year if mon <= now.month else now.year - 1)
    return datetime(year, mon, 1, tzinfo=CFG.tz)


def _clean_x(x: str) -> str:
    x = _TRAIL.sub("", x.strip()).strip(" .,!?'\"")
    return re.sub(r"\s+", " ", x)


def _hypothetical(text: str, start: int) -> bool:
    return bool(HYPO.search(text[max(0, start - 30):start]))


def _rel(r: str) -> str:
    r = r.lower().strip()
    return REL_CANON.get(r, r)


def _first_to_third(x: str, who: str) -> str:
    """'my mom's birthday is on 12 March' → "Tejmul's mom's birthday is on 12 March"."""
    reps = [(r"\bI'm\b|\bI am\b", f"{who} is"), (r"\bI've\b", f"{who} has"), (r"\bI\b", who), (r"\bmy\b", f"{who}'s"),
            (r"\bmine\b", f"{who}'s"), (r"\bme\b", who), (r"\bmyself\b", who)]
    for rx, rep in reps:
        x = re.sub(rx, rep, x, flags=re.I)
    return x[:1].upper() + x[1:]


def _person(rel: str, name: str | None) -> int:
    """'my sister' (+ maybe 'Riya'): one person entity, renamed from the placeholder once he says her name."""
    from .sleep import resolve_entity
    who, rel = _owner(), _rel(rel)
    placeholder = f"{who}'s {rel}"
    if name:
        from ..db import one
        ph = one("""SELECT id FROM entities WHERE merged_into IS NULL AND kind='person' AND lower(name)=lower(%s)""",
                 (placeholder,))
        if ph and not one("SELECT 1 x FROM entities WHERE merged_into IS NULL AND lower(name)=lower(%s)", (name,)):
            q("UPDATE entities SET name=%s, aliases=ARRAY(SELECT DISTINCT unnest(aliases || %s::text[])) WHERE id=%s",
              (name, [placeholder, f"my {rel}"], ph["id"]))
            return ph["id"]
        return resolve_entity(name, "person", [f"my {rel}"])
    return resolve_entity(placeholder, "person", [f"my {rel}"])


_SKIP_X = {"it", "that", "this", "the", "a", "an", "him", "her", "them", "you", "there", "here", "home", "work",
           "office", "early", "late", "on", "to", "talking", "college", "school", "class", "now"}
_IMPERATIVE_HEAD = re.compile(r"^\W*(?:(?:okay|ok|so|and|also|hey|stiti|please|just|haan|acha|accha)\W+)*$", re.I)


def _name(n: str | None) -> str | None:
    """'Okay Pugal' → 'Pugal' (a capitalised filler word glued to the name by the regex)."""
    if not n:
        return None
    words = [w for w in n.split() if w not in NOT_NAMES]
    return " ".join(words) or None


def capture(text: str, user_ep: int | None, *, now: datetime | None = None, privacy: int = 1) -> Update:
    """Deterministic capture for one turn of his. Writes facts at once; returns what was saved."""
    from .sleep import resolve_entity
    now = now or datetime.now(CFG.tz)
    up = Update()
    t = text.strip()
    sents = [s for s in re.split(r"(?<=[.!?;])\s+", t) if s.strip() and not s.rstrip().endswith("?")]
    if not sents:                                   # questions only ("Do you remember my sister?")
        return up
    who = _owner()
    eps = [user_ep] if user_ep else []
    when = _month(t, now)
    me_box: list[int] = []

    def mine() -> int:
        if not me_box:
            me_box.append(_me())
        return me_box[0]

    def add(subj, pred, ftxt, note, **kw):
        _, fid = factstore.add(subj, pred, ftxt, privacy=privacy, ep_ids=eps, origin="conversation",
                               confidence=kw.pop("confidence", 0.9), **kw)
        up.fact_ids.append(fid)
        if note and note not in up.saved:
            up.saved.append(note)
        return fid

    left_orgs: list[str] = []
    for s in sents:
        org_left = False
        # ---- corrections: "actually it's X, not Y" ----
        for i, rx in enumerate(CORRECT):
            m = rx.search(s)
            if not m or (i == 1 and not re.match(r"^\W*(?:(?:no|nahi|nope|actually|sorry)\W+)*$", s[:m.start()], re.I)):
                continue
            new, old = _clean_x(m["new"]), _clean_x(m["old"])
            if len(old) >= 3 and new.lower() != old.lower() and re.search(r"[A-Z0-9]", old + new):
                n = _correct(old, new, eps, privacy)
                if n:
                    up.saved.append(f"it's {new}, not {old}")
                    up.fact_ids += [x for x in n if x > 0]
            break
        # ---- left an org ----
        for rx in LEFT:
            m = rx.search(s)
            if not m or _hypothetical(s, m.start()):
                continue
            x = _clean_x(m["x"])
            if not x or x in NOT_NAMES:
                continue
            org_left = True
            if any(o.startswith(x.lower()) or x.lower().startswith(o) for o in left_orgs):
                break                                   # "…left MVRX Labs… I left MVRX" — the same place
            left_orgs.append(x.lower())
            org = resolve_entity(x, "org")
            fid = add(mine(), "left", f"{who} left {x}" + (f" in {when:%B %Y}" if when else "") + ".",
                      f"you left {x}" + (f" ({when:%B})" if when else ""), obj_id=org, start=when)
            up.ended += factstore.close_ties(mine(), x, when, fid)
            for r in q("""SELECT id FROM facts WHERE subj_id=%s AND obj_id=%s AND upper_inf(recorded) AND valid @> now()
                          AND predicate IN ('works_at','interns_at','studies_at','member_of','joined')""", (mine(), org)):
                if factstore.end_fact(r["id"], when, fid):
                    up.ended.append(r["id"])
            break
        if not org_left and (m := LEFT_LOWER.search(s)) and not _hypothetical(s, m.start()):
            from ..db import one
            x = _clean_x(m["x"])
            known = one("""SELECT name FROM entities WHERE merged_into IS NULL AND kind IN ('org','project') AND
                             (lower(name)=lower(%(x)s) OR word_similarity(lower(name), lower(%(x)s)) >= 0.8)
                           ORDER BY similarity(lower(name), lower(%(x)s)) DESC LIMIT 1""", {"x": x}) if len(x) >= 3 else None
            if known and not any(o.startswith(known["name"].lower()) or known["name"].lower().startswith(o)
                                 for o in left_orgs):
                org_left = True
                x = known["name"]
                left_orgs.append(x.lower())
                org = resolve_entity(x, "org")
                fid = add(mine(), "left", f"{who} left {x}" + (f" in {when:%B %Y}" if when else "") + ".",
                          f"you left {x}" + (f" ({when:%B})" if when else ""), obj_id=org, start=when)
                up.ended += factstore.close_ties(mine(), x, when, fid)
            elif known:
                org_left = True
        # ---- joined an org ----
        for i, rx in enumerate(JOIN):
            m = rx.search(s)
            if not m or _hypothetical(s, m.start()):
                continue
            x = _clean_x(m["x"])
            role = _clean_x(m["role"]) if m.groupdict().get("role") else ""
            if not x or x in NOT_NAMES or x.lower() in left_orgs or (i == 1 and not JOBWORD.search(role)):
                continue
            student = bool(re.search(r"\bstud(ent|ying)\b", role + " " + s, re.I)) and not re.search(r"\bintern", s, re.I)
            pred = "studies_at" if student else "interns_at" if re.search(r"\bintern", s, re.I) else "works_at"
            a = "an" if role[:1].lower() in "aeiou" else "a"
            desc = (f"{who} is {a} {role} at {x}." if role else
                    f"{who} studies at {x}." if pred == "studies_at" else
                    f"{who} is an intern at {x}." if pred == "interns_at" else f"{who} works at {x}.")
            org = resolve_entity(x, "org")
            if pred != "studies_at":                    # one job at a time: interning ends working and vice versa
                other = "works_at" if pred == "interns_at" else "interns_at"
                for r in q("""SELECT id FROM facts WHERE subj_id=%s AND predicate=%s AND upper_inf(recorded)
                              AND valid @> now()""", (mine(), other)):
                    if factstore.end_fact(r["id"], when):
                        up.ended.append(r["id"])
            add(mine(), pred, desc, f"you're at {x}" + (f" as {a} {role}" if role else ""), obj_id=org, start=when,
                functional=True)
            break
        # ---- moved / lives in ----
        m = REL_MOVED.search(s)
        if m and not _hypothetical(s, m.start()):
            x, nm = _clean_x(m["x"]), _name(m["nm"])
            if x and x not in NOT_NAMES:
                rel = _rel(m["rel"])
                p = _person(rel, nm)
                place = resolve_entity(x, "place")
                add(p, "lives_in", f"{nm or who + chr(39) + 's ' + rel} lives in {x}.", f"your {rel} lives in {x}",
                    obj_id=place, functional=True, start=when)
                if nm:
                    add(p, f"{rel.replace(' ', '_')}_of", f"{nm} is {who}'s {rel}.", None, obj_id=mine())
                else:
                    add(mine(), f"has_{rel.replace(' ', '_')}", f"{who} has a {rel}.", None, obj_id=p)
        else:
            for rx in MOVED:
                m = rx.search(s)
                if m and not _hypothetical(s, m.start()):
                    x = _clean_x(m["x"])
                    if x and x not in NOT_NAMES:
                        place = resolve_entity(x, "place")
                        add(mine(), "lives_in", f"{who} lives in {x}.", f"you live in {x}", obj_id=place,
                            functional=True, start=when)
                    break
        # ---- people: "Riya is my sister" ----
        for rx in REL_IS:
            m = rx.search(s)
            nm = _name(m["name"]) if m else None
            if m and nm and nm.lower() != who.lower():
                rel = _rel(m["rel"])
                rel = {"behen": "sister", "bhabhi": "sister-in-law"}.get(rel, rel)
                p = _person(rel, nm)
                add(p, f"{re.sub(r'[^a-z]+', '_', rel)}_of", f"{nm} is {who}'s {rel}.", f"{nm} is your {rel}",
                    obj_id=mine())
                break
        # ---- stopped an activity ----
        for rx in ([] if org_left else STOPPED):
            m = rx.search(s)
            if not m or _hypothetical(s, m.start()):
                continue
            x = _clean_x(m["x"])
            verb = (m.groupdict().get("verb") or "").lower()
            if not x or len(x) < 3 or x.split()[0].lower() in _SKIP_X or re.match(r"[A-Z]", m["x"]):
                continue
            if rx in STOPPED[:2] and verb:              # "I don't play hockey anymore"
                ftxt, note = f"{who} doesn't {_base(verb)} {x} anymore.", f"you don't {_base(verb)} {x} anymore"
            else:                                       # "I quit smoking" / "maine cricket chhod diya"
                ftxt, note = f"{who} stopped {verb + ' ' if verb else ''}{x}.", f"you stopped {verb + ' ' if verb else ''}{x}"
            fid = add(mine(), "stopped", ftxt, note, obj_literal=x.lower(), start=when)
            for r in factstore.mentions_current(mine(), x, exclude=("likes", "dislikes", "stopped", "left")):
                if r["id"] != fid and factstore.end_fact(r["id"], when, fid):
                    up.ended.append(r["id"])
            break
        # ---- "remember that …" ----
        m = REMEMBER.search(s)
        if not (m and _IMPERATIVE_HEAD.match(s[:m.start()])):
            m = REMEMBER_TAIL.search(s)
        if m and not re.match(r"(?i)\s*to\b", m["x"]) and not re.search(r"\bremind me\b", s, re.I) and not up.fact_ids:
            x = m["x"].strip().rstrip(".!,")
            if len(re.findall(r"\w+", x)) >= 3:
                ftxt = _first_to_third(x, who) if re.search(r"\b(i|my|me|i'm)\b", x, re.I) else f"{who}: {x}"
                add(mine(), "noted", ftxt.rstrip(".") + ".", "__remember__", obj_literal=x[:200], confidence=0.9)
    t = " ".join(sents)
    if not up.saved and (CUE.search(t) or LIFE.search(t) and re.search(r"\b(i|my|i'm|i've|mera|meri|mere|maine|mujhe)\b",
                                                                       t, re.I)):
        up.needs_llm = True
    if up.saved:
        if user_ep:
            q("UPDATE episodes SET importance = GREATEST(importance, 7) WHERE id=%s", (user_ep,))
        factstore.refresh(background=True)          # standing profile + USER.md, off the hot path
    return up


def _base(verb: str) -> str:
    return {"playing": "play", "doing": "do", "going to": "go to", "eating": "eat", "drinking": "drink",
            "smoking": "smoke", "watching": "watch", "using": "use", "studying": "study", "learning": "learn",
            "working on": "work on"}.get(verb, verb)


def _correct(old: str, new: str, eps: list[int], privacy: int) -> list[int]:
    """'not Newton's Club, it's Newton School of Technology': every current fact naming `old` is retracted (never
    true — a mishearing) and re-stated with `new`; an entity named `old` is renamed (old name kept as an alias).
    Returns new fact ids (and -entity_id for each renamed entity)."""
    rx = re.compile(rf"(?<!\w){re.escape(old)}(?!\w)", re.I)
    out = []
    for r in q("""SELECT id, subj_id, predicate, obj_id, obj_literal, fact_text, functional, confidence FROM facts
                  WHERE upper_inf(recorded) AND valid @> now() AND fact_text ILIKE %s""", (f"%{old}%",)):
        if not rx.search(r["fact_text"]):
            continue
        factstore.retract_fact(r["id"])
        fixed = re.sub(r"\b(\w+(?:\s+\w+){0,3})\s+\1\b", r"\1", rx.sub(new, r["fact_text"]))   # "…of Technology of Technology"
        _, fid = factstore.add(r["subj_id"], r["predicate"], fixed, obj_id=r["obj_id"],
                               obj_literal=rx.sub(new, r["obj_literal"]) if r["obj_literal"] else None,
                               functional=r["functional"], confidence=max(0.9, r["confidence"]), privacy=privacy,
                               ep_ids=eps, origin="conversation")
        q("UPDATE facts SET invalidated_by=%s WHERE id=%s", (fid, r["id"]))
        out.append(fid)
    for e in q("""SELECT id, name FROM entities WHERE merged_into IS NULL AND kind <> 'self' AND name ILIKE %s""",
               (f"%{old}%",)):
        if rx.search(e["name"]):
            q("UPDATE entities SET name=%s, aliases=ARRAY(SELECT DISTINCT unnest(aliases || %s::text[])) WHERE id=%s",
              (re.sub(r"\b(\w+(?:\s+\w+){0,3})\s+\1\b", r"\1", rx.sub(new, e["name"])), [e["name"]], e["id"]))
            out.append(-e["id"])
    return out


def hint(text: str) -> bool:
    """Cheap: could capture() write something for this text? (a speculative voice turn must not run it, D29)"""
    sents = [x for x in re.split(r"(?<=[.!?;])\s+", text.strip()) if x.strip() and not x.rstrip().endswith("?")]
    return any(rx.search(t) for t in sents for rx in LEFT + JOIN + MOVED + REL_IS + STOPPED + CORRECT + [REL_MOVED, LEFT_LOWER, REMEMBER,
                                                                                       REMEMBER_TAIL])


# ---------- background: the extractor for one turn, after the reply ----------
_bg: threading.Thread | None = None


def after_reply(user_ep: int, privacy: int) -> bool:
    """Start a background extraction of this one turn (+ her reply before it, as context). P2 never leaves the Mac."""
    global _bg
    if privacy >= 2:
        return False

    def job():
        try:
            from .sleep import extract_episodes
            st = extract_episodes([user_ep])
            if st.get("facts") or st.get("ended") or st.get("corrected"):
                factstore.refresh(background=False)
            print(f"[learn] turn {user_ep}: {st}", flush=True)
        except Exception as e:                       # no cloud right now: the night job reads it later
            print(f"[learn] turn {user_ep} left for the night job: {type(e).__name__}: {e}"[:200], flush=True)
    _bg = threading.Thread(target=job, daemon=True)
    _bg.start()
    return True


def join(timeout: float = 30.0) -> None:
    """Tests: wait for background work."""
    if _bg is not None:
        _bg.join(timeout)
    factstore.join(timeout)
