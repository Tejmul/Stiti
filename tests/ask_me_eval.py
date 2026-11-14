""""Ask me questions" (D37): a get-to-know-you round of 10, stored as the brain's own knowledge — no LLM.

His words (2026-11-14): "for knowing me you have to ask questions — ask me 10 questions when I say to ask, which
gathers info about what I want, ambitions, shows, animes I see, characters I like, etc."
Made-up owner and answers only.

STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp> uv run python tests/ask_me_eval.py
"""
from __future__ import annotations

import os
import sys

db = os.environ.get("STITI_DB", "")
if not db.rstrip("/").split("/")[-1].startswith("stiti_test"):
    sys.exit(f"refusing to run against {db!r}: use a stiti_test* database")
os.environ.setdefault("STITI_LIVE_WARM", "0")
os.environ.setdefault("STITI_EVENTKIT", "off")

passed = total = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, total
    total += 1
    passed += bool(cond)
    print(f"  {'✓' if cond else '✗'} {name}" + (f" — {detail}" if detail and not cond else ""))


from stiti import profile, router                                        # noqa: E402
from stiti.brain import askme as A                                       # noqa: E402
from stiti.db import one, q                                              # noqa: E402

A.STATE.unlink(missing_ok=True)
profile.set("name", "Kiran")
profile.set("pronouns", "he")


def current(key: str) -> list[dict]:
    return q("""SELECT f.* FROM facts f JOIN entities e ON e.id=f.subj_id WHERE e.kind='self' AND f.predicate=%s
                AND upper_inf(f.recorded) AND f.valid @> now()""", (f"about_{key}",))


def canned(key: str) -> str:
    qn = A.BY_KEY[key]
    if qn.char:
        return "umm Kenji from Star Blade, for his courage"
    if qn.items:
        return "I think mostly Moon Harbor and river song"
    if qn.want:
        return "I want to build my own robot startup"
    return "honestly long walks with my dog"


print("triggers")
for t in ("ask me questions", "Ask me something", "ask me some questions", "ask me 10 questions", "Stiti, ask me questions",
          "get to know me better", "can you get to know me better?", "know me better", "mujhse sawaal pucho",
          "mujhse kuch pucho", "kuch pucho mujhse", "quiz me about myself", "ask me anything", "nannu prashnalu adugu",
          "naa gurinchi telusuko", "key things"):
    check(f"start: {t!r}", bool(A.START_RX.search(t)))
for t in ("can you ask Priya", "ask me later", "ask me tomorrow", "ask me something tomorrow", "ask me questions about python",
          "quiz me on lexical analysis", "I asked him something", "ask Rahul if he's free", "I know me better than you",
          "the key things in my exam are dates"):
    check(f"not start: {t!r}", not A.START_RX.search(t))

print("question bank")
cats = {x.cat for x in A.BANK}
check("≥40 questions", len(A.BANK) >= 40, str(len(A.BANK)))
check("≥20 categories", len(cats) >= 20, str(sorted(cats)))
check("keys unique", len({x.key for x in A.BANK}) == len(A.BANK))
check("every category is in the rotation", cats == set(A.CAT_ORDER), str(cats ^ set(A.CAT_ORDER)))
check("every question stores something", all(x.fact or x.directive for x in A.BANK))
check("one '?' at most per question (lint keeps one)", all(x.ask.count("?") <= 1 for x in A.BANK))
for c in ("ambition", "anime", "characters", "shows", "music", "books", "games", "sports", "food", "admire", "relax",
          "annoys", "motivates", "values", "fears", "day", "places", "learn", "now", "career"):
    check(f"category {c}", c in cats)

print("answers cleaned without an LLM")
check("fillers stripped, words kept", A.clean("umm I think mostly Vinland Saga, you know") == "Vinland Saga",
      A.clean("umm I think mostly Vinland Saga, you know"))
check("items", A.items("Vinland Saga and one piece, also Frieren") == ["Vinland Saga", "One Piece", "Frieren"],
      str(A.items("Vinland Saga and one piece, also Frieren")))
check("items: lead words dropped", A.items("I'm watching Moon Harbor & Iron Tide too") == ["Moon Harbor", "Iron Tide"],
      str(A.items("I'm watching Moon Harbor & Iron Tide too")))
check("character + show + reason", A.character("Kenji from Star Blade, for his courage")
      == (["Kenji"], "Star Blade", "for his courage"), str(A.character("Kenji from Star Blade, for his courage")))
check("character in brackets", A.character("Mira (Iron Tide) because she never gives up")
      == (["Mira"], "Iron Tide", "because she never gives up"))
check("want: verb", A._want("I want to build my own robot startup")[1] == "you want to build your own robot startup")
check("want: noun", A._want("a new laptop")[1] == "you want a new laptop")
check("said back in second person", A.second("I'm happy when my friends call me") == "you're happy when your friends call you")
check("fact in third person", A.third("my own startup") == "his own startup")
for t in ("nothing", "don't know", "pata nahi", "no idea", "nothing really", "kuch nahi"):
    check(f"skip-like: {t!r}", bool(A.NOTHING_RX.match(A.clean(t))))

# ---------------- engine: a whole round, by text, no LLM ----------------
print("engine: a round of 10 (text / web chat)")
from stiti.engine import Engine                                          # noqa: E402

llm_calls = []


def no_llm(*a, **kw):
    llm_calls.append(a)
    raise router.NoProvider("test: no LLM")


orig_c, orig_s = router.complete, router.stream
router.complete = no_llm
router.stream = lambda *a, **kw: no_llm(*a, **kw) or iter(())
try:
    e = Engine("text")
    check("spec_block: trigger is never speculative", e.spec_block("ask me questions") is not None)
    r = e.turn("can you ask Priya to call me")
    check("'can you ask Priya' doesn't start a round", e.askme is None)
    llm_calls.clear()
    r = e.turn("ask me questions")
    check("round starts", e.askme is not None and "10 quick questions" in r, r)
    check("spec_block: mid-round is a flow", e.spec_block("Vinland Saga") == "flow")
    round1 = list(e.askme.st["round"])
    check("10 questions", len(round1) == 10, str(round1))
    check("all different", len(set(round1)) == 10)
    check("varied: 10 categories", len({A.BY_KEY[k].cat for k in round1}) == 10, str([A.BY_KEY[k].cat for k in round1]))
    check("asks the first question", A.BY_KEY[round1[0]].ask in r, r)
    replies = []
    for i, k in enumerate(round1):
        if i == 3:
            ok = e.turn("ok")                       # a bare "ok" is not a goodbye mid-round: she nudges once
            check("'ok' mid-round → nudge, not goodbye", not e.ended and "say skip" in ok and e.askme is not None, ok)
            w = e.turn("why?")
            check("'why?' explains and re-asks", A.BY_KEY[k].ask in w and w.count("?") == 1, w)
        if i == 5:
            al = e.turn("set an alarm for 6 am")    # a command mid-round runs; the round waits
            check("command mid-round pauses the round", e.askme is None and A.active(), al)
            back = e.turn("ask me questions")
            check("…and 'ask me questions' picks up the same question", "picking up" in back.lower()
                  and A.BY_KEY[k].ask in back, back)
        replies.append(e.turn(canned(k)))
        check(f"answer {i + 1}: stored as a high-importance episode",
              one("SELECT importance FROM episodes WHERE id=%s", (e.cur_user_ep,))["importance"] == 8)
    nxt = [x for x in replies[:-1]]
    check("each reply: short ack + the next question", all(A.BY_KEY[round1[i + 1]].ask in nxt[i] or
                                                            "Quick check" in nxt[i] for i in range(len(nxt))))
    check("acks reflect his answer", any("Moon Harbor" in x for x in replies) and any("Kenji" in x for x in replies))
    check("progress hint once", sum("Halfway there" in x for x in replies) == 1 and "Last one." in replies[-2])
    check("no LLM call in the whole round", not llm_calls, str(len(llm_calls)))
    end = replies[-1]
    check("round ends with a summary line", "That's the round. Got it — you" in end and e.askme is None, end)
    check("summary reflects what she learned", any(w in end for w in ("Moon Harbor", "Kenji", "robot startup")), end)
    check("normal chat resumes after", e.askme is None and e.spec_block("how was your day") != "flow")
    r = e.turn("Kenji is so cool")
    check("…next line isn't eaten by the round", e.askme is None and "Quick check" not in r, r)

    print("engine: goodbye mid-round")
    e2 = Engine("text")
    e2.turn("ask me something")
    g = e2.turn("bye")
    check("'bye' mid-round → goodbye, round kept for later", e2.ended and e2.askme is None and A.active(), g)
    A.STATE.unlink(missing_ok=True)
finally:
    router.complete, router.stream = orig_c, orig_s

print("storage: the brain learns")
check("favourite-anime-style fact stored", any(current(k) for k in round1 if A.BY_KEY[k].items))
k_items = next(k for k in round1 if A.BY_KEY[k].items and current(k))
f = current(k_items)[0]
check("fact text uses his name + his words", "Kiran" in f["fact_text"] and "Moon Harbor" in f["fact_text"], f["fact_text"])
check("names became entities", bool(one("SELECT 1 FROM entities WHERE name='Moon Harbor'"))
      and bool(one("SELECT 1 FROM entities WHERE name='River Song'")))
check("the fact links the entity (graph)", f["obj_id"] is not None)
k_char = next(k for k in round1 if A.BY_KEY[k].char)
fc = current(k_char)[0]["fact_text"]
check("character fact: name, show, reason", fc == "Kiran likes Kenji (Star Blade) for his courage"
      or "Kenji (Star Blade) for his courage" in fc, fc)
check("character → show link", bool(one("SELECT 1 FROM facts WHERE fact_text='Kenji is a character in Star Blade'")))

print("supersede, never duplicate")
A.store(A.BY_KEY["anime_fav"], "Moon Harbor and Iron Tide")
A.store(A.BY_KEY["anime_fav"], "now it's mostly Sky Lantern")
cur = current("anime_fav")
check("one current answer per question", len(cur) == 1, str([c["fact_text"] for c in cur]))
check("newest answer wins", "Sky Lantern" in cur[0]["fact_text"], cur[0]["fact_text"])
old = q("""SELECT * FROM facts WHERE predicate='about_anime_fav' AND NOT upper_inf(valid) ORDER BY id""")
check("old answers kept in history (closed, not deleted)", len(old) == 2 and old[-1]["invalidated_by"] == cur[0]["id"])
links = q("""SELECT e.name FROM facts f JOIN entities e ON e.id=f.subj_id WHERE f.predicate='in_anime_fav'
             AND upper_inf(f.recorded) AND f.valid @> now()""")
check("old name links end with the old answer", [x["name"] for x in links] == ["Sky Lantern"], str(links))
A.store(A.BY_KEY["talk_never"], "my exams")
A.store(A.BY_KEY["talk_never"], "my weight")
dirs = q("SELECT directive, category FROM user_directives WHERE status='active' AND supersession_key='ask_talk_never'")
check("boundary → one active directive", len(dirs) == 1 and dirs[0]["category"] == "boundary"
      and dirs[0]["directive"] == "Never joke about or bring up: his weight", str(dirs))
A.store(A.BY_KEY["talk_win"], "hype me up")
tw = one("SELECT directive FROM user_directives WHERE status='active' AND supersession_key='ask_talk_win'")
check("talk preference → talk_style directive in his terms", tw and tw["directive"] == "When he shares a win: hype him up",
      str(tw))
said, short = A.store(A.BY_KEY["fear_worry"], "failing my final exams")
fw = current("fear_worry")
check("worries are private (P2)", fw and fw[0]["privacy"] == 2)
check("worries are never echoed back", short == "")

print("the next LLM turn knows it")
prof = one("SELECT content FROM briefing_cache WHERE key='standing_profile'")["content"]
check("standing profile has the new answers", "Sky Lantern" in prof and "Kenji" in prof, prof)
check("standing profile keeps his rules", "Never joke about or bring up: his weight" in prof, prof)
check("standing profile never holds P2 worries", "final exams" not in prof)
user_md = (A.CFG.home / "USER.md").read_text()
check("USER.md shows it (he can read and edit it)", "Sky Lantern" in user_md and "Kenji (Star Blade)" in user_md)

print("round two, skip / pause / resume")
a2 = A.AskMe()
r, on = a2.start()
round2 = list(a2.st["round"])
check("second round: 10 new questions", on and len(round2) == 10 and not set(round2) & set(round1),
      str(set(round2) & set(round1)))
check("second round intro", "new ones" in r, r)
r, fin = a2.answer("skip")
check("skip → next question", not fin and A.BY_KEY[round2[1]].ask in r and "No problem" in r, r)
r, fin = a2.answer("nothing really")
check("'nothing' counts as skip", not fin and A.BY_KEY[round2[2]].ask in r, r)
r, fin = a2.answer("bas")
check("'bas' pauses", fin and "ask me questions" in r, r)
a3 = A.AskMe()
r, on = a3.start()
check("resume at the same question", on and "picking up" in r.lower() and A.BY_KEY[round2[2]].ask in r, r)
for k in round2[2:]:
    r, fin = a3.answer(canned(k))
check("round two finishes", fin and "That's the round" in r, r)
skipped = A._state().get("skipped", {})
check("skipped questions remembered", round2[0] in skipped and round2[1] in skipped)

print("bank exhausted → refresh the oldest answers")
for qn in A.BANK:
    if qn.key not in A.answered() and not qn.sensitive:
        A.store(qn, canned(qn.key))
st = A._state()
keys, refresh = A.pick_round(st)
check("next round re-asks skipped / oldest", len(keys) == 10, str(keys))
a4 = A.AskMe()
check("…the last new ones + quick checks", refresh and len(refresh) < 10 and set(keys) - set(refresh), str(refresh))
from datetime import datetime                                            # noqa: E402
A._save({**A._state(), "skipped": {x.key: datetime.now(A.CFG.tz).isoformat() for x in A.BANK if x.sensitive}})
keys, refresh = A.pick_round(A._state())
check("a skipped worry isn't re-asked for 30 days", not any(A.BY_KEY[k].sensitive for k in keys), str(keys))
a4 = A.AskMe()
r, on = a4.start()
check("refresh round", on and "check what's changed" in r and "Quick check —" in r, r)
k0 = a4.st["round"][0]
r, fin = a4.answer("yes, still")
conf = current(k0)[0]["attrs"]
check("'still the same' confirms it", "confirmed_at" in (conf or {}), str(conf))
k1 = a4.st["round"][1]
before = current(k1)[0]["id"]
r, fin = a4.answer("no, now Glass Garden")
check("a changed answer supersedes", current(k1)[0]["id"] != before
      and "Glass Garden" in current(k1)[0]["fact_text"], current(k1)[0]["fact_text"])
check("refreshed ones go to the back of the queue", k0 not in A._oldest_answers(5, set()))

print(f"\n{passed}/{total} passed")
sys.exit(0 if passed == total else 1)
