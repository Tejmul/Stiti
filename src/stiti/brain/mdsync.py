"""Two-way sync between Postgres and the human-readable files in ~/.stiti/.

USER.md and LESSONS.md are rendered with a stable id on every line ([F12], [D7], L3). When Tejmul
edits a file, the next sync imports it as OWNER EDITS (owner always wins), then re-renders:
  - changed line  → directive superseded / fact corrected / lesson edited (ACE EDIT)
  - deleted line  → directive retired / fact retracted (kept in history, never deleted) / lesson retired
  - new line      → new owner directive / fact / active lesson (no id needed, just "- text")
SOUL.md is read fresh every turn; its history lives in the encrypted backups.
Sync is cheap (hash check) and runs before every turn and in the night job.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime

from ..config import CFG
from ..db import one, q

STATE = CFG.home / ".sync.json"
USER = CFG.home / "USER.md"
LESSONS = CFG.home / "LESSONS.md"

CATS = ["talk_style", "boundary", "routine", "preference", "goal"]
CAT_TITLES = {"talk_style": "How to talk to me", "boundary": "Never do", "routine": "My routine",
              "preference": "Preferences", "goal": "Goals"}
TITLE_CAT = {v.lower(): k for k, v in CAT_TITLES.items()}

TRAIT_LINE = re.compile(r"^\s*[-*]\s*\[T:(?P<key>[\w]+)\]\s*(?P<text>.+?)\s*$")
ID_LINE = re.compile(r"^\s*[-*]\s*\[(?P<kind>[FD])(?P<id>\d+)\]\s*(?P<text>.+?)\s*$")
NEW_LINE = re.compile(r"^\s*[-*]\s+(?P<text>(?!\[[FD]\d+\]).+?)\s*$")
LESSON_LINE = re.compile(r"^\s*[-*]\s*\*\*L(?P<id>\d+)\*\*\s*\[(?P<pol>MUST NOT|MUST)\]\s*(?P<text>.+?)\s*$")
NEW_LESSON = re.compile(r"^\s*[-*]\s*\[?(?P<pol>MUST NOT|MUST|DON'?T|DO)\]?:?\s*(?P<text>.+?)\s*$", re.I)


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def _remember(name: str, text: str) -> None:
    st = _state()
    st[name] = _sha(text)
    STATE.write_text(json.dumps(st))


def _self_id() -> int:
    from .sleep import resolve_entity
    from .. import profile
    return resolve_entity(profile.name(), "self")


# ---------------- render ----------------
def render_user() -> str:
    facts = q("""SELECT f.id, f.fact_text, lower(f.valid) since FROM facts f JOIN entities e ON e.id=f.subj_id
                 WHERE e.kind='self' AND upper_inf(f.recorded) AND f.valid @> now() ORDER BY f.id""")
    others = q("""SELECT f.id, f.fact_text FROM facts f JOIN entities e ON e.id=f.subj_id
                  WHERE e.kind<>'self' AND upper_inf(f.recorded) AND f.valid @> now() AND f.privacy <= 1
                  ORDER BY f.id LIMIT 60""")
    dirs = q("SELECT id, category, directive FROM user_directives WHERE status='active' ORDER BY category, id")
    from .. import profile
    lines = [f"# USER — who {profile.call()} is and how to talk to {profile.p('obj')}", "",
             f"_Stiti keeps this file in sync with her brain ({datetime.now(CFG.tz):%Y-%m-%d %H:%M})._",
             "_Edit freely: change a line, delete a line, or add `- something` under any heading. "
             "Your edits always win. Keep the F/D number tag at the start of lines you change._", "",
             "## About me"]
    lines += [f"- [F{f['id']}] {f['fact_text']}" for f in facts] or ["- (nothing yet)"]
    lines += ["", "## People and things in my life"]
    lines += [f"- [F{f['id']}] {f['fact_text']}" for f in others] or ["- (nothing yet)"]
    traits = q("SELECT key, label, confidence, source FROM traits WHERE label IS NOT NULL ORDER BY key")
    lines += ["", "## How I understand you (tentative)",
              "_My reading from what you've told me — not a diagnosis. Rewrite a line if I got you wrong, "
              "or delete it._"]
    lines += [f"- [T:{t['key']}] {t['label']}" + ("" if t["source"] == "owner_edit" else f" · {t['confidence']:.0%} sure")
              for t in traits] or ["- (nothing yet — say “key things” for a 5-minute intro)"]
    for cat in CATS:
        lines += ["", f"## {CAT_TITLES[cat]}"]
        rows = [d for d in dirs if d["category"] == cat]
        lines += [f"- [D{d['id']}] {d['directive']}" for d in rows] or ["- (nothing yet)"]
    text = "\n".join(lines) + "\n"
    USER.write_text(text)
    _remember("USER.md", text)
    return text


def render_lessons() -> str:
    rows = q("""SELECT id, situation, guidance, polarity, confidence, seen_count FROM lessons
                WHERE status='active' ORDER BY id""")
    from .. import profile
    lines = [f"# LESSONS — how Stiti should talk to {profile.call()}", "",
             "_Edit a guidance line to change a rule, delete it to retire it, or add a new one like_",
             "_`- [MUST NOT] joke about deadlines` — your version always wins._", ""]
    for r in rows:
        lines.append(f"- **L{r['id']}** [{'MUST NOT' if r['polarity'] == 'dont' else 'MUST'}] {r['guidance']}")
        lines.append(f"  _when:_ {r['situation']} · conf {r['confidence']:.2f} · seen {r['seen_count']}")
    text = "\n".join(lines) + "\n"
    LESSONS.write_text(text)
    _remember("LESSONS.md", text)
    return text


# ---------------- import ----------------
def _import_user(text: str) -> dict:
    stats = {"changed": 0, "removed": 0, "added": 0}
    seen_f, seen_d = set(), set()
    section = None
    seen_t = set()
    for line in text.splitlines():
        h = re.match(r"^##\s+(.+?)\s*$", line)
        if h:
            section = h.group(1).strip().lower()
            continue
        tm = TRAIT_LINE.match(line)
        if tm:
            key, new = tm["key"], re.sub(r"\s*·\s*\d+% sure\s*$", "", tm["text"]).strip()
            seen_t.add(key)
            row = one("SELECT label FROM traits WHERE key=%s", (key,))
            if row and (row["label"] or "").strip() != new:
                q("""UPDATE traits SET label=%s, source='owner_edit', confidence=0.95, value=NULL, updated_at=now()
                     WHERE key=%s""", (new, key))
                stats["changed"] += 1
            continue
        m = ID_LINE.match(line)
        if m:
            kind, rid, new = m["kind"], int(m["id"]), m["text"].strip()
            if kind == "F":
                seen_f.add(rid)
                row = one("SELECT fact_text, subj_id FROM facts WHERE id=%s AND upper_inf(recorded)", (rid,))
                if row and row["fact_text"].strip() != new:
                    _correct_fact(rid, row["subj_id"], new)
                    stats["changed"] += 1
            else:
                seen_d.add(rid)
                row = one("SELECT directive, category, supersession_key FROM user_directives WHERE id=%s AND status='active'",
                          (rid,))
                if row and row["directive"].strip() != new:
                    nid = one("""INSERT INTO user_directives(directive, category, supersession_key, status, origin)
                                 VALUES (%s,%s,%s,'active','owner_edit') RETURNING id""",
                              (new, row["category"], f"{row['supersession_key']}#{rid}"))["id"]
                    q("UPDATE user_directives SET status='superseded', superseded_by=%s WHERE id=%s", (nid, rid))
                    seen_d.add(nid)
                    stats["changed"] += 1
            continue
        n = NEW_LINE.match(line)
        if n and section and "(nothing yet)" not in n["text"]:
            new = n["text"].strip()
            if section in ("about me", "people and things in my life"):
                q("""INSERT INTO facts(subj_id, predicate, obj_literal, fact_text, confidence, origin)
                     VALUES (%s,'noted',%s,%s,0.95,'owner_edit')""", (_self_id(), new, new))
            elif section in TITLE_CAT:
                cat = TITLE_CAT[section]
                q("""INSERT INTO user_directives(directive, category, supersession_key, status, origin)
                     VALUES (%s,%s,%s,'active','owner_edit')""", (new, cat, f"owner_{_sha(new)[:10]}"))
            else:
                continue
            stats["added"] += 1
    # ids that were in the last render but are gone from the file = owner removed them
    for rid in _last_rendered_ids("F") - seen_f:
        stats["removed"] += len(q("""UPDATE facts SET recorded = tstzrange(lower(recorded), now())
                                     WHERE id=%s AND upper_inf(recorded) RETURNING id""", (rid,)))
    for rid in _last_rendered_ids("D") - seen_d:
        stats["removed"] += len(q("""UPDATE user_directives SET status='superseded'
                                     WHERE id=%s AND status='active' RETURNING id""", (rid,)))
    for key in set(_state().get("ids_T", [])) - seen_t:
        stats["removed"] += len(q("DELETE FROM traits WHERE key=%s RETURNING key", (key,)))
    return stats


def _correct_fact(rid: int, subj: int, new_text: str) -> None:
    """Owner says the fact is wrong: retract it from the record (kept in history) and store his version."""
    q("UPDATE facts SET recorded = tstzrange(lower(recorded), now()) WHERE id=%s", (rid,))
    q("""INSERT INTO facts(subj_id, predicate, obj_literal, fact_text, confidence, origin)
         VALUES (%s,'noted',%s,%s,0.95,'owner_edit')""", (subj, new_text, new_text))


def _last_rendered_ids(kind: str) -> set[int]:
    return set(_state().get(f"ids_{kind}", []))


def _record_ids() -> None:
    st = _state()
    txt = USER.read_text() if USER.exists() else ""
    ids = [ID_LINE.match(line) for line in txt.splitlines()]          # only real list lines count
    st["ids_F"] = sorted({int(m["id"]) for m in ids if m and m["kind"] == "F"})
    st["ids_D"] = sorted({int(m["id"]) for m in ids if m and m["kind"] == "D"})
    st["ids_T"] = sorted({m["key"] for m in map(TRAIT_LINE.match, txt.splitlines()) if m})
    STATE.write_text(json.dumps(st))


def _import_lessons(text: str) -> dict:
    from .. import embed
    stats = {"changed": 0, "removed": 0, "added": 0}
    seen = set()
    for line in text.splitlines():
        m = LESSON_LINE.match(line)
        if m:
            lid, new, pol = int(m["id"]), m["text"].strip(), ("dont" if m["pol"] == "MUST NOT" else "do")
            seen.add(lid)
            row = one("SELECT guidance, polarity, situation FROM lessons WHERE id=%s AND status='active'", (lid,))
            if row and (row["guidance"].strip() != new or row["polarity"] != pol):
                vec = embed.embed_docs([f"{row['situation']}. {new}"])[0]
                q("""UPDATE lessons SET guidance=%s, polarity=%s, situation_embedding=%s, origin='owner_edit',
                            confidence=GREATEST(confidence, 0.95) WHERE id=%s""", (new, pol, vec, lid))
                stats["changed"] += 1
            continue
        if line.strip().startswith(("- **L", "  _when")) or line.startswith("#") or line.startswith("_"):
            continue
        n = NEW_LESSON.match(line)
        if n and n["text"]:
            pol = "dont" if n["pol"].upper().startswith(("MUST NOT", "DON")) else "do"
            vec = embed.embed_docs([f"Any situation. {n['text']}"])[0]
            q("""INSERT INTO lessons(situation, guidance, polarity, source, status, confidence, situation_embedding, origin)
                 VALUES ('Any situation (written by Tejmul)', %s, %s, 'owner_explicit', 'active', 0.95, %s, 'owner_edit')""",
              (n["text"], pol, vec))
            stats["added"] += 1
    active = {r["id"] for r in q("SELECT id FROM lessons WHERE status='active'")}
    rendered = set(_state().get("ids_L", []))
    for lid in (active & rendered) - seen:
        stats["removed"] += len(q("UPDATE lessons SET status='retired' WHERE id=%s RETURNING id", (lid,)))
    return stats


def sync() -> dict:
    """Import owner edits if a file changed since Stiti last wrote it, then re-render. Cheap when unchanged."""
    out = {}
    st = _state()
    if USER.exists():
        txt = USER.read_text()
        if st.get("USER.md") and _sha(txt) != st["USER.md"]:
            out["USER.md"] = _import_user(txt)
    if LESSONS.exists():
        txt = LESSONS.read_text()
        if st.get("LESSONS.md") and _sha(txt) != st["LESSONS.md"]:
            out["LESSONS.md"] = _import_lessons(txt)
    if out or not st.get("USER.md") or not st.get("LESSONS.md"):
        render_all()
    return out


def render_all() -> None:
    render_user()
    render_lessons()
    _record_ids()
    st = _state()
    st["ids_L"] = sorted(int(m["id"]) for m in map(LESSON_LINE.match, LESSONS.read_text().splitlines()) if m)
    STATE.write_text(json.dumps(st))
