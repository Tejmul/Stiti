"""Sleep / consolidation (report §Consolidation): idempotent, watermarked steps.

1 embed backlog · 3 extract entities/facts/directives (cloud, P0/P1 owner episodes only)
4 resolve entities (no LLM) · 5 apply bitemporal facts · 6 supersede directives
8 strength decay (nothing deleted) · 9 precompile standing profile · 10 render USER.md /
LESSONS.md / GRAPH_REPORT.md. Cloud steps end `partial` when no provider is available and
resume next run from the watermark. P2 never enters an LLM step.
"""
from __future__ import annotations

import json
from datetime import datetime

from .. import embed, router
from ..config import CFG
from ..db import one, q
from . import lessons

EXTRACT_PROMPT = """You extract durable memory for a personal assistant about its owner, {owner}.
From the owner's messages below, return ONLY JSON:
{"entities":[{"name":"","kind":"self|person|project|place|org|event|feeling|topic|thing","aliases":[]}],
 "facts":[{"subject":"","predicate":"snake_case verb","object":"","object_is_entity":true,
           "fact_text":"one plain sentence","functional":false,"valid_from":"YYYY-MM-DD or null",
           "evidence_ids":[0],"confidence":0.0}],
 "directives":[{"directive":"imperative rule for the assistant, e.g. 'Reply in Hinglish when I do'",
                "category":"talk_style|routine|preference|boundary|goal","supersession_key":"snake_case",
                "evidence_ids":[0]}]}
Rules: the owner is the subject "{owner}" (kind self). Only facts the owner states or clearly implies — no guesses.
functional=true when a subject can only have one value at a time (lives_in, works_at, relationship_status).
Skip commands (todos/alarms), small talk and questions. Use names as written (Hinglish is fine). Empty lists are fine.

MESSAGES:
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
    if not row:
        row = one("""SELECT id FROM entities WHERE merged_into IS NULL AND kind=%s AND similarity(lower(name), lower(%s)) >= 0.6
                     ORDER BY similarity(lower(name), lower(%s)) DESC LIMIT 1""", (kind, name, name))
    vec = embed.embed_docs([f"{kind}: {name}"])[0]
    if not row:
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
def apply_fact(f: dict, ep_ids: list[int], kinds: dict[str, str]) -> str:
    subj = resolve_entity(f["subject"], kinds.get(f["subject"].lower(), "person"))
    obj_id, obj_lit = None, None
    if f.get("object_is_entity", True):
        obj_id = resolve_entity(f["object"], kinds.get(f["object"].lower(), "thing"))
    else:
        obj_lit = f["object"]
    pred = f["predicate"].strip().lower().replace(" ", "_")
    functional = bool(f.get("functional"))
    vf = f.get("valid_from")
    try:
        start = datetime.fromisoformat(vf).replace(tzinfo=CFG.tz) if vf else None
    except ValueError:
        start = None
    same = one("""SELECT id FROM facts WHERE subj_id=%s AND predicate=%s AND upper_inf(recorded) AND valid @> now()
                    AND obj_id IS NOT DISTINCT FROM %s AND obj_literal IS NOT DISTINCT FROM %s LIMIT 1""",
               (subj, pred, obj_id, obj_lit))
    if same:
        q("""UPDATE facts SET confidence = LEAST(confidence + 0.1, 0.99),
                    source_episode_ids = ARRAY(SELECT DISTINCT unnest(source_episode_ids || %s::bigint[]))
             WHERE id=%s""", (ep_ids, same["id"]))
        return "confirmed"
    vec = embed.embed_docs([f["fact_text"]])[0]
    old = one("""SELECT id, valid FROM facts WHERE subj_id=%s AND predicate=%s AND functional AND upper_inf(recorded)
                   AND valid @> now() LIMIT 1""", (subj, pred)) if functional else None
    new = one("""INSERT INTO facts(subj_id, predicate, obj_id, obj_literal, fact_text, functional, valid, confidence,
                                   source_episode_ids, embedding)
                 VALUES (%s,%s,%s,%s,%s,false,tstzrange(COALESCE(%s, now()), NULL),%s,%s,%s) RETURNING id""",
              (subj, pred, obj_id, obj_lit, f["fact_text"], start, float(f.get("confidence", 0.7)), ep_ids, vec))
    if old:  # close the old interval in the same breath; never delete
        q("""UPDATE facts SET valid = tstzrange(lower(valid), GREATEST(lower(valid), COALESCE(%s, now()))),
                    invalidated_by=%s WHERE id=%s""", (start, new["id"], old["id"]))
    if functional:
        q("UPDATE facts SET functional=true WHERE id=%s", (new["id"],))
    for e in (subj, obj_id):
        if e:
            for ep in ep_ids:
                q("INSERT INTO episode_mentions VALUES (%s,%s) ON CONFLICT DO NOTHING", (ep, e))
    return "superseded" if old else "added"


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


# ---------- step 3 driver ----------
def extract(verbose: bool = False) -> dict:
    rid, wm = _run_start("extract")
    stats = {"batches": 0, "facts": {}, "directives": {}, "entities": 0}
    tokens, provider, last_id = 0, None, wm
    rows = q("""SELECT id, occurred_at, text FROM episodes
                WHERE id > %s AND speaker='user' AND origin='owner' AND privacy <= 1 AND importance > 1
                ORDER BY id LIMIT 400""", (wm,))
    try:
        for i in range(0, len(rows), 20):
            batch = rows[i:i + 20]
            msgs = "\n".join(f"[{r['id']}] ({r['occurred_at'].astimezone(CFG.tz):%Y-%m-%d}) {r['text']}" for r in batch)
            from .. import profile
            res = router.complete([{"role": "user", "content": EXTRACT_PROMPT.replace("{owner}", profile.name()) + msgs}], route="background_smart",
                                  privacy=1, max_tokens=1500, temperature=0.1, json_mode=True)
            provider, tokens = res["provider"], tokens + res["tokens_in"] + res["tokens_out"]
            data = json.loads(res["text"][res["text"].find("{"):res["text"].rfind("}") + 1])
            ids_ok = {r["id"] for r in batch}
            kinds = {e["name"].lower(): e.get("kind", "thing") for e in data.get("entities", [])}
            for e in data.get("entities", []):
                resolve_entity(e["name"], e.get("kind", "thing"), e.get("aliases") or [])
                stats["entities"] += 1
            for f in data.get("facts", []):
                ev = [x for x in f.get("evidence_ids", []) if x in ids_ok] or [batch[-1]["id"]]
                if float(f.get("confidence", 0.7)) < 0.5 or not f.get("subject") or not f.get("object"):
                    continue
                r = apply_fact(f, ev, kinds)
                stats["facts"][r] = stats["facts"].get(r, 0) + 1
            for dv in data.get("directives", []):
                ev = [x for x in dv.get("evidence_ids", []) if x in ids_ok] or [batch[-1]["id"]]
                if dv.get("directive") and dv.get("supersession_key"):
                    r = apply_directive(dv, ev)
                    stats["directives"][r] = stats["directives"].get(r, 0) + 1
            q("UPDATE episodes SET extracted_at=now() WHERE id = ANY(%s)", ([r["id"] for r in batch],))
            last_id = batch[-1]["id"]
            stats["batches"] += 1
            if verbose:
                print(f"  extract batch {stats['batches']}: {stats}")
        _run_end(rid, "ok", last_id, stats, provider, tokens)
    except router.NoProvider as e:
        _run_end(rid, "partial", last_id, stats, provider, tokens, f"no provider: {e}")
        stats["skipped"] = f"cloud unavailable ({e}); will resume from episode {last_id}"
    except Exception as e:
        _run_end(rid, "failed", last_id, stats, provider, tokens, str(e)[:500])
        stats["error"] = str(e)[:200]
    return stats


# ---------- steps 8-10 ----------
def decay() -> None:
    q("""UPDATE episodes SET strength = GREATEST(0.2, strength * CASE WHEN access_count > 3 THEN 0.99 ELSE 0.97 END)
         WHERE occurred_at < now() - interval '1 day'""")


def standing_profile() -> str:
    dirs = q("SELECT directive FROM user_directives WHERE status='active' ORDER BY category, id LIMIT 10")
    facts = q("""SELECT f.fact_text FROM facts f JOIN entities e ON e.id=f.subj_id
                 WHERE e.kind='self' AND upper_inf(f.recorded) AND f.valid @> now() AND f.privacy <= 1
                 ORDER BY f.confidence DESC, f.id DESC LIMIT 10""")
    text = "\n".join([f"- {r['fact_text']}" for r in facts] + [f"- {r['directive']}" for r in dirs])
    if text:
        q("""INSERT INTO briefing_cache(key, content, tokens) VALUES ('standing_profile', %s, %s)
             ON CONFLICT (key) DO UPDATE SET content=EXCLUDED.content, tokens=EXCLUDED.tokens, built_at=now()""",
          (text[:700], len(text[:700]) // 4))
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
                   ORDER BY upper(f.valid) DESC LIMIT 10""")
    from .. import profile
    g = [f"# GRAPH_REPORT — {profile.name()}'s life graph", f"_Built {datetime.now(CFG.tz):%Y-%m-%d %H:%M}_", "",
         "## Central nodes"] + [f"- **{r['name']}** ({r['kind']}) — {r['deg']} current facts" for r in gods]
    g += ["", "## Current facts"] + [f"- {r['fact_text']}" for r in cur]
    g += ["", "## Recently changed (kept, not deleted)"] + [f"- {r['fact_text']} — ended {r['ended']:%Y-%m-%d}"
                                                           for r in changed]
    (home / "GRAPH_REPORT.md").write_text("\n".join(g) + "\n")
    from .graphview import render as render_graph
    render_graph(open_browser=False)


def run(verbose: bool = False) -> dict:
    out = {"embedded": embed_backlog()}
    if verbose:
        print(f"1. embedded backlog: {out['embedded']}")
    out["extract"] = extract(verbose)
    if verbose:
        print(f"3-6. extract/resolve/apply: {out['extract']}")
    decay()
    from . import learning
    out["lessons"] = learning.curate()
    out["segments"] = learning.build_segments()
    out["reflections"] = learning.reflect()
    if verbose:
        print(f"7. lessons curated {out['lessons']} · segments {out['segments']} · reflections {out['reflections']}")
    out["profile"] = standing_profile()
    render()
    try:
        from .backup import backup
        out["backup"] = str(backup())
    except Exception as e:
        out["backup"] = f"FAILED: {e}"
    if verbose:
        print(f"10. backup: {out['backup']}")
        print(f"8-10. decay done; standing profile:\n{out['profile'] or '(empty yet)'}\n"
              f"rendered {CFG.home}/USER.md, LESSONS.md, GRAPH_REPORT.md")
    return out
