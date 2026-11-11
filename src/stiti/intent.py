"""Exemplar intent/mood classifier on the already-loaded embedder (~7 ms, ~0 extra RAM).

Stiti's hot-path "System 1" until Laya fits the M2 (pilot: Laya zero-shot 13-15/30 on domain,
200-500 ms, 2.7-2.9 GB RSS with torch — see docs/DECISIONS.md D10).
Learns without training: owner-confirmed examples append to ~/.stiti/exemplars.jsonl.
"""
from __future__ import annotations

import json
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
             "dad is travelling to Hyderabad tomorrow", "I have a test on Friday", "my roommate got an internship today",
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


def classify(qvec: np.ndarray, kind: str, top: int = 3) -> tuple[str, float, dict[str, float]]:
    labels, vecs = _index()[kind]
    sims = vecs @ qvec
    scores = {}
    for lab in dict.fromkeys(labels):
        s = np.sort(sims[labels == lab])[::-1][:top]
        scores[lab] = float(s.mean())
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    best, second = ranked[0], ranked[1]
    conf = float(1 / (1 + np.exp(-(best[1] - second[1]) * 40)))  # margin -> (0.5, 1)
    return best[0], conf, scores


def learn(kind: str, label: str, text: str) -> None:
    """Owner-confirmed example (e.g. after a correction). Takes effect on next start."""
    with open(CFG.home / "exemplars.jsonl", "a") as f:
        f.write(json.dumps({"kind": kind, "label": label, "text": text}) + "\n")
    _index.cache_clear()
