"""Sleep / consolidation (report §Consolidation): idempotent, watermarked steps.

1 embed backlog · 3 extract entities/facts/directives (cloud, P0/P1 owner episodes only)
4 resolve entities (no LLM) · 5 apply bitemporal facts · 6 supersede directives
8 strength decay (nothing deleted) · 9 precompile standing profile · 10 render USER.md /
LESSONS.md / GRAPH_REPORT.md. Cloud steps end `partial` when no provider is available and
resume next run from the watermark. P2 never enters an LLM step.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime

from .. import embed, router
from ..config import CFG
from ..db import one, q
from . import factstore, lessons

KINDS = ["self", "person", "project", "place", "org", "event", "feeling", "topic", "thing"]
TOPICS = ["call_me", "reply_length", "questions", "humour", "language", "topics_to_avoid", "routine", "preference",
          "boundary", "goal", "other"]
EXTRACT_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["entities", "facts", "ends", "directives"],
    "properties": {
        "entities": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["name", "kind", "aliases"],
            "properties": {"name": {"type": "string"}, "kind": {"type": "string", "enum": KINDS},
                           "aliases": {"type": "array", "items": {"type": "string"}}}}},
        "facts": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["subject", "predicate", "object", "object_kind", "fact_text", "functional", "valid_from",
                         "evidence_ids", "confidence"],
            "properties": {"subject": {"type": "string"}, "predicate": {"type": "string"},
                           "object": {"type": "string"},
                           "object_kind": {"type": "string", "enum": KINDS[1:] + ["literal"]},
                           "fact_text": {"type": "string"}, "functional": {"type": "boolean"},
                           "valid_from": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                           "evidence_ids": {"type": "array", "items": {"type": "integer"}},
                           "confidence": {"type": "number"}}}},
        "ends": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["fact_id", "valid_to", "wrong", "evidence_ids"],
            "properties": {"fact_id": {"type": "integer"},
                           "valid_to": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                           "wrong": {"type": "boolean"},
                           "evidence_ids": {"type": "array", "items": {"type": "integer"}}}}},
        "directives": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["directive", "category", "topic", "standing", "evidence_ids"],
            "properties": {"directive": {"type": "string"},
                           "category": {"type": "string",
                                        "enum": ["talk_style", "routine", "preference", "boundary", "goal"]},
                           "topic": {"type": "string", "enum": TOPICS}, "standing": {"type": "boolean"},
                           "evidence_ids": {"type": "array", "items": {"type": "integer"}}}}},
    },
}

EXTRACT_PROMPT = """You keep the long-term memory of {owner}'s personal assistant, Stiti. Below is a stretch of their
conversation, from speech-to-text (words can be misheard; Hinglish/Telugu is normal). Lines "[id] {owner}: …" are what
{owner} said. Lines "Stiti: …" are her replies, given ONLY as context — never take a fact from what Stiti said.

Return JSON:
- entities: people, places, orgs, projects, events, topics {owner} names. A person known only by relation ("my
  sister") is named "{owner}'s sister" with alias "my sister".
- facts: lasting things {owner} states or clearly confirms about themself or the people, projects and places in
  their life: work/study, where they live, relationships ("Riya is {owner}'s sister"), projects, likes/dislikes,
  habits, goals, plans with a date, how they feel about something lasting. subject = who it is about ("{owner}" for
  themself). object_kind = the object's entity kind, or "literal" for a plain value. fact_text = one plain
  third-person sentence ("{owner} left Ledgerly in September 2026."). functional = true when the subject has only one
  value at a time (works_at, lives_in, studies_at, relationship_status). evidence_ids = the [id]s it comes from.
  confidence = how sure you are {owner} really said and meant it: 0.9 clear, 0.7 implied. Misheard or garbled → leave out.
  For every person, also say who they are to {owner} ("Meera is {owner}'s sister."). A change is a fact too:
  "{owner} left Ledgerly in September 2026.", "{owner} stopped playing hockey."
- ends: {owner} says a KNOWN FACT is no longer true ("I left X", "I don't play football anymore") → its fact_id,
  valid_to (YYYY-MM-DD or null = today), wrong=false. A known fact that was never true (he corrects a mistake) → wrong=true.
- directives: lasting rules for how Stiti should behave ("keep replies short in the morning", "never call me Tej");
  standing=false for one-off commands ("switch to Hindi", "open the whiteboard", "shut up", "bye").
SKIP: questions, commands to Stiti (todos, alarms, reminders, open/teach/switch/stop), greetings, small talk, jokes and
teasing, anything Stiti said, lines that make no sense. Empty lists are fine — never invent. Today is {today}.

Example — "[7] {owner}: I finished my internship at Ledgerly last month, now I'm at Orbit as a backend intern" with
KNOWN FACT "F3: {owner} interns at Ledgerly" → ends [{{"fact_id":3,"valid_to":null,"wrong":false,"evidence_ids":[7]}}],
facts [{{"subject":"{owner}","predicate":"interns_at","object":"Orbit","object_kind":"org","fact_text":"{owner} is a
backend intern at Orbit.","functional":true,"valid_from":null,"evidence_ids":[7],"confidence":0.9}}].

KNOWN FACTS:
{known}

CONVERSATION:
{lines}
"""


def _run_start(job: str) -> tuple[int, int]:
    last = one("""SELECT watermark FROM consolidation_runs WHERE job=%s AND status IN ('ok','partial')
                  AND watermark IS NOT NULL ORDER BY id DESC LIMIT 1""", (job,))
    rid = one("INSERT INTO consolidation_runs(job) VALUES (%s) RETURNING id", (job,))["id"]
    return rid, (last["watermark"] if last else 0)


def _run_end(rid: int, status: str, watermark: int | None, stats: dict, provider=None, tokens=0, error=None):
    q("""UPDATE consolidation_runs SET finished_at=now(), status=%s, watermark=%s, stats=%s,
                provider=%s, tokens_used=%s, error=%s WHERE id=%s""",
      (status, watermark, json.dumps(stats), provider, tokens, error, rid))


# ---------- step 1 ----------
def embed_backlog() -> int:
    rows = q("SELECT id, text FROM episodes WHERE embedding IS NULL ORDER BY id LIMIT 500")
    for i in range(0, len(rows), 32):
        chunk = rows[i:i + 32]
        for r, v in zip(chunk, embed.embed_docs([r["text"] for r in chunk])):
            q("UPDATE episodes SET embedding=%s, embed_model=%s WHERE id=%s", (v, embed.EMBED_MODEL, r["id"]))
    return len(rows)


# ---------- step 4 ----------
def resolve_entity(name: str, kind: str, aliases: list[str] | None = None) -> int:
    name = name.strip()
    from .. import profile
    if kind == "self" or name.lower() in profile.self_aliases() + ["the owner"]:
        row = one("SELECT id FROM entities WHERE kind='self' AND merged_into IS NULL LIMIT 1")
        if row:
            if profile.get("name"):
                q("UPDATE entities SET name=%s WHERE id=%s AND name<>%s", (profile.name(), row["id"], profile.name()))
            return row["id"]
        return one("INSERT INTO entities(kind, name, aliases) VALUES ('self',%s,'{me,main}') RETURNING id",
                   (profile.name(),))["id"]
    row = one("""SELECT id FROM entities WHERE merged_into IS NULL AND
                   (lower(name)=lower(%(n)s) OR lower(%(n)s) = ANY(SELECT lower(a) FROM unnest(aliases) a))
                 LIMIT 1""", {"n": name})
    exact_only = bool(re.search(r"'s\s", name))     # "Ravi's sister" ≠ "Ravi's friend" (trigram/embedding say they're close)
    if not row and not exact_only:
        row = one("""SELECT id FROM entities WHERE merged_into IS NULL AND kind=%s AND similarity(lower(name), lower(%s)) >= 0.6
                     ORDER BY similarity(lower(name), lower(%s)) DESC LIMIT 1""", (kind, name, name))
    vec = embed.embed_docs([f"{kind}: {name}"])[0]
    if not row and not exact_only:
        row = one("""SELECT id FROM entities WHERE merged_into IS NULL AND kind=%s AND embedding IS NOT NULL
                       AND 1 - (embedding <=> %s) >= 0.85 ORDER BY embedding <=> %s LIMIT 1""", (kind, vec, vec))
    if row:
        if aliases:
            q("UPDATE entities SET aliases = ARRAY(SELECT DISTINCT unnest(aliases || %s::text[])) WHERE id=%s",
              (aliases, row["id"]))
        return row["id"]
    kind = kind if kind in ("person", "project", "place", "org", "event", "feeling", "topic", "thing") else "thing"
    return one("INSERT INTO entities(kind, name, aliases, embedding) VALUES (%s,%s,%s,%s) RETURNING id",
               (kind, name, aliases or [], vec))["id"]


# ---------- step 5 ----------
def apply_fact(f: dict, ep_ids: list[int], kinds: dict[str, str], privacy: int = 1) -> tuple[str, int]:
    """One extracted fact → the graph (subject/object entities resolved, temporal validity, merge on duplicates)."""
    from .. import profile
    owner = profile.name()
    m = re.fullmatch(rf"(?i){re.escape(owner)}'s\s+(?:younger |older |elder |little |big |best )?([a-z][a-z -]{{1,25}})",
                     (f.get("object") or "").strip())
    t = re.fullmatch(rf"(?i)(?P<name>[\w .'-]{{2,40}}?) is {re.escape(owner)}'s\s+(?:younger |older |elder |little |big |"
                     rf"best |close )?(?P<rel>[a-z][a-z -]{{1,25}}?)\.?", (f.get("fact_text") or "").strip())
    if t and t["name"].lower() != owner.lower():   # the sentence is the truth: "Meera is Ravi's sister" → Meera —sister_of→ Ravi
        f = {**f, "subject": t["name"], "predicate": f"{re.sub(r'[^a-z]+', '_', t['rel'].lower())}_of", "object": owner,
             "object_kind": "self"}
        kinds = {**kinds, owner.lower(): "self", t["name"].lower(): kinds.get(t["name"].lower(), "person")}
    elif m and f.get("predicate", "").lower() in ("is", "is_a", "relation", "relationship", "relation_to_owner", "noted"):
        rel = m.group(1).strip().lower()            # "Arjun —is→ Ravi's friend" → "Arjun —friend_of→ Ravi"
        f = {**f, "predicate": f"{re.sub(r'[^a-z]+', '_', rel)}_of", "object": owner, "object_kind": "self"}
        kinds = {**kinds, owner.lower(): "self"}
    subj = resolve_entity(f["subject"], kinds.get(f["subject"].lower(), "person"))
    obj_id, obj_lit = None, None
    ok = f.get("object_kind") or ("thing" if f.get("object_is_entity", True) else "literal")
    if ok != "literal":
        obj_id = resolve_entity(f["object"], ok if ok == "self" else kinds.get(f["object"].lower(), ok))
    else:
        obj_lit = f["object"].strip()
    return factstore.add(subj, f["predicate"], f["fact_text"], obj_id=obj_id, obj_literal=obj_lit,
                         functional=bool(f.get("functional")), start=f.get("valid_from"),
                         confidence=_conf(f), privacy=privacy, ep_ids=ep_ids)


# ---------- step 6 ----------
def apply_directive(dv: dict, ep_ids: list[int]) -> str:
    key = dv["supersession_key"].strip().lower()
    cur = one("SELECT id, directive FROM user_directives WHERE status='active' AND supersession_key=%s", (key,))
    if cur and cur["directive"].strip().lower() == dv["directive"].strip().lower():
        return "same"
    if cur:
        q("UPDATE user_directives SET status='superseded' WHERE id=%s", (cur["id"],))
    new = one("""INSERT INTO user_directives(directive, category, supersession_key, status, source_episode_ids)
                 VALUES (%s,%s,%s,'active',%s) RETURNING id""",
              (dv["directive"], dv.get("category", "preference") if dv.get("category") in
               ("talk_style", "routine", "preference", "boundary", "goal") else "preference", key, ep_ids))
    if cur:
        q("UPDATE user_directives SET superseded_by=%s WHERE id=%s", (new["id"], cur["id"]))
    return "superseded" if cur else "added"


# same keys as the real-time instructions (instructions.py), so the night job and the turn replace each other
TOPIC_KEY = {"call_me": "call_me", "reply_length": "brevity", "questions": "questions", "humour": "humour"}


def directive_key(dv: dict) -> str | None:
    """A canonical supersession key, or None to skip it (language is decided per turn, D34; one-off commands)."""
    from .lang import is_language_rule
    text, topic = (dv.get("directive") or "").strip(), dv.get("topic") or "other"
    if not text or dv.get("standing") is False or topic == "language" or is_language_rule(text) \
            or re.search(r"\b(switch to|talk in|speak in|reply in)\b", text, re.I):
        return None
    if topic in TOPIC_KEY:
        return TOPIC_KEY[topic]
    return f"{topic}:" + "_".join(re.findall(r"[a-z]+", text.lower())[:6])


# ---------- step 3: what goes to the LLM, and what comes back ----------
_TRIVIAL = re.compile(r"^\W*(hey|hi|hello|ok(ay)?|yeah|yes|ya+|no|nope|thanks?|thank you|bye|good ?night|hmm+|so|"
                      r"(hey |hi |hello )?st?iti|shut up|stop|nothing|great|cool|sure)\W*$", re.I)
_ASK = re.compile(r"^\W*(what|who|whom|whose|when|where|why|how|which|can|could|would|will|do|does|did|is|are|am|"
                  r"should|shall|have|has|tell me|kya|kaun|kab|kahan|kaise|kyun)\b", re.I)
_SENT = re.compile(r"(?<=[.!?])\s+")
_STOP = set("the a an and or but to of in on at for with from is am are was were be been it this that my me i you your "
            "his her he she they them we our has have had do does did not no yes so just very really".split())


def _conf(f: dict) -> float:
    try:
        return float(f.get("confidence"))
    except (TypeError, ValueError):
        return 0.7


def statements(text: str) -> str:
    """His line minus questions and greetings; '' if nothing in it could be a fact."""
    keep = [s for s in _SENT.split(text.strip()) if s.strip() and not s.rstrip().endswith("?") and not _ASK.match(s)
            and not _TRIVIAL.match(s)]
    out = " ".join(keep).strip()
    return out if len(re.findall(r"\w+", out)) >= 3 else ""


def _norm(t: str) -> str:
    return re.sub(r"\W+", " ", t).strip().lower()


def select_lines(rows: list[dict]) -> tuple[list[dict], list[int]]:
    """rows = episodes in id order (both speakers). Returns (units, skipped_ids): one unit per owner line worth reading,
    with the reply of Stiti just before it as context. A cut-off fragment he then said in full is dropped."""
    units, skipped = [], []
    owner = [r for r in rows if r["speaker"] == "user"]
    nxt = {a["id"]: b for a, b in zip(owner, owner[1:])}
    prev_stiti: dict[int | None, str] = {}
    for r in rows:
        if r["speaker"] != "user":
            prev_stiti[r["session_id"]] = r["text"]
            continue
        n = nxt.get(r["id"])
        frag = n is not None and n["session_id"] == r["session_id"] and _norm(n["text"]).startswith(_norm(r["text"])) \
            and len(_norm(n["text"])) > len(_norm(r["text"]))
        body = "" if (frag or r["origin"] != "owner" or r["importance"] <= 1 or r.get("extracted_at")) \
            else statements(r["text"])
        if not body:
            skipped.append(r["id"])
            continue
        units.append({"id": r["id"], "text": body, "date": r["occurred_at"], "context": prev_stiti.get(r["session_id"])})
        prev_stiti[r["session_id"]] = None
    return units, skipped


def known_facts(texts: list[str], limit: int = 30) -> list[dict]:
    """Current P0/P1 facts the LLM may end or correct: his own most recent ones + any about entities named here."""
    joined = " ".join(texts)
    return q("""WITH named AS (
                  SELECT id FROM entities e WHERE merged_into IS NULL AND kind <> 'self' AND length(name) >= 3 AND (
                    word_similarity(lower(name), lower(%(t)s)) >= 0.7
                    OR EXISTS (SELECT 1 FROM unnest(aliases) a WHERE length(a) >= 3
                               AND word_similarity(lower(a), lower(%(t)s)) >= 0.7)))
                SELECT f.id, f.fact_text FROM facts f JOIN entities s ON s.id=f.subj_id
                WHERE upper_inf(f.recorded) AND f.valid @> now() AND f.privacy <= 1
                  AND (f.subj_id IN (SELECT id FROM named) OR f.obj_id IN (SELECT id FROM named) OR s.kind='self')
                ORDER BY (f.subj_id IN (SELECT id FROM named) OR f.obj_id IN (SELECT id FROM named)) DESC, f.id DESC
                LIMIT %(n)s""", {"t": joined, "n": limit})


def _close(word: str, hay: list[str]) -> bool:
    import difflib
    return any(h.startswith(word[:5]) or difflib.SequenceMatcher(None, word, h).ratio() >= 0.8 for h in hay)


def grounded(f: dict, evidence: list[str]) -> bool:
    """Some distinctive word of the fact's subject/object appears in what he said (no facts from thin air)."""
    from .. import profile
    text = " ".join(evidence)
    if re.search(r"[^\x00-\x7F]", text) and len(re.findall(r"[^\x00-\x7F]", text)) > len(text) / 3:
        return True                                    # Telugu/Hindi script: the LLM translated it; can't word-match
    hay = re.findall(r"[a-z0-9]+", text.lower())
    me = set(profile.self_aliases()) | {"owner"}
    words = [w for part in (f.get("subject", ""), f.get("object", "")) for w in re.findall(r"[a-z0-9]+", part.lower())
             if w not in _STOP and w not in me and len(w) >= 3]
    return not words or any(_close(w, hay) for w in words)


def check_fact(f: dict, by_id: dict[int, dict]) -> tuple[str | None, list[int]]:
    """(reject reason or None, evidence ids)."""
    ev = [x for x in (f.get("evidence_ids") or []) if isinstance(x, int) and x in by_id]
    if not (f.get("subject") or "").strip() or not (f.get("object") or "").strip() or not (f.get("fact_text") or "").strip():
        return "empty", ev
    if not ev:
        return "no_evidence", ev
    if _conf(f) < 0.6:
        return "low_confidence", ev
    if re.fullmatch(r"(stiti|the assistant|assistant|you)", f["subject"].strip(), re.I):
        return "about_stiti", ev
    if len(f["object"]) > 120 or len(f["fact_text"]) > 240:
        return "too_long", ev
    if not grounded(f, [by_id[x]["text"] for x in ev]):
        alt = [i for i, u in by_id.items() if grounded(f, [u["text"]])]   # the model cited the line next to it
        if not alt or len(alt) > 2:
            return "ungrounded", ev
        ev = alt
    if contradicted(f, [by_id[x]["text"] for x in ev]):
        return "contradicted", ev
    return None, ev


CHANGE_RX = re.compile(r"^(left|quit|resigned_from|stopped|stopped_\w+|no_longer_\w+|gave_up|finished|"
                       r"ended|moved_out_of|graduated_from|broke_up_with)$")
_ENDING = re.compile(r"\b(left|quit|finished|resigned|ended|no longer|not\b.{0,30}\banymore|anymore|stopped|gave up|"
                     r"chhod|chod|done with|moved out|over now|is over|was over)\b", re.I)


def contradicted(f: dict, evidence: list[str]) -> bool:
    """'I finished my internship at Ledgerly, I left' → a weak model still writes 'Ravi interns at Ledgerly'. A current
    tie (works_at / interns_at / plays …) whose object sits in a sentence that says it ended is dropped."""
    pred = factstore.norm_predicate(f.get("predicate", ""))
    if pred not in factstore.TIES or pred in ("noted", "is") or CHANGE_RX.search(pred) \
            or factstore.PAST_RX.search(f.get("fact_text") or ""):
        return False                                # "Ravi finished his internship at X" IS the change
    words = [w for w in re.findall(r"[a-z0-9]+", (f.get("object") or "").lower()) if len(w) >= 3 and w not in _STOP]
    for e in evidence:
        for sent in re.split(r"(?<=[.!?;])\s+|,\s+(?=(?:and |but |so )?i\b)", e):
            low = sent.lower()
            if _ENDING.search(sent) and any(re.search(rf"\b{re.escape(w)}", low) for w in words):
                return True
    return False


def extract_units(units: list[dict], stats: dict, provider_box: dict, route: str = "extract") -> None:
    """One LLM call for a batch of his lines → entities, facts (merged/superseded), ends, directives. Raises NoProvider."""
    from .. import profile
    owner = profile.name()
    by_id = {u["id"]: u for u in units}
    lines = []
    for u in units:
        if u["context"]:
            lines.append(f"Stiti: {u['context'][:160]}")
        lines.append(f"[{u['id']}] ({u['date'].astimezone(CFG.tz):%Y-%m-%d}) {owner}: {u['text'][:400]}")
    known = known_facts([u["text"] for u in units])
    known_ids = {k["id"] for k in known}
    prompt = EXTRACT_PROMPT.format(owner=owner, today=f"{datetime.now(CFG.tz):%Y-%m-%d}",
                                   known="\n".join(f"F{k['id']}: {k['fact_text'][:160]}" for k in known) or "(none)",
                                   lines="\n".join(lines))
    res = router.complete([{"role": "user", "content": prompt}], route=route, privacy=1,
                          max_tokens=2000, temperature=0.1, schema=EXTRACT_SCHEMA, schema_name="memory")
    provider_box["provider"] = res["provider"]
    provider_box["tokens"] = provider_box.get("tokens", 0) + res["tokens_in"] + res["tokens_out"]
    t = res["text"]
    data = json.loads(t[t.find("{"):t.rfind("}") + 1])
    rej = stats.setdefault("rejected", {})
    ents = {}
    texts = " ".join(u["text"] for u in units).lower()
    for e in data.get("entities") or []:
        name = (e.get("name") or "").strip()
        kind = e.get("kind") if e.get("kind") in KINDS else "thing"
        if not name or re.fullmatch(r"stiti", name, re.I):
            continue
        aliases = [a for a in (e.get("aliases") or []) if isinstance(a, str) and a.strip()]
        if kind != "self" and not any(_close(w, re.findall(r"[a-z0-9]+", texts))
                                      for x in [name] + aliases for w in re.findall(r"[a-z0-9]+", x.lower())
                                      if len(w) >= 3 and w not in _STOP and w not in profile.self_aliases()):
            rej["entity_not_said"] = rej.get("entity_not_said", 0) + 1
            _example(stats, "entity_not_said", name)
            continue
        eid = resolve_entity(name, kind, aliases)
        ents[name.lower()] = (eid, kind, [name] + aliases)
        stats["entities"] += 1
    kinds = {k: v[1] for k, v in ents.items()}
    for eid, kind, names in ents.values():          # episode_mentions: every line of his that names it
        if kind == "self":
            continue
        hits = [u["id"] for u in units if any(len(n) >= 3 and re.search(rf"\b{re.escape(n.lower())}\b", u["text"].lower())
                                              for n in names)]
        stats["mentions"] += factstore.link(hits, [eid])
    new_ids: dict[int, int] = {}
    for f in data.get("facts") or []:
        why, ev = check_fact(f, by_id)
        if why:
            rej[why] = rej.get(why, 0) + 1
            _example(stats, why, f.get("fact_text") or f"{f.get('subject')} {f.get('predicate')} {f.get('object')}")
            continue
        r, fid = apply_fact(f, ev, kinds)
        stats["facts"][r] = stats["facts"].get(r, 0) + 1
        for x in ev:
            new_ids.setdefault(x, fid)
        if r != "confirmed" and CHANGE_RX.search(factstore.norm_predicate(f["predicate"])):
            # "Ravi left Ledgerly" even when the model forgot the `ends`: his present-tense ties to it end here
            subj = one("SELECT subj_id FROM facts WHERE id=%s", (fid,))["subj_id"]
            stats["ended"] += len(factstore.close_ties(subj, f["object"], f.get("valid_from"), fid))
    for en in data.get("ends") or []:
        fid = en.get("fact_id")
        if isinstance(fid, str) and fid.lstrip("Ff").isdigit():
            fid = int(fid.lstrip("Ff"))
        ev = [x for x in (en.get("evidence_ids") or []) if x in by_id]
        if fid not in known_ids:
            rej["bad_end"] = rej.get("bad_end", 0) + 1
            _example(stats, "bad_end", f"F{fid} {en}")
            continue
        by = next((new_ids[x] for x in ev if x in new_ids), None)
        if en.get("wrong"):
            stats["corrected"] += factstore.retract_fact(fid, by)
        else:
            stats["ended"] += factstore.end_fact(fid, en.get("valid_to"), by)
    for dv in data.get("directives") or []:
        ev = [x for x in (dv.get("evidence_ids") or []) if x in by_id]
        key = directive_key(dv)
        if not key or not ev:
            rej["directive_skipped"] = rej.get("directive_skipped", 0) + 1
            continue
        r = apply_directive({**dv, "supersession_key": key}, ev)
        stats["directives"][r] = stats["directives"].get(r, 0) + 1


def _example(stats: dict, why: str, what: str) -> None:
    """A few rejected items, for `stiti sleep` / tuning (local only: stats live in consolidation_runs)."""
    ex = stats.setdefault("examples", [])
    if len(ex) < 6:
        ex.append(f"{why}: {str(what)[:90]}")


def _new_stats() -> dict:
    return {"batches": 0, "lines": 0, "skipped_lines": 0, "facts": {}, "ended": 0, "corrected": 0, "entities": 0,
            "mentions": 0, "directives": {}, "rejected": {}}


BATCH = 16          # his lines per LLM call: ~2.5k prompt tokens + 2k out fits Groq's 8k TPM


def extract(verbose: bool = False, limit: int = 600) -> dict:
    """Steps 3–6 over everything since the watermark. Resumable: a cloud outage ends the run 'partial'."""
    rid, wm = _run_start("extract")
    stats = _new_stats()
    box: dict = {}
    last_id = wm
    rows = q("""SELECT id, session_id, speaker, origin, importance, occurred_at, text, extracted_at FROM episodes
                WHERE id > %s AND privacy <= 1 AND speaker IN ('user','stiti') ORDER BY id LIMIT %s""", (wm, limit))
    units, skipped = select_lines(rows)
    stats["lines"], stats["skipped_lines"] = len(units), len(skipped)
    if skipped:
        q("UPDATE episodes SET extracted_at=now() WHERE id = ANY(%s) AND speaker='user'", (skipped,))
    try:
        for i in range(0, len(units), BATCH):
            batch = units[i:i + BATCH]
            for attempt in (0, 1):
                try:
                    extract_units(batch, stats, box)
                    break
                except router.NoProvider:
                    if attempt:
                        raise
                    import time
                    time.sleep(0 if os.environ.get("STITI_SLEEP_NO_WAIT") else 61)   # per-minute token limits
                except (ValueError, KeyError, TypeError) as e:    # a malformed answer: skip this batch, never stall
                    stats["rejected"]["bad_batch"] = stats["rejected"].get("bad_batch", 0) + 1
                    print(f"[sleep] batch skipped: {type(e).__name__}: {e}"[:200], flush=True)
                    break
            q("UPDATE episodes SET extracted_at=now() WHERE id = ANY(%s)", ([u["id"] for u in batch],))
            last_id = batch[-1]["id"]
            stats["batches"] += 1
            if verbose:
                print(f"  extract batch {stats['batches']}: {stats}")
        last_id = rows[-1]["id"] if rows else wm
        _run_end(rid, "ok", last_id, stats, box.get("provider"), box.get("tokens", 0))
    except router.NoProvider as e:
        _run_end(rid, "partial", last_id, stats, box.get("provider"), box.get("tokens", 0), f"no provider: {e}")
        stats["skipped"] = f"cloud unavailable ({e}); will resume from episode {last_id}"
    except Exception as e:
        _run_end(rid, "failed", last_id, stats, box.get("provider"), box.get("tokens", 0), str(e)[:500])
        stats["error"] = str(e)[:200]
    return stats


def extract_episodes(ep_ids: list[int]) -> dict:
    """Real time (lifeupdate.py, background thread after the reply): the same extraction for one or two turns."""
    stats = _new_stats()
    rows = q("""SELECT id, session_id, speaker, origin, importance, occurred_at, text, NULL::timestamptz extracted_at
                FROM episodes WHERE privacy <= 1 AND (id = ANY(%s) OR id IN (
                  SELECT max(p.id) FROM episodes p JOIN episodes e ON e.session_id=p.session_id
                  WHERE e.id = ANY(%s) AND p.id < e.id AND p.speaker='stiti' GROUP BY e.id))
                ORDER BY id""", (ep_ids, ep_ids))
    units, _ = select_lines(rows)
    if units:                       # while he's talking: never the voice chain's Groq model
        extract_units(units, stats, {}, route="background_smart")
        q("UPDATE episodes SET extracted_at=now() WHERE id = ANY(%s)", ([u["id"] for u in units],))
    return stats


# ---------- steps 8-10 ----------
def decay() -> None:
    q("""UPDATE episodes SET strength = GREATEST(0.2, strength * CASE WHEN access_count > 3 THEN 0.99 ELSE 0.97 END)
         WHERE occurred_at < now() - interval '1 day'""")


PROFILE_CHARS = 900


def standing_profile() -> str:
    """The always-on 'who he is' block (briefing_cache): his newest facts first (a life update must show up the same
    day, not lose to day-one resume lines), then his most certain ones, then his people, then his standing rules."""
    cur = """upper_inf(f.recorded) AND f.valid @> now() AND f.privacy <= 1"""
    newest = q(f"""SELECT f.id, f.fact_text FROM facts f JOIN entities e ON e.id=f.subj_id
                   WHERE e.kind='self' AND {cur} ORDER BY GREATEST(lower(f.valid), lower(f.recorded)) DESC, f.id DESC
                   LIMIT 6""")
    surest = q(f"""SELECT f.id, f.fact_text FROM facts f JOIN entities e ON e.id=f.subj_id
                   WHERE e.kind='self' AND {cur} ORDER BY f.confidence DESC, f.id DESC LIMIT 8""")
    people = q(f"""SELECT f.id, f.fact_text FROM facts f JOIN entities s ON s.id=f.subj_id
                   LEFT JOIN entities o ON o.id=f.obj_id
                   WHERE {cur} AND s.kind <> 'self' AND (o.kind='self' OR s.kind='person')
                   ORDER BY f.confidence DESC, f.id DESC LIMIT 4""")
    dirs = q("SELECT directive FROM user_directives WHERE status='active' ORDER BY category, id LIMIT 10")
    seen, lines = set(), []
    for r in newest + surest + people:
        if r["id"] not in seen:
            seen.add(r["id"])
            lines.append(f"- {r['fact_text']}")
    lines += [f"- {r['directive']}" for r in dirs]
    out, n = [], 0
    for line in lines:                      # whole lines only, within budget
        if n + len(line) + 1 > PROFILE_CHARS:
            continue
        out.append(line)
        n += len(line) + 1
    text = "\n".join(out)
    if text:
        q("""INSERT INTO briefing_cache(key, content, tokens) VALUES ('standing_profile', %s, %s)
             ON CONFLICT (key) DO UPDATE SET content=EXCLUDED.content, tokens=EXCLUDED.tokens, built_at=now()""",
          (text, len(text) // 4))
    else:                                   # everything ended/retracted: never serve a stale profile
        q("DELETE FROM briefing_cache WHERE key='standing_profile'")
    return text


def render() -> None:
    from .mdsync import render_all, sync
    home = CFG.home
    sync()            # owner edits first — they always win
    render_all()
    # graphify-style report: god nodes = degree x recency
    gods = q("""SELECT e.name, e.kind, count(f.id) deg FROM entities e
                JOIN facts f ON (f.subj_id=e.id OR f.obj_id=e.id) AND upper_inf(f.recorded) AND f.valid @> now()
                WHERE e.merged_into IS NULL GROUP BY e.id ORDER BY deg DESC, max(f.id) DESC LIMIT 15""")
    cur = q("""SELECT f.fact_text FROM facts f WHERE upper_inf(f.recorded) AND f.valid @> now() ORDER BY f.id DESC LIMIT 40""")
    changed = q("""SELECT f.fact_text, upper(f.valid) ended FROM facts f WHERE NOT upper_inf(f.valid)
                   AND upper(f.valid) IS NOT NULL AND upper_inf(f.recorded) ORDER BY upper(f.valid) DESC LIMIT 10""")
    from .. import profile
    g = [f"# GRAPH_REPORT — {profile.name()}'s life graph", f"_Built {datetime.now(CFG.tz):%Y-%m-%d %H:%M}_", "",
         "## Central nodes"] + [f"- **{r['name']}** ({r['kind']}) — {r['deg']} current facts" for r in gods]
    g += ["", "## Current facts"] + [f"- {r['fact_text']}" for r in cur]
    g += ["", "## Recently changed (kept, not deleted)"] + [f"- {r['fact_text']} — ended {r['ended']:%Y-%m-%d}"
                                                           for r in changed]
    (home / "GRAPH_REPORT.md").write_text("\n".join(g) + "\n")
    from .graphview import render as render_graph
    render_graph(open_browser=False)


def _step(out: dict, key: str, fn, verbose: bool):
    """One night step; a failure is logged and the rest still run (a reflection crash must not cost the facts)."""
    try:
        out[key] = fn()
    except Exception as e:
        out[key] = f"FAILED: {type(e).__name__}: {e}"[:300]
    if verbose:
        print(f"  {key}: {out[key]}")
    return out[key]


def summary(out: dict) -> str:
    """One log line with the counts that matter: did she learn anything tonight?"""
    ex = out.get("extract") if isinstance(out.get("extract"), dict) else {}
    facts = ex.get("facts") or {}
    prof = out.get("profile")
    return (f"lines {ex.get('lines', 0)} (+{ex.get('skipped_lines', 0)} skipped) · facts +{facts.get('added', 0)} "
            f"={facts.get('confirmed', 0)} ~{facts.get('superseded', 0)} · ended {ex.get('ended', 0)} · corrected "
            f"{ex.get('corrected', 0)} · entities {ex.get('entities', 0)} · mentions {ex.get('mentions', 0)} · "
            f"directives {ex.get('directives') or {}} · rejected {ex.get('rejected') or {}} · profile "
            f"{len(prof.splitlines()) if isinstance(prof, str) else prof} lines"
            + (f" · {ex['skipped']}" if ex.get("skipped") else "") + (f" · ERROR {ex['error']}" if ex.get("error") else ""))


def nap(verbose: bool = False) -> dict:
    """Daytime catch-up after he goes quiet: only the learning steps (extract → profile → USER.md), no backup."""
    out: dict = {}
    _step(out, "embedded", embed_backlog, verbose)
    _step(out, "extract", lambda: extract(verbose), verbose)
    _step(out, "profile", standing_profile, verbose)
    _step(out, "render", render, verbose)
    return out


def pending_lines() -> int:
    """His lines the extractor hasn't read yet (for the app's nap trigger)."""
    last = one("""SELECT watermark FROM consolidation_runs WHERE job='extract' AND status IN ('ok','partial')
                  AND watermark IS NOT NULL ORDER BY id DESC LIMIT 1""")
    return one("""SELECT count(*) n FROM episodes WHERE id > %s AND speaker='user' AND origin='owner' AND privacy <= 1
                  AND importance > 1 AND extracted_at IS NULL""", (last["watermark"] if last else 0,))["n"]


def run(verbose: bool = False) -> dict:
    out: dict = {}
    rid = one("INSERT INTO consolidation_runs(job) VALUES ('night') RETURNING id")["id"]   # naps also log 'extract'
    _step(out, "embedded", embed_backlog, verbose)
    _step(out, "extract", lambda: extract(verbose), verbose)
    _step(out, "decay", decay, verbose)
    from . import learning
    _step(out, "lessons", learning.curate, verbose)
    _step(out, "segments", learning.build_segments, verbose)
    _step(out, "reflections", learning.reflect, verbose)
    _step(out, "profile", standing_profile, verbose)
    def emotion():          # D28: personal voice-emotion head from his recorded turns (no-op if the recorder never ran)
        from ..learn.emotion_train import nightly
        return nightly()
    _step(out, "emotion", emotion, verbose)
    _step(out, "render", render, verbose)
    def do_backup():
        from .backup import backup
        return str(backup())
    _step(out, "backup", do_backup, verbose)
    _run_end(rid, "ok", None, {"summary": summary(out)})
    if verbose:
        print(f"standing profile:\n{out['profile'] or '(empty yet)'}\nrendered {CFG.home}/USER.md, LESSONS.md, "
              f"GRAPH_REPORT.md\n[sleep] {summary(out)}")
    return out
