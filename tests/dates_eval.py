"""Hinglish/English time parsing checks (no DB, no network): uv run python tests/dates_eval.py"""
import sys
from datetime import datetime

from stiti.config import CFG
from stiti.fastpath.dates import parse_when

EVENING = datetime(2026, 11, 10, 21, 45, tzinfo=CFG.tz)   # Tue 9:45 PM
LATE = datetime(2026, 11, 10, 1, 15, tzinfo=CFG.tz)       # Tue 1:15 AM (hasn't slept yet)

CASES = [
    (EVENING, "set alarm for 6 am", "Wed 06:00"),
    (EVENING, "kal subah 6 baje uthana", "Wed 06:00"),
    (EVENING, "remind me at 7 pm to call mummy", "Wed 19:00"),
    (EVENING, "shaam 7 baje yaad dilana", "Wed 19:00"),
    (EVENING, "10 minute ka timer", "Tue 21:55"),
    (EVENING, "remind me in 2 hours", "Tue 23:45"),
    (EVENING, "parso 9 baje meeting", "Thu 09:00"),
    (EVENING, "raat 11 baje", "Tue 23:00"),
    (EVENING, "raat 12 baje", "Wed 00:00"),
    (EVENING, "alarm 5:30 am", "Wed 05:30"),
    (EVENING, "friday ko yaad dilana", "Fri 09:00"),
    (EVENING, "dopahar 2 baje", "Wed 14:00"),
    (EVENING, "set alarm 6", None),                 # ambiguous -> Stiti asks "morning or evening?"
    (LATE, "kal 9 baje yaad dilana", "Tue 09:00"),  # 1 AM "kal" = later today
    (LATE, "remind me tomorrow at 9", "Wed 09:00"),
]

fails = 0
for ref, text, want in CASES:
    got = parse_when(text, ref)
    got_s = got.strftime("%a %H:%M") if got else None
    ok = got_s == want
    fails += not ok
    print(("OK  " if ok else "FAIL"), f"{text!r:36} -> {got_s} (want {want})")
print(f"\n{len(CASES) - fails}/{len(CASES)} passed")
sys.exit(1 if fails else 0)
