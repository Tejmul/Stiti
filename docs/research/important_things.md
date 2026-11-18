# Important things: notice, ask once, book it

Research for D49. 2026-11-18.

## 1. What he asked for

"If it reads my mail, it should ask me: is it important? If it is, save it on the calendar and remind me before.
Not just mail — whatever it gets or sees. If my exams are on the 9th and I say remind me on the 1st, it should book
my reminders and everything before."

So three steps: **notice** a dated thing that matters, **ask** one short question, **follow through** (calendar
entry, reminders ahead, an offer to plan the preparation). Never save silently, never claim a save that didn't happen.

Where Stiti is today: `fastpath/dates.py` parses clock times and "kal / parso / Friday" but not "the 9th" or
"18 November". "My exams are on the 9th, give me a reminder on the 1st" gets "Morning or evening?". Mail is read
as headers only, and nothing reads it unless he asks.

## 2. Sources (all fetched and read unless marked)

| # | Source | Mechanism | Strengths | Weaknesses | Fits free + local + 8 GB + no local LLM? |
|---|---|---|---|---|---|
| 1 | Google Calendar "events from Gmail" ([help](https://support.google.com/calendar/answer/6084018)) + schema.org email markup ([docs](https://developers.google.com/workspace/gmail/markup/overview), [EventReservation](https://developers.google.com/workspace/gmail/markup/reference/event-reservation)) | Senders embed JSON-LD (flight, hotel, restaurant, ticket). Events "may be automatically added", no question asked | Deterministic, no ML | Bulk senders only. Nothing for "exam on the 9th". Adds silently — the thing he does not want | Mechanism yes, but it covers almost none of his cases |
| 2 | Apple data detectors ([NSDataDetector](https://developer.apple.com/documentation/foundation/nsdatadetector)) + Siri suggestions in Mail / Calendar ([Mail](https://support.apple.com/guide/mail/use-information-found-in-mail-in-other-apps-mlhleed80167/15.0/mac/12.0), [Calendar](https://support.apple.com/guide/calendar/iclc121e66ee/mac)) | Pattern matcher for dates; it "discards potential matches in case of uncertainty". Mail shows a suggestion, he clicks Add or Ignore | On-device. Suggest, then confirm | Finds any date, no judgement of what matters. Hinglish not stated | **Yes — this is the shape to copy** |
| 3 | Gemini in Gmail "Add to calendar" ([Workspace Updates, Mar 2025](https://workspaceupdates.googleblog.com/2025/03/add-events-to-google-calendar-using-gemini-in-gmail.html)) | LLM spots calendar content, shows a button, he confirms. Not shown for events already extracted | One tap. Skips what is already on the calendar | Cloud LLM reads the mail, paid tier | No (mail must not go to a cloud model), but copy "confirm" and "skip what's already there" |
| 4 | Superhuman AI ([blog, Feb 2025](https://blog.superhuman.com/the-next-superhuman-ai/)) | Classifies every mail (needs reply, waiting on, meeting, marketing); auto-reminders for mail that needs a reply | Classify, then remind | Paid cloud LLM; event detection not stated. Help pages returned 403, so only the blog was read. Shortwave and Fyxer were not verified | No |
| 5 | Reclaim ([help](https://help.reclaim.ai/en/articles/6207587-how-reclaim-manages-your-schedule-automatically)) and Motion ([help](https://www.usemotion.com/help/time-management/auto-scheduling/reference-auto-scheduling/what-auto-scheduling-considers)) | Greedy scheduler: priority, then soonest due date, duration, working hours; re-plans when a task is at risk | No LLM needed | Paid. Neither documents planning backward from the deadline | Idea yes — Stiti's CP-SAT planner already takes `due` |
| 6 | Lampert, Dale, Paris 2010, requests in email ([NAACL](https://aclanthology.org/N10-1142/)) | SVM, but first cuts the mail into zones (drops quoted replies, signatures) | Zoning alone lifts accuracy 72% → 84% | English, no dates | Zoning idea yes (subject + first lines only) |
| 7 | Corston-Oliver et al. 2004, SmartMail ([ACL](https://aclanthology.org/W04-1008/)) | Per-sentence classifier; task sentences are offered for the to-do list | Suggest-then-add. Word n-grams do nearly as well as deep features | Needs labelled data | Design yes |
| 8 | Kalia et al. 2013, commitments ([pdf](https://www.csc2.ncsu.edu/faculty/mpsingh/papers/societal/SCC-13-people.pdf)) | Modal verbs, action verbs, "please + verb", tense, negation → classifier. F 0.90 on Enron mail, 0.80 on chat | The features are regex-level | Business mail only. (The HP Labs report first looked for was not found; this is the same group's paper) | **Yes — tense and negation as rules** |
| 9 | Azarbonyad, Sim, White 2019, commitments for Cortana ([MSR](https://www.microsoft.com/en-us/research/publication/domain-adaptation-for-commitment-detection-in-email/); [Cortana post](https://blogs.windows.com/windowsexperience/2017/02/09/cortana-reminds-important-stuff-even-forget-ask/)) | Logistic regression on n-grams, F1 0.78–0.81; drops to 0.73 on a new domain. Cortana saved a "suggested reminder" | Tiny model | Breaks when the domain shifts — and his speech is not Enron | Lesson: keep a human yes in the loop |
| 10 | Purver et al. 2007, action items in meetings ([SIGdial](https://aclanthology.org/2007.sigdial-1.4/)); Liu et al. 2023 ([arXiv](https://arxiv.org/abs/2303.16763)) | Split the job into task / timeframe / owner / agreement | Good decomposition (what, when, whose) | Speech is hard: F1 0.45; 2023 BERT only ~0.43 on AMI | Lesson: on speech, never act without asking |
| 11 | Duckling ([GitHub](https://github.com/facebook/duckling)) | Rule-based time parser (regex + productions), Haskell server | Mature for English | **No Hindi time rules** (Hindi has numbers and durations only). Extra process, Haskell build | No |
| 12 | dateparser ([docs](https://dateparser.readthedocs.io/en/latest/), [issue 582](https://github.com/scrapinghub/dateparser/issues/582)) | 200+ locales incl. Hindi; `search_dates` scans running text | Pure Python | Its own docs: date search "is limited". Reads "100M" and "73 20" as dates | No — false dates would become false questions |
| 13 | HeidelTime ([SemEval 2010](https://aclanthology.org/S10-1071/)), SUTime ([LREC 2012](https://aclanthology.org/L12-1122/)) | Hand-written rules. F1 0.86 and 0.92 on TempEval | Proof that rules are enough for dates | Java, English; no Hinglish | Approach yes, code no |
| 14 | Lu et al. 2024, Proactive Agent / ProactiveBench ([arXiv 2410.12361](https://arxiv.org/abs/2410.12361)) | LLM watches activity and proposes a task "or nothing" | Measures the cost | Best F1 66%; **about half of all proposals are false alarms**, GPT-4o included | No. Strongest argument for rules + a cap |
| 15 | Horvitz 1999, mixed-initiative interfaces / LookOut ([CHI](https://erichorvitz.com/chi99horvitz.pdf)) | From a mail, estimate the chance he wants scheduling; below one threshold do nothing, above it ask, far above it act. A question that gets no answer times out | The exact blueprint for "ask once" | Thresholds are set by hand | **Yes** |
| 16 | Mark et al. 2008 ([CHI](https://ics.uci.edu/~gmark/chi08-mark.pdf)); Okoshi et al. 2015, Attelia ([PerCom](https://julian-ramos.github.io/papers/Okoshi2015.pdf)); Pielot et al. 2014 ([MobileHCI](https://pielot.org/pubs/Pielot2014-MobileHCI-Notifications.pdf)) | Interrupted work is finished faster but with more stress. Notifying at breakpoints cut load 33–46%. People get ~64 notifications a day; more means worse mood | Hard numbers for "when" and "how many" | Phones, not voice | Yes — already Stiti's nudge gate (`research_notes/…/productivity_and_psychology.md` §nudges: 3–5 a day, breakpoints only) |
| 17 | Cepeda et al. 2008 ([doi](https://doi.org/10.1111/j.1467-9280.2008.02209.x)); Dunlosky et al. 2013 ([doi](https://doi.org/10.1177/1529100612453266)); Park, Lu, Hedgcock 2017 ([doi](https://doi.org/10.1177/0956797617715510)) | Best gap between study sessions is 20–40% of a one-week delay, less for longer delays. Practice tests and spread-out practice are the two high-value techniques. Planning backward from the goal raised motivation and results | Says when to start and how to spread it | Lab studies (abstracts read, not full papers) | Yes — as defaults |

## 3. What the good ones share

1. **Suggest, then confirm** (2, 3, 7, 9, 15). Only machine-readable reservations are added silently (1), and that is
   the one behaviour he ruled out.
2. **Rules are enough for dates** (11–13), and learned detectors break on new domains and on speech (9, 10). Nobody
   ships Hinglish time rules, so `dates.py` has to grow its own.
3. **Cheap features decide "does this matter"**: an event word, a date, tense, negation (6, 8).
4. **Proactive LLMs are wrong half the time** (14), so the brain decides and a daily cap applies (15, 16).
5. **Skip what is already booked** (3).
6. **Prep plans run backward from the date** (17).

## 4. `dates.py` today vs what is needed

| Says | `parse_when` today | Needed |
|---|---|---|
| "kal 6 baje", "Friday at 4", "in 10 minutes" | ✓ | keep |
| "the 9th", "9th December", "18 November", "December 9", "9 tarikh", "9/12" | ✗ | a calendar-day parser |
| "by Friday", "next Monday", "in 3 days", "3 din baad", "this weekend" | partly | same parser |
| "two days before", "a week before", "the day before", "ek din pehle" | ✗ | offsets from the event |

## 5. The smallest design that fits

**Notice — local rules, no LLM on the hot path.** An item = an event word (exam, test, interview, deadline,
submission, meeting, appointment, flight, birthday, fee, result…, English + Hinglish) **and** a date that resolves to
today or later. Rejected: questions, past tense ("was", "tha", "ho gaya"), negation and "if", cancelled, other
people's things (except birthdays), anything already on the calendar or already a reminder, and anything asked
before (one hash per thing). Reminder / alarm / to-do commands keep their fast paths. The same detector runs on his
words, on mail (sender + subject + first lines; sale / newsletter mail dropped) and on documents he ingests.
A background cloud call may add what the rules miss, only for his own non-private words, and its finds are only
ever *asked about*.

**Ask — Horvitz's three zones.** Confidence below 0.7: nothing. Above: one question. Never act alone, except when
he gave the instruction himself in the same sentence. His own words are asked about in the same turn if the
sentence is short and he isn't upset; otherwise, and for mail and documents, the question goes through the existing
proactive gate (present, not in a call, not quiet hours, not mid-conversation, inside the daily budget, at most two
a day, 30 minutes apart). Asked once; then it waits in a "noticed" list he can ask for.

**Follow through — by kind, read back exactly.** Calendar entry, then reminders: exam = a week before, the day
before, that morning; deadline / fee = two days before and the day before; meeting / appointment / interview = the
evening before and an hour before; travel = the day before and three hours before; birthday / result = that
morning. His own words replace the defaults. Exams, deadlines and interviews get one follow-up: a preparation plan
and when to start; the answer books a start reminder and a task with the due date (so the day planner plans
backward from it), or opens the existing step-by-step chunker.

**State — Postgres `noticed`.** The open question lives in the row, not in the process, so it survives a restart.

**Honesty and safety.** The read-back is built from what the writes returned. Mail and document text is matched
by patterns only: it is never sent to an LLM, never obeyed, and never causes a write without his yes.

**Cost.** Regex + two small queries per turn (about 1 ms). No model, no RAM, no network for the decision.

## 6. Not chosen

- Auto-adding like Gmail: he asked to be asked.
- dateparser / Duckling: false dates, no Hinglish time rules, a new dependency or a Haskell server.
- An LLM reading mail to judge importance: half false alarms (14), and mail must stay on the Mac.
- A learned "important to him" classifier: nothing to train on yet. `noticed.status` (accepted / declined) is the
  label set for a future Laya head.
