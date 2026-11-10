"""Turn-completion markers (Pipecat ● ◐ ○, D29): the reply LLM's second opinion on "has he finished?".

Every voice reply starts with exactly one marker. ● = he finished → answer. ◐ = he stopped mid-thought ("I was
talking to my friend about the…") → say NOTHING, keep the fragment and join what he says next; "Mm-hm?" after 5 s.
○ = he needs time ("hold on", "hmm let me see", only a reaction) → stay quiet longer; "Mm-hm?" after 10 s.
Costs ~1 token. A missing or garbled marker counts as ●, so a weak model can never block a reply. Markers are
stripped before anything is spoken, stored, shown on the web or learned from.
"""
from __future__ import annotations

import re

COMPLETE, SHORT, LONG = "●", "◐", "○"
INCOMPLETE = (SHORT, LONG)
REPROMPT_AFTER_S = {SHORT: 5.0, LONG: 10.0}
# what models actually emit for each one (lookalike glyphs); all of them are removed from the text
_ALIASES = {COMPLETE: "●⬤⚫◉", SHORT: "◐◑◒◓", LONG: "○◯⚪"}
_KIND = {ch: m for m, chars in _ALIASES.items() for ch in chars}
_ANY = re.compile("[" + "".join(_KIND) + "]")
# a model may dress it up: "[●]", "**●**", "`◐`", "Marker: ●"
_LEAD = re.compile(r"^\s*(?:marker\s*[:=-]\s*)?[\[(*`'\"]*\s*(?P<m>[" + "".join(_KIND) + r"])\s*[\])*`'\"]*[ \t]*",
                   re.I)
_MAX_LEAD = 16                       # chars to look at before deciding "no marker"

RULES = """[TURN MARKER — first character of EVERY reply, then a space]
● he has finished his thought (a question, a statement, a request — complete, even if short) → ● then your reply.
◐ his words stop mid-sentence (ends on "and", "but", "the", "because", "ki", "aur", an unfinished list or number) →
  reply with ONLY ◐ and nothing else. Don't answer it, don't guess the rest.
○ he asked for time or is still thinking ("hold on", "let me think", "hmm…") → reply with ONLY ○.
If earlier fragments were joined into his message, judge the whole thing. When in doubt, use ●."""


def split(text: str) -> tuple[str | None, str]:
    """(marker or None, text without any marker). The marker is the first one at the very start; stray markers
    anywhere else are removed too (they are never speakable)."""
    t = text or ""
    m = _LEAD.match(t)
    mark = _KIND[m.group("m")] if m else None
    if m:
        t = t[m.end():]
    return mark, _ANY.sub("", t).lstrip() if mark else _ANY.sub("", t)


def strip(text: str) -> str:
    return split(text)[1]


def is_incomplete(mark: str | None) -> bool:
    return mark in INCOMPLETE


class MarkerStream:
    """Strips the marker from a streamed reply whose deltas can split anywhere ("", " ", "●", " Sure", …).

    feed(delta) → text to pass on ("" while the opening is still undecided). `marker` is None until decided, then
    ●/◐/○; a reply without a marker is decided as ● the moment its first real character arrives (or after
    _MAX_LEAD characters of dressing). `incomplete` → stop the LLM and say nothing."""

    def __init__(self):
        self.marker: str | None = None
        self.decided = False
        self._buf = ""
        self._lstrip = False                 # drop the space(s) right after the marker, even in later deltas

    @property
    def incomplete(self) -> bool:
        return self.decided and self.marker in INCOMPLETE

    def feed(self, delta: str) -> str:
        if not delta:
            return ""
        if self.decided:
            return self._out(delta)
        self._buf += delta
        b = self._buf
        m = _LEAD.match(b)
        if m and (m.end() < len(b) or len(b) >= _MAX_LEAD or b[-1].isspace()):
            # the marker and its dressing are complete once anything (even a space) follows them: decided
            self.decided, self.marker, self._lstrip = True, _KIND[m.group("m")], True
            self._buf = ""
            return self._out(b[m.end():])
        s = b.lstrip()
        if not s:
            return ""                                  # only whitespace so far
        if _could_be_lead(s) and len(s) < _MAX_LEAD:
            return ""                                  # "[", "**", "Marker:" … wait for the glyph
        self.decided, self.marker = True, None        # no marker: a normal reply (counts as ●)
        self._buf = ""
        return _ANY.sub("", b)

    def _out(self, text: str) -> str:
        text = _ANY.sub("", text)
        if self._lstrip:
            text = text.lstrip()
            self._lstrip = not text
        return text

    def flush(self) -> str:
        """End of stream: whatever was held back (a reply that was only dressing or only a marker)."""
        if self.decided:
            return ""
        b, self._buf = self._buf, ""
        mark, text = split(b)
        self.decided, self.marker = True, mark
        return text


def _could_be_lead(s: str) -> bool:
    """Could this opening still turn into a dressed marker ("[", "**", "Marker:")?"""
    if _LEAD.match(s):
        return True
    return bool(re.fullmatch(r"[\[(*`'\"]+\s*|m(a(r(k(e(r(\s*[:=-]?\s*[\[(*`'\"]*)?)?)?)?)?)?", s, re.I))
