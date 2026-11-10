# Research: alarms, reminders, timers: AM/PM, recurrence, ringing, snooze, missed alarms, delivery

Date: 2026-11-10. Scope: redesign of the fast-path alarm/reminder/timer flow. The current flow parses locally in `fastpath/dates.py`
with no LLM, stores rows in `intents`, mirrors them to Apple Reminders through `connectors/eventkit.py`, and fires them from a 5 s scheduler loop.
Goals: correct AM/PM defaults, recurring alarms, a real ring that can be dismissed or snoozed by voice, a missed-alarm policy, editing and
cancelling by voice, and reminders that reach Tejmul when he is present or away.

## 1. Sources compared

| # | Source | Mechanism / convention | What Stiti copies |
|---|---|---|---|
| 1 | Amazon AVS **Alerts** interface [1][2] | Alerts carry a loop count. With no duration given, an alert sounds for **1 h** unless stopped. On reconnect, alerts **≤30 min** overdue still fire; older ones are **discarded** with an `AlertStopped` event. Alerts drop to the "background" (quieter) while the user talks. | A hard missed-alarm cutoff. Duck the ring while he speaks. Log every discarded alert. |
| 2 | Amazon Echo help: snooze; missed reminders [3][4] | Default snooze is **9 min**. Missed reminders show a yellow light and are read out on "What are my reminders?". Missed ones are not replayed automatically. | Snooze default 9. Missed items go to a "missed" list he can ask about. Never auto-replay stale ones. |
| 3 | Alexa Reminders usage guidelines [5] | "Restate the time and nature of the reminder". Plain-language recurrence ("Every weekday at 7 AM"). Say so if creation fails. Make a **new** reminder rather than editing an expired one. | Readback template. A failed save is spoken. A recurring item is one row; each fire creates an occurrence row. |
| 4 | Google Assistant / Nest alarms help [6][7] | "Stop" works **without the hotword** while ringing (on-device, small grammar). "Snooze for 5 minutes". Default snooze **10 min**. "Cancel my 7am alarm". "Every day of the week" repeats. | Wake-word-free stop/snooze grammar while ringing. Pick an alarm by its time. |
| 5 | Google Clock: "Silence after" + "Gradually increase volume" [8] | Rings for **10 min** by default (user reports), then silences. Optional rising volume. | 10-min ring cap. Rising volume. |
| 6 | Apple Clock iOS 26 (custom snooze) [9] | Snooze is user-set from **1 to 15 min**. Default is still **9**. | Clamp a spoken snooze length to 1–30 min (voice gives wider latitude). |
| 7 | Apple **AlarmKit** (WWDC25 #230) [10] | Alarms break through Silent/Focus and need permission. *Fixed* (absolute) vs *Relative* (wall-clock, follows time zone, weekly recurrence) schedules. Stop button plus an optional snooze/secondary button. Countdown pre/post-alert. | Store recurring alarms as wall-clock + TZ, not epoch. Model countdown (timer) separately from alarm. |
| 8 | Android AlarmManager guide [11] | `setAlarmClock()` is the most critical kind: never deferred, wakes the device. **All alarms are cleared on shutdown**, so re-arm them on `BOOT_COMPLETED`. Inexact windows ≥10 min. | On every app start: rebuild the schedule from Postgres, then run a catch-up pass with the grace windows. |
| 9 | RFC 5545 §3.3.10 RRULE + python-dateutil `rrule`/`rrulestr` [12][13] | `FREQ`, `INTERVAL`, `BYDAY`, `BYMONTHDAY`, `COUNT`/`UNTIL` (never both), plus `EXDATE` for skips. dateutil expands rules (`after(now)`). | Store `rrule TEXT` + `dtstart` + `tzid`. The next fire time = `rrulestr(...).after(now)`. Skip one occurrence = EXDATE. |
| 10 | **Duckling** (Meta) time dimension [14][15] | A bare hour is *latent* / `is12H` and matches both halves. The caller resolves AM/PM. Maintainers: "Duckling doesn't know this context". | Ambiguity is the parser's output, not a guess. Resolve AM/PM with *kind + verb + part-of-day* rules and say the result back. |
| 11 | **dateparser** `PREFER_DATES_FROM` [16] | `current_period` (default) can return a past time: "1pm" said at 5 pm gives today 1 pm. `future` always rolls forward. | Every alarm/reminder time is forced into the future. Never schedule a time in the past. |
| 12 | **SUTime** (Chang & Manning, LREC 2012) [17] | Rule cascade with TIMEX3 normalisation relative to a reference time. Part-of-day words map to ranges (MO, AF, EV, NI). | Map each part-of-day word to an hour range. Reference time = now. |
| 13 | Hindi temporal tagging (ILTIMEX2012, F1 0.78) [18] + Hindi clock usage [19] | Rule-based Hindi tagger. Clock fractions: *sawa* = +:15, *saade* = +:30 (from 3 up), *paune* = next hour −:15, *dedh* = 1:30, *dhai* = 2:30. | Rules, not ML, for Hinglish. Fraction words also apply to durations ("dedh ghante" = 90 min). |
| 14 | Sundelin et al. 2023, "Is snoozing losing?" (J. Sleep Res.) [20] | 69% snooze. A **30-min** snooze period gave no harm to sleep or mood in habitual snoozers, slightly *less* sleep inertia, and ~6 min of sleep lost. | Cap total snooze at about 30 min (3 × 9). Don't moralise about snoozing. |
| 15 | Hilditch & McHill 2019, "Sleep inertia: current insights" [21] | Grogginess is worst in the first **15–30 min** after waking. Waking from deep sleep is worse. | Keep the wake-up voice line short and concrete. Do the post-wake check-in only after he's up. |
| 16 | McFarlane et al. 2020 (PLOS ONE) [22] | A **melodic** alarm sound was linked to less self-reported sleep inertia. Harsh beeps were not. | Use a melodic tone (from a soft start), not a buzzer. |
| 17 | Iqbal & Bailey 2008 (CHI) / OASIS [23] | Holding a notification until a task **breakpoint** cuts frustration and reaction time. | Hold a spoken reminder until his turn or Stiti's speech ends (≤2 min max delay). |
| 18 | Mehrotra et al. 2016 (CHI) [24]; Pielot et al. 2017 (IMWUT) [25] | Receptivity depends on content and context. Predicted "opportune moments" engage far better than fixed rules. | Choose the channel from presence: voice when present, notification + Telegram when away. Log acks for later tuning by Laya. |

## 2. Recommendations (numbers are starting defaults; record them in DECISIONS.md)

### 2a. AM/PM resolution (applied in this order; the first rule that matches wins)
1. **Explicit marker**: `am/pm`, a 24-h value (`14:30`), or a part-of-day word.
   `subah/savere` → 4–11 = AM; `subah 12` → ask.
   `dopahar` → 12 = noon, 1–4 = PM.
   `shaam` → 4–8 = PM.
   `raat` → 8–11 = PM; `raat 12` = **00:00 at the end of that day** ("aaj raat 12" = tonight's midnight, "kal raat 12" = midnight at the end of tomorrow); `raat 1–4` = AM *after* that evening.
   `bhor/tadke` → 3–6 AM.
2. **Wake verb / alarm kind**: if the text has `uth/uthana/jaga/jagana/alarm/wake`, hours **3–11 → AM** ("6 baje uthana" = 06:00). `alarm 12 baje` → ask.
3. **Reminder/meeting with no cue**: **1–6 → PM** ("kal 2 baje" = 14:00, "5 baje call" = 17:00). **7–11 → the next future occurrence** of either half ("8 baje" said at 10:00 → 20:00; said at 21:00 → 08:00 tomorrow). **12 → noon**.
4. **Never in the past** [16]. If an explicit-day time has already passed today ("aaj 3 baje" said at 16:00) → ask "aaj 3 toh nikal gaya — kal 3?".
5. **"kal" said between 00:00 and 03:59** → means later *today* (already in the code). Always say the weekday in the readback.
6. **Hinglish clock forms**:
   - `sawa 7` = 7:15, `saade 6` = 6:30, `paune 7` = **6:45**, `dedh` = 1:30, `dhai` = 2:30, `saade 12` = 12:30, `paune 1` = 12:45.
   - `7 bajke 10 minute` = 7:10. `7 bajne mein 10 minute` = **6:50**.
   - Durations: `aadha ghanta` = 30 min, `sawa ghanta` = 75 min, `dedh ghanta` = 90 min, `dhai ghante` = 150 min, `paun ghanta` = 45 min.
7. **Gap found in the current `dates.py`**: the "+12 h roll" excludes `am/subah` but not `raat`. As a result, "raat 1 baje" said at 10:00 becomes **13:00**. Rule 1 must be final; nothing should roll an hour that already has a part-of-day word.

### 2b. Recurrence phrases → RRULE (store `rrule`, `dtstart` local, `tzid=Asia/Kolkata`; expand with dateutil)
| Phrase | RRULE |
|---|---|
| `roz`, `har din`, `daily`, `every day` | `FREQ=DAILY` |
| `weekdays`, `har weekday`, `somvar se shukravar`, `Mon–Fri`, `office days` | `FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR` |
| `weekends`, `har shanivar-ravivar` | `FREQ=WEEKLY;BYDAY=SA,SU` |
| `har somvar` / `every Monday` (somvar MO, mangalvar TU, budhvar WE, guruvar/veervar TH, shukravar FR, shanivar SA, ravivar/itvaar SU) | `FREQ=WEEKLY;BYDAY=MO` |
| `har Monday aur Thursday` | `FREQ=WEEKLY;BYDAY=MO,TH` |
| `ek din chhod ke`, `every other day`, `har do din` | `FREQ=DAILY;INTERVAL=2` |
| `har mahine 5 tareekh` | `FREQ=MONTHLY;BYMONTHDAY=5` |
| `agle 5 din roz` | `FREQ=DAILY;COUNT=5` |
| `Diwali/15 Dec tak roz` | `FREQ=DAILY;UNTIL=<date>T235959` |
| `har ghante` (reminders only; ask about quiet hours) | `FREQ=HOURLY;BYHOUR=9,...,21` |

- Skip one occurrence ("kal ka alarm mat bajana") → add an `EXDATE`. Stop the series ("roz wala band karo") → set `active=false`.
- If it's unclear which one he means → ask "Sirf kal ka ya roz ka?".
- Mirror to EventKit with the same rule (EKRecurrenceRule supports daily, weekly with days, and monthly).

### 2c. The ring (wake alarms)
- **Sound**: a melodic tone [22], looped.
- **Volume ramp**: start at **30%** of the target, add **+10% every 15 s**, reach **100% at about 2 min**. Raise the Mac output volume to at least **50%** while ringing, then restore it.
- **Voice line**: first at **0:10**, then every **60 s**. Short and concrete [21]: "Tejmul, 6 baj gaye — uthne ka time. 'Band karo' ya '5 minute aur' bolo." From the 3rd line on, add today's first event ("9:30 pe standup hai").
- **Listening while it rings**: no wake word needed [6], for the whole ring. Use a closed on-device grammar fed by whisper STT, with the tone loop as the AEC reference. Duck the tone to **20%** while speech is detected [1].
  - **Dismiss**: `band karo`, `bas`, `stop`, `off`, `uth gaya/gayi`, `utha hoon`, `theek hai`.
  - **Snooze**: `snooze`, `N minute aur`, `thodi der aur`, `baad mein`.
  - If he says a number it means snooze; any other speech is ignored. Menubar and Telegram buttons work too.
- **Snooze**: default **9 min** [3][9]. A spoken N is clamped to **1–30**. Soft max **3 snoozes (~27 min, inside Sundelin's 30-min window)** [20]. A 4th snooze is allowed only after a confirmation ("pakka? 3 ho gaye"). Hard stop at **45 min** total.
- **Auto-stop**: after **10 min** with no response [8] (not Alexa's 1 h — the Mac may be in an empty room). Then: mark the alarm `unanswered`, send a Telegram ping plus a macOS notification, and auto-snooze **once** (re-ring after 9 min). After that it is done.
- **Timer**: same ramp, auto-stop at **5 min**, one voice line ("20 minute ho gaye").
- **Reminder**: one chime + voice line. If not acknowledged, repeat **once at +2 min**. If still not acknowledged → notification + Telegram. Items tagged "zaroor" nag every **10 min, at most 3 times**, until "ho gaya".
- **Optional wake check**: **3 min** after a wake alarm is dismissed, Stiti says one line ("Good morning — paani pi lo"). If there is no voice or HID activity within **60 s**, ring once more at 50% volume.

### 2d. Missed while Stiti was off or the Mac was asleep (catch-up pass at startup and wake, per AVS/Android [1][11])
| Kind | Lateness ≤ | Action | Later than that |
|---|---|---|---|
| Wake alarm | **10 min** | Ring normally | 10–30 min: one soft chime + "7 baje ka alarm tha, Mac so raha tha — 7:20 ho gaye". **>30 min: never ring.** Note it in the morning brief and the "missed" list. |
| Timer | **2 min** | Ring (short) | Say "timer 6 min pehle khatam ho gaya tha" once he is present. |
| Reminder | **15 min** | Deliver normally | 15 min–**12 h**: deliver once with a "late:" prefix and the original time. Over 12 h: digest in the next brief. Skip it if the EventKit mirror already alerted on his phone (`completed` or overdue there). |
| Recurring (any) | — | Apply the row above to the **latest** missed occurrence only | Never replay older occurrences. Recompute `next_fire = rrule.after(now)`. |

- **Mac asleep**: optionally `pmset schedule wake` 1 min before a wake alarm (this needs a one-time sudoers entry).
- **Clamshell sleep**: the iPhone mirror is the fallback.

### 2e. Delivering reminders: presence → channel [23][24][25]
- **Present**: a voice turn in the last **10 min**, or `HIDIdleTime` < **2 min**, and the screen is unlocked.
- **Away**: idle > **5 min**, locked, or asleep.
- **Present, not mid-turn** → speak now.
- **Present, mid-turn** (he or Stiti is talking) → wait for the turn's end. Maximum delay **2 min**, then interrupt.
- **In a call** (another app holds the mic or camera) → banner only; speak after the call.
- **Away** → macOS notification + Telegram. The Apple Reminders mirror already reaches the iPhone and Watch.
- **Quiet hours 23:00–07:00**: reminders are held unless they are alarms or tagged "zaroor".
- Log the channel used and the ack latency for each delivery, as training data for Laya.

### 2f. Confirmation, readback, editing
- **Always restate kind + time + part of day + day** [5]:
  - "Theek hai — alarm kal subah 6 baje, Wednesday."
  - "Yaad dila dungi — aaj shaam 5 baje, call Rahul."
- **Defaulted AM/PM**: when rule 2a.3 or a 12 o'clock rule picked the half, add the half as a question: "…dopahar 2 baje, sahi?". Accept a correction within **10 s** ("nahi, raat ko").
- **Recurring**: "Roz subah 7 baje, sirf weekdays — pehla kal, Tuesday."
- **Timer**: "20 minute ka timer — 7:42 pe bajega."
- **Failed save** (DB or EventKit) → say so and give the reason [5].
- **Picking an alarm to change**:
  - It can be named by time ("6 baje wala"), label ("gym wala"), ordinal ("pehla"), or "last one" (most recently created).
  - If 2 or more match → list **at most 3**: "Do alarm hain — subah 6 aur 6:30. Kaunsa?"
  - Edit readback: "6 ki jagah 6:30 kar diya." Cancel readback: "Kal subah 6 ka alarm hata diya."
  - Cancelling a recurring alarm asks which scope: just that occurrence or the whole series.

## 3. Sources
[1] Amazon AVS Alerts 1.5 — https://developer.amazon.com/docs/alexa-voice-service/alerts.html
[2] Amazon AVS Alerts overview (30-min rule) — https://developer.amazon.com/docs/alexa-voice-service/alerts-overview.html
[3] Amazon help, Snooze Alarms on Echo (9 min) — https://www.amazon.com/gp/help/customer/display.html?nodeId=GNH83D4XPJPX4PDN
[4] Amazon help, What are Alexa Reminders? (missed reminders) — https://www.amazon.com/gp/help/customer/display.html?nodeId=GVMW5E8YCNR6AC6E
[5] Alexa Reminders Guidelines for Usage — https://developer.amazon.com/en-US/docs/alexa/smapi/alexa-reminders-guidelines-for-usage.html
[6] Google Assistant, Set & manage alarms — https://support.google.com/assistant/answer/9275058
[7] Google Nest, alarms on speakers/displays (snooze 10 min, hotword-free "Stop") — https://support.google.com/googlenest/answer/7071598
[8] Google Clock: gradual volume (v4.2) / silence-after reports — https://www.androidauthority.com/google-clock-app-update-v4-2-ui-alarm-volume-tones-643728 ; https://forums.androidcentral.com/threads/slowly-increasing-alarm-volume.940280
[9] MacRumors, iOS 26 custom snooze (1–15 min, default 9) — https://www.macrumors.com/2025/06/11/ios-26-big-change-iphone-alarm-options/
[10] Apple AlarmKit docs + WWDC25 "Wake up to the AlarmKit API" — https://developer.apple.com/documentation/alarmkit ; https://wwdcnotes.com/documentation/wwdc25-230-wake-up-to-the-alarmkit-api/
[11] Android, Schedule alarms (setAlarmClock, BOOT_COMPLETED) — https://developer.android.com/training/scheduling/alarms ; exact alarms on 14 — https://developer.android.com/about/versions/14/changes/schedule-exact-alarms
[12] RFC 5545 §3.3.10 Recurrence Rule — https://www.rfc-editor.org/rfc/rfc5545#section-3.3.10
[13] python-dateutil rrule — https://dateutil.readthedocs.io/en/stable/rrule.html
[14] Duckling Time helpers (`is12H`, latent hours) — https://github.com/facebook/duckling/blob/main/Duckling/Time/Helpers.hs
[15] Rasa forum, Duckling AM/PM context (maintainer) — https://forum.rasa.com/t/duckling-time-extraction/48479
[16] dateparser settings, PREFER_DATES_FROM — https://dateparser.readthedocs.io/en/latest/settings.html
[17] Chang & Manning, SUTime, LREC 2012 — https://nlp.stanford.edu/pubs/lrec2012-sutime.pdf
[18] Temporal Expression Recognition in Hindi (ILTIMEX2012) — https://doi.org/10.1007/978-3-319-03844-5_72
[19] Five Colleges Hindi, time expressions — https://www.langmedia.fivecolleges.edu/resources/hindi/grammar/time-expressions ; https://preply.com/en/blog/telling-time-in-hindi
[20] Sundelin, Landry, Axelsson 2023, Is snoozing losing? J. Sleep Res. — https://doi.org/10.1111/jsr.14054
[21] Hilditch & McHill 2019, Sleep inertia: current insights, Nat. Sci. Sleep — https://doi.org/10.2147/NSS.S188911
[22] McFarlane et al. 2020, Alarm tones, music and their elements, PLOS ONE — https://doi.org/10.1371/journal.pone.0215788
[23] Iqbal & Bailey 2008, Effects of intelligent notification management…, CHI — https://doi.org/10.1145/1357054.1357070
[24] Mehrotra et al. 2016, My Phone and Me: receptivity to mobile notifications, CHI — https://discovery.ucl.ac.uk/1502364/1/CHI16.pdf
[25] Pielot et al. 2017, Beyond Interruptibility, IMWUT 1(3) — https://doi.org/10.1145/3130956
