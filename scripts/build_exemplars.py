#!/usr/bin/env python3
"""Public English examples for Stiti's intent router (D50). Rows are downloaded, never committed.

    python scripts/build_exemplars.py              # download what is missing, then build
    python scripts/build_exemplars.py --fixture    # (maintainer) re-draw tests/fixtures/public_intent.jsonl

Downloads into $STITI_HOME/data/ (default ~/.stiti/data/), about 22 MB kept on disk:
  massive/en-US.jsonl        Amazon MASSIVE 1.1, en-US only           CC BY 4.0
  clinc150/data_full.json    CLINC150 incl. out-of-scope              CC BY 3.0
  presto/en-US_*.jsonl       Google PRESTO, en-US (slimmed lines)     CC BY 4.0
Builds $STITI_HOME/data/public_exemplars.npz from the TRAIN splits only: ~40 varied lines per source intent, mapped
to Stiti's domains, with their vectors (so start-up never embeds thousands of lines). `stiti.intent` picks the file
up on its next start; delete it and the router is exactly what it was. Attributions: docs/THIRD_PARTY_DATA.md.
The files are parsed as data only (json / tarfile member read / zipfile member read) — nothing in them is executed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MASSIVE_URL = "https://amazon-massive-nlu-dataset.s3.amazonaws.com/amazon-massive-dataset-1.1.tar.gz"
CLINC_URL = "https://raw.githubusercontent.com/clinc/oos-eval/master/data/data_full.json"
PRESTO_URL = "https://storage.googleapis.com/gresearch/presto/presto_v1.zip"
PRESTO_TEST = {"en-US_revisions_test.jsonl": "test_partitions/en-US/en-US_revisions/test.jsonl",
               "en-US_no_phenomena_test.jsonl": "test_partitions/en-US/en-US_no_phenomena/test.jsonl",
               "en-US_disfluency_test.jsonl": "test_partitions/en-US/en-US_disfluency/test.jsonl"}
PRESTO_TRAIN_MEMBER, PRESTO_TRAIN_BYTES = "presto_train.jsonl", 60 << 20    # read the first 60 MB (unpacked) of train
UA = {"User-Agent": "stiti-build-exemplars/1.0"}


def data_dir() -> Path:
    d = Path(os.path.expanduser(os.getenv("STITI_HOME", "~/.stiti"))) / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ------------------------------------------------------------------ downloads
class HttpRange:
    """Seekable read-only view of a remote file over HTTP Range requests, so one member of a 400 MB zip can be read
    without downloading the zip."""

    def __init__(self, url: str, ahead: int = 1 << 20):
        self.url, self.pos, self.ahead = url, 0, ahead
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD", headers=UA), timeout=30) as r:
            self.size = int(r.headers["Content-Length"])
        self.buf, self.buf_at = b"", 0

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, off: int, whence: int = 0) -> int:
        self.pos = off if whence == 0 else self.pos + off if whence == 1 else self.size + off
        return self.pos

    def read(self, n: int = -1) -> bytes:
        n = self.size - self.pos if n < 0 else min(n, self.size - self.pos)
        if n <= 0:
            return b""
        if not (self.buf_at <= self.pos and self.pos + n <= self.buf_at + len(self.buf)):
            end = min(self.size, self.pos + max(n, self.ahead)) - 1
            req = urllib.request.Request(self.url, headers={**UA, "Range": f"bytes={self.pos}-{end}"})
            with urllib.request.urlopen(req, timeout=180) as r:
                self.buf, self.buf_at = r.read(), self.pos
        o = self.pos - self.buf_at
        out = self.buf[o:o + n]
        self.pos += len(out)
        return out


def _fetch(url: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    tmp.replace(dest)


def _slim_presto(line: bytes) -> str | None:
    """Keep only what Stiti needs from a PRESTO example (the full line carries contacts, lists and notes)."""
    try:
        r = json.loads(line)
    except ValueError:
        return None
    m = r.get("metadata") or {}
    if m.get("locale") != "en-US":
        return None
    prev = [t.get("user_query", "") for t in (m.get("previous_turns") or [])][-1:]
    return json.dumps({"inputs": r.get("inputs", ""), "targets": (r.get("targets") or "")[:200], "split": m.get("split"),
                       "phenomena": m.get("linguistic_phenomena", ""), "prev_user": prev[0] if prev else "",
                       "id": m.get("example_id")}, ensure_ascii=False)


def download(d: Path, log=print) -> None:
    m = d / "massive" / "en-US.jsonl"
    if not m.exists():
        log("MASSIVE 1.1 (40 MB archive; only en-US.jsonl is kept) …")
        m.parent.mkdir(exist_ok=True)
        tar = d / "massive" / "massive.tar.gz"
        _fetch(MASSIVE_URL, tar)
        with tarfile.open(tar, "r:gz") as tf:
            for member in tf:                           # read ONE member as a stream; nothing is extracted to disk paths
                if member.isfile() and member.name.endswith("/data/en-US.jsonl"):
                    m.write_bytes(tf.extractfile(member).read())
                    break
        tar.unlink()
    c = d / "clinc150" / "data_full.json"
    if not c.exists():
        log("CLINC150 (2.5 MB) …")
        c.parent.mkdir(exist_ok=True)
        _fetch(CLINC_URL, c)
    p = d / "presto"
    want = [n for n in PRESTO_TEST if not (p / n).exists()]
    train = p / "en-US_train_sample.jsonl"
    if want or not train.exists():
        log("PRESTO en-US (read out of the 416 MB zip by byte range; ~25 MB transferred) …")
        p.mkdir(exist_ok=True)
        z = zipfile.ZipFile(HttpRange(PRESTO_URL, ahead=4 << 20))
        for name in want:
            with z.open(PRESTO_TEST[name]) as src, open(p / name, "w") as out:
                for line in src:
                    if (s := _slim_presto(line)):
                        out.write(s + "\n")
        if not train.exists():
            n = 0
            with z.open(PRESTO_TRAIN_MEMBER) as src, open(train, "w") as out:
                for line in src:
                    n += len(line)
                    if (s := _slim_presto(line)):
                        out.write(s + "\n")
                    if n > PRESTO_TRAIN_BYTES:
                        break


# ------------------------------------------------------------------ label maps (source intent → Stiti domain)
# Only intents with a clear home in Stiti's label set are used. Left out on purpose: smart-home (iot_*), volume
# (her voice or the Mac's? `control` vs `tool`), contacts (her memory or a tool?), stock / currency (live info, taken
# by connectors/live.py before the domain matters), recommendations, taxi / takeaway / tickets, banking, travel, cars.
REMIND_RX = re.compile(r"\b(remind|reminder|reminders|notify|notification|notifications|alert)\b", re.I)
MASSIVE_MAP = {
    "alarm_set": "time", "alarm_query": "time", "alarm_remove": "time",
    "lists_createoradd": "todo", "lists_query": "todo", "lists_remove": "todo",
    "calendar_set": "tool", "calendar_query": "tool", "calendar_remove": "tool",     # → `time` when it asks for a reminder
    "weather_query": "tool", "news_query": "tool", "email_query": "tool", "email_sendemail": "tool",
    "play_music": "tool", "play_radio": "tool", "play_podcasts": "tool", "play_audiobook": "tool",
    "music_settings": "tool",
    "general_quirky": "chat", "general_greet": "chat", "general_joke": "chat", "qa_factoid": "chat",
    "qa_definition": "chat", "qa_maths": "chat", "cooking_recipe": "chat", "datetime_query": "chat",
    "datetime_convert": "chat",
}
CLINC_MAP = {
    "alarm": "time", "reminder": "time", "reminder_update": "time", "timer": "time",
    "todo_list": "todo", "todo_list_update": "todo", "shopping_list": "todo", "shopping_list_update": "todo",
    "calendar": "tool", "calendar_update": "tool", "meeting_schedule": "tool", "schedule_meeting": "tool",
    "weather": "tool", "play_music": "tool", "next_song": "tool", "text": "tool", "make_call": "tool",
    "greeting": "chat", "how_old_are_you": "chat", "what_is_your_name": "chat", "tell_joke": "chat",
    "fun_fact": "chat", "meaning_of_life": "chat", "who_made_you": "chat", "are_you_a_bot": "chat",
    "what_are_your_hobbies": "chat", "do_you_have_pets": "chat", "where_are_you_from": "chat",
    "who_do_you_work_for": "chat", "what_can_i_ask_you": "chat", "thank_you": "chat", "definition": "chat",
    "calculator": "chat", "spelling": "chat", "recipe": "chat", "translate": "chat",
    "measurement_conversion": "chat", "timezone": "chat", "date": "chat", "time": "chat", "next_holiday": "chat",
    "flip_coin": "chat", "roll_dice": "chat",
    "oos": "chat",                      # out-of-scope questions: for Stiti that is "just talk / ask the LLM", never a command
    "cancel": "control", "repeat": "control",
    "user_name": "memory",
}
PRESTO_MAP = {"Add_item_to_list": "todo", "Create_list": "todo", "Get_list": "todo",
              "Send_digital_object": "tool", "Initiate_call": "tool", "Get_message_content": "tool",
              "Post_message": "tool", "Cancel": "control"}
ONE_WORD_OK = {"control"}
# CLINC's out-of-scope lines are "none of the commands". For Stiti that means: never an alarm / to-do / control /
# feedback fast path. Whether the talk then needs the web (`tool`) or his memory is not what these lines test.
ALSO_OK = {"clinc150:oos": ["tool", "memory"]}

# How many TEST lines of each source intent go into the committed yardstick (tests/fixtures/public_intent.jsonl).
FIXTURE_MASSIVE = {
    "alarm_set": 16, "alarm_query": 10, "alarm_remove": 10, "calendar_set+remind": 18, "calendar_set": 12,
    "calendar_query": 12, "calendar_remove": 8, "lists_createoradd": 14, "lists_query": 12, "lists_remove": 12,
    "weather_query": 14, "news_query": 12, "email_query": 10, "email_sendemail": 10, "play_music": 12,
    "play_radio": 6, "play_podcasts": 5, "play_audiobook": 4, "general_quirky": 20, "general_joke": 5,
    "qa_factoid": 18, "qa_definition": 7, "qa_maths": 6, "cooking_recipe": 7, "datetime_query": 12}
FIXTURE_CLINC = {
    "alarm": 8, "reminder": 7, "reminder_update": 8, "timer": 9, "todo_list": 7, "todo_list_update": 8,
    "shopping_list": 5, "shopping_list_update": 6, "calendar": 6, "calendar_update": 6, "meeting_schedule": 4,
    "weather": 6, "play_music": 5, "text": 5, "greeting": 4, "tell_joke": 3, "fun_fact": 3, "what_is_your_name": 3,
    "are_you_a_bot": 3, "meaning_of_life": 3, "thank_you": 3, "definition": 4, "calculator": 4, "date": 4, "time": 4,
    "translate": 3, "recipe": 3, "cancel": 7, "repeat": 7, "user_name": 4, "oos": 45}
FIXTURE_PRESTO = [   # (file, phenomenon, target intents, how many)
    ("en-US_revisions_test", "cancel-action", ("Cancel",), 12),
    ("en-US_revisions_test", "within-turn-correction", ("Add_item_to_list", "Create_list", "Get_list"), 12),
    ("en-US_revisions_test", "within-turn-correction", ("Send_digital_object", "Initiate_call", "Get_message_content", "Post_message"), 12),
    ("en-US_no_phenomena_test", "", ("Add_item_to_list", "Create_list", "Get_list"), 12),
    ("en-US_disfluency_test", "disfluency", ("Add_item_to_list",), 6),
    ("en-US_disfluency_test", "disfluency", ("Send_digital_object", "Post_message", "Get_message_content"), 6)]
FIXTURE_REVISIONS = [("correct-argument", 14), ("correct-action", 14)]     # "no, I meant …" right after a request
# Test lines whose published label is plainly wrong or means something else in Stiti; found by reading the drawn
# fixture once. They are skipped when the fixture is drawn (normalised text).
BAD_GOLD: set[str] = {x for x in (
    "remind me what i am doing on sunday afternoon",
    "please add my pay days",
    "mark today as the start of my diet",
    "give me an update on the election in one hour",
    "on monday the twentieth i need to have a conversation with greg about our weekend trip",
    "the event will include walter and gemma",
    "set lunch every day at twelve thirty",
    "give me to do list",
    "can you give me the movie schedule",
    "my party planning",
    "can you check the facts on this issue",
    "what is the plan today",
    "search the item",
    "make a list about selena gomez concert schedule",
    "add business contacts to contact list",
    "i want sweet potato pie from a local bakery",
    "create a playlist",
    "add paav bhaji in menu card",
    "how many lists do i have in contacts",
    "give me the details on purchase order",
    "recite the schedules of the list",
    "what else is missing in the diary",
    "if there is event of show then remove it",
    "i mostly pay attention",
    "hot topic",
    "will trump visit russia anytime soon",
    "set environmental news notification",
    "this new email should be added to my contact",
    "nobody knows",
    "put on",
    "next button",
    "check celebrity where abouts",
    "can you give me the details of upcoming annual function on twenty sixth march",
    "best paid jobs in digital marketing in my area",
    "is there a groomer in town for cats only",
    "hey what has been happening interesting in sports lately",
    "google what are the basic things humans need",
    "searching information online",
    "who is celebrity",
    "it must be taste",
    "cook me some oats",
    "find a recipe for dinner tonight",
    "find me a chocolate cake recipe",
    "can you tell me the to do's on my reminder list",
    "who set up the numbers for it",
    "what will tomorrow be on the calendar",
    "can you find me a brisket recipe",
    "find me a recipe for chili",
    "delete note",
    "stop note",
    "a few good men",
    "my fitness list",
    "fix alarm",
    "search my calendar for my next event and notify me before it occurs",
    "let me know when the meeting is gonna happen",
    "meet with joe tomorrow at three",
    "where is the venue in which the marriage of tom is going to take place",
    "is this program is scheduled",
    "do i need to do anything today",
    "set list",
    "add bob to my list of contacts",
    "i have my clothes list",
    "what groups are listed in my contacts",
    "if any new news comes out about the flood can you let me know right away",
    "i want to know about the brexit",
    "tell me about the new foreign policy of trump",
    "here s the truth about meals on wheels in someone s budget",
    "search nandy",
    "go backward thirty seconds",
    "latest movies in theaters",
    "biography of person",
    "please look in to the matter",
    "what time are the hockey games tonight",
    "who won the presidential election this year",
    "show me recipes",
    "show me the best recipe for spaghetti",
    "search to find current local time and time zone",
    "do laundry",
    "a tent 2 canteens and bug spray",
    "what is the top searches in google today",
)}


# Our own counterweights (original lines, not from any dataset), stored next to the public rows and treated as HIS
# examples (they get the owner bonus and also vote on plain statements). Public calendar / call / alarm requests sit
# close to two kinds of sentence that are not requests to a tool: a question about a fact of his life (her memory
# answers it, not the calendar) and a statement that only mentions an alarm, a list, a mail or the weather.
GUARD_EX = {
    "memory": [
        "when is my mom's birthday", "when is my sister's anniversary", "where does my brother live",
        "what is my cousin's name", "which company does my dad work for", "how old is my sister",
        "what did i tell you about my roommate", "do you remember my manager's name", "who is priya",
        "what is my friend's favourite movie", "when did i start my internship", "what did my doctor tell me last time"],
    "chat": [
        "my friend called me late last night", "i have a class at nine tomorrow",
        "my boss shifted the deadline to next week", "my cousin is arriving on monday",
        "i emailed my professor this morning", "the weather was terrible on our trip",
        "we listened to music all night", "my alarm did not ring this morning", "i forgot to set my alarm last night",
        "i woke up late today", "i slept through my alarm again", "my to-do list keeps growing these days",
        "i wrote a long list of ideas yesterday", "the timer on my oven stopped working",
        "i already finished everything for today", "my friend texted me about the party",
        "my manager scheduled a review for friday", "we have a family function next sunday",
        "my brother's flight got delayed", "i read the news about the layoffs this morning",
        "my calendar was packed last week", "i had three meetings back to back today",
        "my phone's reminder app annoyed me all day", "the meeting with my guide went well"],
}


def clean(t: str) -> str:
    """Light tidy-up of a public line: the SLURP wake word and the spelt-out 'a. m.' / 'p. m.' go."""
    t = re.sub(r"\b(?:hey |ok |okay |hi |hello )?olly\b[,]?\s*", "", t, flags=re.I)
    t = re.sub(r"\b([ap])\. ?m\.?(?=\s|$)", r"\1m", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip()


def norm(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", t.lower())).strip()


def _ok(t: str, label: str) -> bool:
    n = len(t.split())
    return (1 if label in ONE_WORD_OK else 2) <= n <= 22 and t.isascii()


def _presto_intent(targets: str) -> str:
    m = re.match(r"\w+", targets or "")
    return m.group(0) if m else ""


def read_sources(d: Path, split: str) -> list[tuple[str, str, str]]:
    """(text, Stiti domain, source tag) for one split ('train' or 'test') of every source."""
    out: list[tuple[str, str, str]] = []
    for line in open(d / "massive" / "en-US.jsonl", encoding="utf-8"):
        r = json.loads(line)
        lab = MASSIVE_MAP.get(r["intent"])
        if lab is None or r["partition"] != split:
            continue
        t, tag = clean(r["utt"]), r["intent"]
        if r["intent"].startswith("calendar_") and REMIND_RX.search(t):
            lab, tag = "time", r["intent"] + "+remind"
        out.append((t, lab, "massive:" + tag))
    cl = json.load(open(d / "clinc150" / "data_full.json", encoding="utf-8"))
    for key in (split, "oos_" + split):
        for t, intent in cl[key]:
            if intent in CLINC_MAP:
                out.append((clean(t), CLINC_MAP[intent], "clinc150:" + intent))
    files = ["en-US_train_sample"] if split == "train" else sorted({f for f, *_ in FIXTURE_PRESTO})
    for f in files:
        for line in open(d / "presto" / f"{f}.jsonl", encoding="utf-8"):
            r = json.loads(line)
            intent = _presto_intent(r["targets"])
            if r["split"] != split or intent not in PRESTO_MAP or r["phenomena"] == "code-mixing" \
                    or (intent != "Cancel" and len(r["inputs"].split()) < 4):
                continue
            out.append((clean(r["inputs"]), PRESTO_MAP[intent], f"presto:{intent}" + (f"+{r['phenomena']}" if r["phenomena"] else "")))
    return [(t, lab, src) for t, lab, src in out if _ok(t, lab)]


def varied(lines: list[str], k: int, seed: int) -> list[str]:
    """k lines that are typical but not near-copies of each other: walk the lines in a fixed pseudo-random order
    (a hash of each line, so dropping one line never reshuffles the rest), skip a line that shares most of its words
    with one already taken; loosen the bar if that leaves too few."""
    uniq = {norm(l): l for l in sorted(lines)}
    order = sorted(uniq, key=lambda n: hashlib.sha1(f"{seed}:{n}".encode()).hexdigest())
    toks = [set(n.split()) for n in order]
    chosen: list[int] = []
    for bar in (0.5, 0.7, 0.9, 1.01):
        for i, tk in enumerate(toks):
            if len(chosen) >= k:
                break
            if i in chosen:
                continue
            if all(len(tk & toks[j]) / max(1, len(tk | toks[j])) < bar for j in chosen):
                chosen.append(i)
    return [uniq[order[i]] for i in chosen[:k]]


def fixture_path() -> Path:
    return REPO / "tests" / "fixtures" / "public_intent.jsonl"


def fixture_texts() -> set[str]:
    p = fixture_path()
    return {norm(json.loads(l)["text"]) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()} if p.exists() else set()


# ------------------------------------------------------------------ the committed yardstick (TEST splits)
def draw_fixture(d: Path, seed: int = 7) -> list[dict]:
    test = [x for x in read_sources(d, "test") if norm(x[0]) not in BAD_GOLD]
    by: dict[str, list[tuple[str, str]]] = {}
    for t, lab, src in test:
        by.setdefault(src, []).append((t, lab))
    rows: list[dict] = []
    seen: set[str] = set()

    def take(src: str, n: int) -> None:
        cand = {t: lab for t, lab in by.get(src, []) if norm(t) not in seen}
        for t in varied(list(cand), n, seed):
            seen.add(norm(t))
            rows.append({"text": t, "gold": cand[t], "src": src, **({"also": ALSO_OK[src]} if src in ALSO_OK else {})})

    for intent, n in FIXTURE_MASSIVE.items():
        take("massive:" + intent, n)
    for intent, n in FIXTURE_CLINC.items():
        take("clinc150:" + intent, n)
    for f, ph, intents, n in FIXTURE_PRESTO:
        pool: dict[str, tuple[str, str]] = {}
        for line in open(d / "presto" / f"{f}.jsonl", encoding="utf-8"):
            r = json.loads(line)
            intent, t = _presto_intent(r["targets"]), clean(r["inputs"])
            if r["phenomena"] == ph and intent in intents and _ok(t, PRESTO_MAP[intent]) and norm(t) not in seen | BAD_GOLD \
                    and (intent == "Cancel" or len(t.split()) >= 4):       # "Nail polish" answers her question; not a request
                pool[t] = (PRESTO_MAP[intent], f"presto:{intent}" + (f"+{ph}" if ph else ""))
        for t in varied(list(pool), n, seed):
            seen.add(norm(t))
            rows.append({"text": t, "gold": pool[t][0], "src": pool[t][1]})
    for ph, n in FIXTURE_REVISIONS:      # judged on "did she notice he is correcting the last request", not on the domain
        pool2: dict[str, str] = {}
        for line in open(d / "presto" / "en-US_revisions_test.jsonl", encoding="utf-8"):
            r = json.loads(line)
            t = clean(r["inputs"])
            if r["phenomena"] == ph and r["prev_user"] and 2 <= len(t.split()) <= 22 and t.isascii() \
                    and norm(t) not in seen | BAD_GOLD:
                pool2[t] = clean(r["prev_user"])
        for t in varied(list(pool2), n, seed):
            seen.add(norm(t))
            rows.append({"text": t, "prev": pool2[t], "revision": True, "src": "presto:" + ph})
    return rows


# ------------------------------------------------------------------ the public example set (TRAIN splits)
def select_train(d: Path, per_intent: int = 40, seed: int = 11) -> list[tuple[str, str, str]]:
    held_out = fixture_texts()
    by: dict[str, dict[str, str]] = {}
    for t, lab, src in read_sources(d, "train"):
        if norm(t) in held_out:                  # the same words also sit in a TEST line of the yardstick: never use
            continue
        by.setdefault(src.split("+")[0] if src.startswith("presto:") else src, {})[t] = lab
    rows: list[tuple[str, str, str]] = []
    for src in sorted(by):
        k = 100 if src == "clinc150:oos" else per_intent
        rows += [(t, by[src][t], src) for t in varied(list(by[src]), k, seed)]
    return rows


def build(d: Path, per_intent: int = 40, log=print) -> Path:
    import numpy as np

    sys.path.insert(0, str(REPO / "src"))
    from stiti import embed

    rows = select_train(d, per_intent)
    n_public = len(rows)
    rows += [(t, lab, "stiti:guard") for lab, lines in GUARD_EX.items() for t in lines]
    t0 = time.perf_counter()
    vecs = []
    for i in range(0, len(rows), 32):
        vecs += [v.to_numpy() for v in embed.embed_docs([t for t, _, _ in rows[i:i + 32]])]
    out = d / "public_exemplars.npz"
    tmp = d / "public_exemplars.tmp.npz"
    np.savez_compressed(tmp, vecs=np.stack(vecs).astype(np.float16), labels=np.array([lab for _, lab, _ in rows]),
                        texts=np.array([t for t, _, _ in rows]), sources=np.array([s for _, _, s in rows]),
                        owner=np.array([s.startswith("stiti:") for _, _, s in rows]), model=np.array(embed.EMBED_MODEL))
    tmp.replace(out)
    counts: dict[str, int] = {}
    for _, lab, _ in rows:
        counts[lab] = counts.get(lab, 0) + 1
    log(f"{n_public} public examples from {len({s for _, _, s in rows}) - 1} source intents (+ {len(rows) - n_public} of our own "
        f"counterweights) → {out} "
        f"({out.stat().st_size / 1e6:.1f} MB, embedded in {time.perf_counter() - t0:.0f} s): "
        + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--fixture", action="store_true", help="re-draw tests/fixtures/public_intent.jsonl from the TEST splits")
    ap.add_argument("--no-download", action="store_true", help="use what is already in $STITI_HOME/data")
    ap.add_argument("--per-intent", type=int, default=40)
    a = ap.parse_args()
    d = data_dir()
    if not a.no_download:
        download(d)
    if a.fixture:
        rows = draw_fixture(d)
        fixture_path().write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        print(f"{len(rows)} yardstick lines → {fixture_path()}")
        return
    build(d, a.per_intent)


if __name__ == "__main__":
    main()
