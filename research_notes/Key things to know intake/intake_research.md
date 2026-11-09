# "Key Things to Know" Intake for Stiti: psychology-grounded, offline, no-LLM

Researched 2026-11-10 for Stiti, an open-source, local-first voice buddy (Apple M2, 8 GB). Users speak casual Indian English or Hinglish.

**Constraints.** The intake and the learning that follows must run with **no LLM**: rules, regex, small lookup tables and the local embedder already in the repo (`src/stiti/embed.py` uses EmbeddingGemma-300M ONNX, 768-dim, about 7 ms per query). Everything must work for **any user** (no hard-coded "he"/"him") and use **only instruments whose licence allows free use in an open-source project**.

**Verification legend** (used in every table):
- **[V]**: verified this session from the primary page or an official page I fetched or searched (permission statements, item lists, abstracts).
- **[S]**: confirmed only through search-result snippets or a secondary summary. The main claim is likely right; check exact numbers in the paper.
- **[R]**: recalled from training knowledge and **not re-verified this session**. The citation is believed correct. Treat numbers as approximate.
- **[U]**: uncertain or unresolved, especially licence status. **Do not ship anything marked [U] verbatim.**

Nothing here is legal advice. Licence findings are what the instrument owners' pages say as of 2026-11-10.

---

## 0. Summary

1. **Personality.** Use **IPIP items**, which are public domain ([V] ipip.ori.org: "permission has already been automatically granted … for any purpose, commercial or non-commercial"), specifically the **Mini-IPIP** item set (Donnellan et al. 2006, 20 items).
   - Ask **5 items in the intake** (one per trait, spoken 5-point scale). Drip-feed the other 15 over the first 2–3 weeks, one at a time and only with opt-in, until the full validated 20-item set is reached.
   - **TIPI** (Gosling) is also free for any purpose [V]. Its adjective pairs are double-barrelled and hard to translate into Hinglish, so keep it as a fallback.
   - **Do not use** BFI-2/-S/-XS (non-commercial only [V]), BFI-10 (status unclear [U]) or HEXACO (non-profit academic research only [V]).
2. **Chronotype.** Do **not** copy MEQ/rMEQ/MCTQ wording (permission-based [S]). Ask **factual sleep and wake times on work days and free days in Stiti's own words**, then compute the **MCTQ mid-sleep metric (MSF, MSFsc) and social jetlag**. The published formula is science, not the questionnaire text. Add one self-rated "sharpest time of day" question, a construct supported by Loureiro & Garcia-Marques 2015 [S].
3. **Values and motivation.**
   - In the intake, use **two "this-or-that" questions** on Schwartz's two higher-order axes and **one regulatory-focus question**, all in Stiti's own wording.
   - Afterwards, drip-feed the **TIVI** (10 items), which is free for any purpose [V] (Gosling lab).
   - The **Personal Values Card Sort** (Miller et al. 2001) is public domain [S] and suits an optional "values chat" later.
   - Do not ship PVQ or SVS text (CC BY-NC-ND repository [S]) or BPNSFS (commercial use needs permission [V]).
4. **Stress and support.**
   - Ask **"how can I tell you're having a rough day"**, which gives personal stress markers.
   - Ask **"what helps most from me: listening, a plan, a joke/distraction, or space"**. This draws on Brief COPE categories and optimal-matching theory, and Carver says it is free to use [V].
   - Ask **"what do you do yourself to feel better"**, coded with the Brief COPE taxonomy.
   - **No PSS, PHQ, DASS or other clinical screeners in the intake.** Keep it non-diagnostic. PSS also needs permission for for-profit use [S].
5. **Conversation design.**
   - Order: consent → easy facts → fun (likes) → quick-fire → values → communication → *permission gate* → stress/support → boundaries → **read-back with correction** (the Summary in MI's OARS).
   - Keep answer options to 3 or fewer per prompt where possible. "Skip" and "pause" work everywhere.
   - Voice gets *less* sensitive disclosure than text (Schober et al. 2015 [V]), so offer "you can also type this one" for the stress block.
6. **Learning from conversation without an LLM.**
   - Regex fast path for explicit statements in English and Hinglish ("mujhe X pasand hai", "I can't stand X").
   - An embedding prototype classifier routes utterances into key-thing categories.
   - **Revealed-behaviour counters** (ignored nudges, "bas/stop", accepted plans) drive adaptation more than any text-based personality inference.
   - Text-to-Big-Five accuracy is only about r ≈ .3–.4 even with large data (Azucar et al. 2018 [S]; Park et al. 2015 [S]). It is too weak to act on for a single user, so **don't infer traits from text**.
   - **VADER** (MIT [V]), **Empath** (MIT [V]) and **AFINN** (Apache-2.0 repo [V]) may be bundled. **NRC EmoLex may not**: it is non-commercial and says "Do not redistribute" [V]. **LIWC** is proprietary.
7. **Ethics.**
   - Consent up front and again before the sensitive block.
   - No diagnosis or clinical words.
   - Trait labels are always "leans …" with source and confidence, viewable ("What do you know about me?") and correctable. User edits win.
   - Stress, coping and health data go in **P2 (never leaves the Mac)**, and only generic style directives derived from them may reach a cloud LLM.
   - Never infer protected attributes. Adaptations serve **only the user's own stated goals**, and every adaptation is logged with a reason.
8. **Adaptation.** **Explicit preferences always beat trait inferences.**
   - The strongest-evidence adaptations are timing from the user's own sleep/wake times, support mode from the user's own answer, autonomy-supportive language for everyone, and implementation-intention chunking.
   - Trait-matched framing (Hirsh et al. 2012 [V]) has real but **small** effects. Tailoring overall: r ≈ .07 (Noar et al. 2007 [V]). Field evidence is contested (Matz et al. 2017 vs Eckles et al. 2018 [V]).
   - Treat trait framing as a light touch. It is also the main **manipulation risk**.
9. **Intake length.** 20 turns (24 spoken prompts including the 5-item quick-fire), **about 5.5–6 min** (budget in §9.3).

### 0.1 Licence traffic-light for an open-source repo

An MIT/Apache code licence lets *anyone* reuse the code commercially. Embedding "non-commercial only" item text in the repo therefore conflicts with the project licence. The repo has no LICENSE file yet as of today.

| Status | Instruments |
|---|---|
| **Green: ship verbatim** | IPIP items incl. Mini-IPIP and IPIP-NEO/BFAS item text (public domain [V]); TIPI ("anyone can use it for any purpose" [V]); TIVI/TwIVI ("anyone can use it for any purpose" [V]); VADER (MIT [V]); Empath (MIT [V]); AFINN (Apache-2.0 repo [V]) |
| **Yellow: probably fine, confirm before verbatim use** | Brief COPE (Carver: "You are welcome to use all scales … Feel free as well to adapt the language" [V]. No explicit commercial clause, though Carver's index says measures are available "without any need for permission" [S]); Personal Values Card Sort (authors' notice says public domain [S]) |
| **Red: do not ship item text** | BFI-2/-S/-XS ("for non-commercial uses only" [V]); BFI-10 (article CC BY, item ownership unclear [U]); HEXACO-60/100 (non-profit academic only [V]); BHI-24 (no terms found [U]); PVQ-21/40/RR and SVS (repository CC BY-NC-ND [S]); BPNSFS and other CSDT scales (commercial use needs permission [V]); PSS (for-profit use needs permission and fee [S]); MEQ/rMEQ and MCTQ (permission-based per the ATS sleep-questionnaire registry [S]); RFQ/GRFM (no terms found [U]); NRC EmoLex (non-commercial, no redistribution [V]); LIWC (proprietary) |

**Workaround used throughout:** constructs and formulas are not copyrightable, but specific item wording is (general principle; not legal advice). For red-listed constructs, Stiti asks **original, plainly worded questions** about the *construct* and cites the theory. It marks them **"Stiti-original, unvalidated"**, and the code must never call them by the instrument's name or claim its validity.

---

## 1. Brief personality instruments usable in conversation

### Comparison table

| # | Instrument | Link | Year | Measures | Items | Licence / usage | Validity evidence | Fit for spoken 5–6 min intake | Ver. |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **TIPI** (Gosling, Rentfrow, Swann) | [Gosling lab page](https://gosling.psy.utexas.edu/scales-weve-developed/ten-item-personality-measure-tipi/), [doi](https://doi.org/10.1016/S0092-6566(03)00046-1) | 2003 | Big Five | 10 (2/trait, 7-pt) | "**ANYONE CAN USE IT FOR ANY PURPOSE. NO NEED TO ASK ME FOR PERMISSION.**" Items 2, 4, 6, 8, 10 reverse-scored. | Convergence with BFI about .65–.87 (mean about .77); 6-week retest about .72; alphas low (.40–.73) by design | Medium. Free. Adjective *pairs* ("Anxious, easily upset") are double-barrelled. A 7-point scale is hard by voice. Hinglish translation is awkward. | [V] permission/scoring; [R] numbers |
| 2 | **FIPI** (Five-Item Personality Inventory) | same paper as TIPI | 2003 | Big Five | 5 bipolar | Published with TIPI. The lab page's permission text names only TIPI. | Weaker than TIPI in the original paper | Low–Medium. Very fast, but bipolar adjective scales are hard by voice. | [R]; licence [U] |
| 3 | **BFI-10** (Rammstedt & John) | [doi](https://doi.org/10.1016/j.jrp.2006.02.001); [MDA 2013 OA article](https://mda.gesis.org/index.php/mda/article/view/2013.013) | 2007 | Big Five | 10 (2/trait, 5-pt) | 2013 validation article is CC BY. Items derive from BFI-44 (John copyright). The Berkeley lab page recommends against BFI-10 "unless there are exceptional circumstances" [V]. No explicit open/commercial grant found. | Retest about .75; about 70% of BFI-44 variance; part-whole r about .83 | Medium psychometrically, **Red** on licence clarity | [S] licence; [R] numbers; [U] reuse |
| 4 | **BFI-2-XS** (Soto & John) | [doi](https://doi.org/10.1016/j.jrp.2017.02.004); [John lab](https://www.ocf.berkeley.edu/~johnlab/bfi.html) | 2017 | Big Five domains | 15 (3/trait) | "BFI-2 … **for non-commercial uses only**"; commercial requests to the lab [V] | Domain-level validity acceptable; facet-level not; alphas about .5–.7 | Red (licence) | [V] licence; [R] numbers |
| 5 | **BFI-2-S** | same | 2017 | Big Five + 15 facets | 30 | Same non-commercial restriction [V] | Good | Too long and Red | [V]/[R] |
| 6 | **Mini-IPIP** (Donnellan et al.) | [IPIP key](https://ipip.ori.org/MiniIPIPKey.htm), [doi](https://doi.org/10.1037/1040-3590.18.2.192) | 2006 | Big Five (O = Intellect/Imagination) | 20 (4/trait, 5-pt) | **Public domain** (IPIP) [V] | Alphas at or above .60 across 5 studies; retest similar to parent IPIP-50 [S]; widely replicated | **High.** Short verb-phrase items ("Get chores done right away") work well spoken and translate cleanly. Can be split across days. | [V] items/licence; [S] psychometrics |
| 7 | **IPIP Big-Five Factor Markers** (Goldberg) | [ipip.ori.org](https://ipip.ori.org) | 1992/1999 | Big Five | 50 or 100 | Public domain [V] | Strong; parent of Mini-IPIP | Too long for intake; source for extra items later | [V] licence |
| 8 | **IPIP-NEO-120** (Johnson) | [doi](https://doi.org/10.1016/j.jrp.2014.05.003) | 2014 | Big Five + 30 facets | 120 | Public domain items [R] | Good facet-level validity | Never in intake; possible "deep profile" opt-in | [R] |
| 9 | **BFAS** (DeYoung, Quilty, Peterson) | [doi](https://doi.org/10.1037/0022-3514.93.5.880) | 2007 | 10 aspects (e.g., Withdrawal vs Volatility) | 100 | IPIP-derived, public domain items [R] | Good | Too long. Aspects matter for adaptation (e.g., N-Withdrawal → gentler framing). | [R] |
| 10 | **Mini-IPIP6** (Sibley et al.) | NZ J Psychol 40(3) (link not verified) | 2011 | Big Five + Honesty-Humility | 24 | IPIP-based [R] | Validated in NZ samples | Low; H-H not needed for adaptation | [R]/[U] |
| 11 | **HEXACO-60** (Ashton & Lee) | [hexaco.org](https://hexaco.org/hexaco-inventory), [doi](https://doi.org/10.1080/00223890902935878) | 2009 | 6 factors | 60 | "free of charge, but only for the purpose of **non-profit academic research**"; other uses contact the authors or buy a licence [S] | Strong | Red | [S] |
| 12 | **BHI-24** (Brief HEXACO Inventory, de Vries) | J Res Pers 47 (2013), doi not verified | 2013 | 6 factors | 24 | No terms found [U] | Moderate | Red/unknown | [R]/[U] |
| 13 | **SIMP** single-item bipolar Big Five (Woods & Hampson) | [doi](https://doi.org/10.1002/per.542) | 2005 | Big Five | 5 | Not found [U] | Mean convergence with long scales r = .61, N = 791 [S] | Shows 1 item/trait is usable as a *prior* | [S] |
| 14 | **Credé et al.** (evaluation of short Big Five measures) | [doi](https://doi.org/10.1037/a0027403) | 2012 | (meta-method) | n/a | n/a | 1–2-item measures **underestimate** trait–outcome links and raise Type I and II error [S] | Warning: treat 1-item scores as low-confidence priors | [S] |
| 15 | **Denissen et al.** (single-item Big Five in a social network design) | [PDF](https://www.psychology.hu-berlin.de/de/prof/perdev/pdf/2008/Denissen_SingleItemBig5.pdf) | 2008 | Big Five | 5 | n/a | Single items show usable validity in large samples | Supports progressive design | [S] |

### Reliability of 1–2-item measures (what it means for Stiti)
- **Internal consistency** (alpha) is undefined or low for 1–2 items. **Retest reliability** and **convergent validity** (about .6–.8) are the right yardsticks (TIPI, SIMP [S]/[R]).
- Spearman–Brown logic: if a single item correlates about .6 with the full scale, 2 items reach about .7–.75 and 4 items (Mini-IPIP) about .85–.9 with the parent IPIP-50 [R].
- Credé et al. (2012) [S]: short forms are fine for *describing* a person roughly but bad for *precise* decisions. Stiti should therefore **never make hard decisions from 1 item**. Use it as a weak prior that explicit preferences and behaviour override.

### How to ask conversationally, and scoring
- **Format:** a fully labelled 5-point scale. Fully labelled scales outperform numeric ones for data quality (Krosnick & Presser 2010 handbook chapter [R]). Numbers ("1 to 5") are hard to hold in working memory by voice.
- **Spoken anchors:**
  - EN: "**totally** / **kind of** / **not sure** / **not really** / **not at all**"
  - Hinglish: "**bilkul** / **thoda thoda** / **pata nahi** / **zyada nahi** / **bilkul nahi**"
- **Item stem:** IPIP verb phrases read as descriptions ("Gets chores done right away."), with the frame "how much is that you?".
  - Hinglish uses gender-neutral second-person forms ("…karte ho"). This avoids Hindi verb gender (karta/karti) for an unknown user.
- **Scoring:** totally = 5, kind of = 4, not sure/depends = 3, not really = 2, not at all = 1. Reverse-keyed items: 6 − x. Trait estimate = mean of the items answered so far.
- **Mode effects:** telephone/voice respondents give more extreme and more positive answers than web respondents (Christian, Dillman & Smyth 2008 [R]). Acquiescence ("yes" bias) is higher in collectivist and high-context cultures (Smith 2004, JCCP [R]). **Mitigation:** balance keying (the intake set has 2 reverse-keyed items, and the drip set completes the 2+/2− balance). Use only within-person interpretation; **no population norms** (no Indian norms for Mini-IPIP were verified [U]).

### Recommendation
- **Use Mini-IPIP items**: public domain, simple language, validated, splittable.
- Intake: **5 items**, one per trait, chosen for spoken clarity and keying balance. Drip-feed the remaining 15 (one at most per day, at low-load moments, after asking "can I sometimes ask you a quick one?").
- Keep TIPI as a licence-safe alternative for users who prefer one fast block. Never use BFI-2/BFI-10/HEXACO text.
- Translation caveat: Hinglish wordings below are **Stiti translations, not validated adaptations** (ITC *Guidelines for Translating and Adapting Tests*, 2nd ed. 2017 [R]). Psychometric properties may change.

---

## 2. Chronotype and daily rhythm

### Comparison table

| # | Instrument / source | Link | Year | Measures | Items | Licence / usage | Validity | Fit | Ver. |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **MEQ** (Horne & Östberg) | [PubMed](https://pubmed.ncbi.nlm.nih.gov/1027738/), [CET](https://www.cet.org/assessment/) | 1976 | Morningness–eveningness preference | 19 | ATS registry: "with permission … free for non-profit use" [S]; CET points clinical-trial users to Mapi Research Trust [S] | Gold standard; correlates with DLMO | Too long; licence unclear | [S] |
| 2 | **rMEQ** (Adan & Almirall) | [doi](https://doi.org/10.1016/0191-8869(91)90110-W) | 1991 | Preference (MEQ items 1, 7, 10, 18, 19) | 5 | Same family as MEQ; no explicit grant found [U] | Range 4–25; cut-offs < 12 evening, 12–17 neither, > 17 morning [S] | Good length, but don't copy wording | [S] |
| 3 | **Single self-assessment item** (Loureiro & Garcia-Marques) | [doi](https://doi.org/10.1016/j.paid.2015.06.022) | 2015 | Self-rated chronotype ("definitely morning" … "definitely evening") | 1 | The original item is MEQ/rMEQ item 19 [U]; the *construct* is free | Single item classifies people like the full scale; r > .8 with rMEQ [S] | **High as a construct.** Ask in Stiti's own words. | [S] |
| 4 | **CSM** (Composite Scale of Morningness; Smith, Reilly, Midkiff) | [doi](https://doi.org/10.1037/0021-9010.74.5.728) | 1989 | Preference | 13 | Not found [U] | Good | Too long | [R] |
| 5 | **MCTQ** (Roenneberg, Wirz-Justice, Merrow) | [doi](https://doi.org/10.1177/0748730402239679); [ATS registry](https://www.thoracic.org/assemblies/srn/questionaires/mctq.php) | 2003 | **Actual** sleep timing on work and free days → MSF | 17 (core) | ATS registry lists "with permission" [S]. thewep.org was unreachable this session (TLS error). | Correlates with actimetry and DLMO | **Construct and formula are ideal for voice.** Re-word the questions. | [S]/[U] |
| 6 | **MSFsc correction** (Roenneberg et al.) | [doi](https://doi.org/10.1016/j.cub.2004.11.039) | 2004 | Corrects mid-sleep for free-day oversleep | formula | Formula, not text | Standard in the chronobiology literature | **Use** | [R] |
| 7 | **µMCTQ** (Ghotbi et al.) | [PubMed 31791166](https://www.pubmed.gov/31791166/) | 2020 | Ultra-short MCTQ core module | 6 | Has its own "Terms of use" section (not retrieved) [U] | Matches stdMCTQ; validated by actimetry and DLMO; shifts < 35 min [S] | Shows that ~4 factual times suffice | [S] |
| 8 | **Social jetlag** (Wittmann et al.) | [doi](https://doi.org/10.1080/07420520500545979) | 2006 | \|MSF − MSW\|, the mismatch between body clock and social clock | derived | Concept | Linked to well-being and substance use | **Use** to decide whether to *protect* free-day mornings | [R] |
| 9 | **MESSi** (Randler et al.) | Chronobiol Int (2016), doi not verified | 2016 | Morning affect, eveningness, amplitude | 15 | [U] | Good | Too long | [R]/[U] |
| 10 | **Synchrony effect** (May, Hasher & Stoltzfus 1993; Schmidt et al. 2007 review) | Psychol Sci 4(5); Cogn Neuropsychol 24(7) | 1993/2007 | Cognitive performance peaks at the chronotype-optimal time | n/a | n/a | Repeated lab evidence | Justifies scheduling deep work in the user's "sharpest" window | [R] |
| 11 | **Sleep inertia** (Tassi & Muzet 2000) | Sleep Med Rev 4(4) | 2000 | Grogginess for minutes to about an hour after waking | n/a | n/a | Review | Justifies "no nudges in the first 45–60 min after waking" | [R] |
| 12 | **Passive rhythm from activity timestamps** (e.g., Twitter rhythms, Leypunskiy et al. 2018) | Current Biology (doi not verified) | 2018 | Daily activity cycles and social jetlag from digital traces | n/a | n/a | Population-level | Stiti can learn first/last interaction times per day locally | [R]/[U] |

### Recommendation: 3 conversational questions + passive learning
1. **Work day:** "On a usual work or college day, roughly when do you fall asleep and wake up?" Gives SO_w and WU_w.
2. **Free day (no alarm):** "And on a free day, with no alarm, when do you sleep and wake?" Gives SO_f and WU_f.
3. **Self-rated peak:** "When does your brain feel sharpest: morning, afternoon, evening, or late night?"

**Computation (MCTQ logic, Roenneberg 2003/2004 [R]):**
```
SD_w = (WU_w − SO_w) mod 24h ; SD_f = (WU_f − SO_f) mod 24h
MSW  = SO_w + SD_w/2         ; MSF  = SO_f + SD_f/2
WD   = workdays per week (default 5; ask later; many Indian jobs have 6)
SD_week = (SD_w*WD + SD_f*(7−WD)) / 7
MSFsc = MSF − (SD_f − SD_week)/2   if SD_f > SD_w else MSF
social_jetlag = |MSF − MSW|
```
- Classification (**heuristic, mark as such**): MSFsc < 03:00 → "early"; 03:00–05:00 → "intermediate"; > 05:00 → "late".
  - Central-European population means sit around 04:00–04:30 [R]. Young Indian urban users may skew later [U]. **Prefer the user's own times over category labels.**
- Agreement check: if the Q5 self-rating agrees with the MSFsc category, confidence is 0.8; if not, 0.5, and the *reported times* decide timing.
- **Passive update:** keep a 14-day rolling median of the first and last interaction of each day, separately for weekdays and weekends. If it drifts more than 60 min from the intake values for 7+ days, ask: "Looks like you're up later these days. Should I shift my morning check-in?"
- **Licence:** Stiti's questions are original wording asking for factual times. The MCTQ/MSFsc formula is cited, not reproduced as a questionnaire.

---

## 3. Values and motivation

### Comparison table

| # | Instrument | Link | Year | Measures | Items | Licence / usage | Validity | Fit | Ver. |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **SVS** (Schwartz Value Survey) | [doi](https://doi.org/10.1016/S0065-2601(08)60281-6) | 1992 | 10 basic values | 57 | Schwartz repository CC BY-NC-ND [S] | Cross-cultural (incl. India) | Too long; Red | [R]/[S] |
| 2 | **PVQ-40** | [doi](https://doi.org/10.1177/0022022101032005001) | 2001 | 10 values via portraits | 40 | As above [S] | Strong | Red | [R] |
| 3 | **PVQ-21 / ESS Human Values Scale** | [ESS](https://www.europeansocialsurvey.org/) | 2003 | 10 values | 21 | APA PsycTests record; terms not retrieved [U] | Many countries | Red/unknown | [S] |
| 4 | **PVQ-RR** (refined theory) | [doi](https://doi.org/10.1037/a0029393) | 2012/2017 | 19 values | 57 | [U] | Strong | Too long | [R] |
| 5 | **TIVI** (Sandy, Gosling, Schwartz, Koelkebeck) | [Gosling lab](https://gosling.psy.utexas.edu/two-short-measures-of-values-tivi-and-twivi/), [doi](https://doi.org/10.1080/00223891.2016.1231115) | 2017 | 10 values, 1 item each (portraits, 6-pt) | 10 | "**ANYONE CAN USE IT FOR ANY PURPOSE. NO NEED TO ASK ME FOR PERMISSION.**" [V] | Derived from PVQ-40 on samples of about 38k and 29k; reproduces PVQ correlation patterns [V] | **Green.** Best licence-safe values measure. Too long for intake (portraits about 8 s each) → drip-feed. Use pronoun-branching wording as the lab advises [V]. | [V] |
| 6 | **TwIVI** | same | 2017 | 10 values, 2 items each | 20 | Same "any purpose" [V] | 2022 Portuguese CFA confirmed circumplex [S] | Optional deep profile | [V]/[S] |
| 7 | **SSVS** (Lindeman & Verkasalo) | J Pers Assess 85(2) | 2005 | 10 values, 1 item each | 10 | [U] | Good | Red/unknown | [R] |
| 8 | **Rokeach Value Survey** | Rokeach (1973), *The Nature of Human Values* | 1973 | Terminal and instrumental values (ranking) | 36 | Copyrighted book [R] | Historic | Low | [R] |
| 9 | **Personal Values Card Sort** (Miller, C'de Baca, Matthews, Wilbourne; MI tradition) | [CASAA PDF](https://casaa.unm.edu/assets/inst/personal-values-card-sort-2.pdf); [MINT](https://motivationalinterviewing.org/node/4481) | 2001 (upd. 2011) | Idiographic values (sort 83 cards) | 83 cards | Authors' notice: **public domain**, "may be copied or adapted without further permission" [S] | Clinical/MI use; idiographic, not psychometric | Too long for intake. A good later "what matters to you" conversation. | [S] |
| 10 | **BPNSFS** (SDT basic needs; Chen et al.) | [CSDT page](https://selfdeterminationtheory.org/basic-psychological-need-satisfaction-and-frustration-scale/), [doi](https://doi.org/10.1007/s11031-014-9450-1) | 2015 | Autonomy, competence, relatedness (satisfaction and frustration) | 24 | "All academic use is permitted, but you must obtain permission … for **commercial use**" [V] | Strong, cross-cultural | Red (verbatim); construct OK | [V] |
| 11 | **BMPN** (Sheldon & Hilpert) | [doi](https://doi.org/10.1007/s11031-012-9279-4) | 2012 | SDT needs | 18 | [U] | Good | Red/unknown | [R] |
| 12 | **Aspiration Index** (Kasser & Ryan) | [CSDT](https://selfdeterminationtheory.org/aspirations-index) | 1996 | Intrinsic vs extrinsic life goals | 35+ | CSDT terms (academic OK, commercial needs permission) [S] | Strong | Construct useful; text Red | [S] |
| 13 | **RFQ** (Higgins et al.) | [doi](https://doi.org/10.1002/ejsp.27) | 2001 | Promotion vs prevention *history* | 11 | [U] | Good | Construct useful | [R] |
| 14 | **GRFM** (Lockwood, Jordan, Kunda) | [doi](https://doi.org/10.1037/0022-3514.83.4.854) | 2002 | Promotion vs prevention *strivings* | 18 | [U] | Good; predicts role-model matching | Construct useful | [R] |
| 15 | **Composite RF scale** (Haws, Dholakia, Bearden) | [doi](https://doi.org/10.1509/jmkr.47.5.967) | 2010 | Promotion and prevention | 10 | [U] | Compares RF scales | Construct useful | [R] |
| 16 | **MFQ-20** (Graham et al.) | [doi](https://doi.org/10.1037/a0021847) | 2011 | Moral foundations | 20 | Freely available for research [R]/[U] | Mixed | Not needed; politically loaded → skip | [R] |

### Quick conversational versions (Stiti-original, unvalidated)
- **Schwartz higher-order axis 1 (Openness to change vs Conservation):** "Right now in life, what matters more: **stability and security**, or **freedom and new experiences**?"
- **Axis 2 (Self-enhancement vs Self-transcendence):** "**Getting ahead and achieving big things**, or **looking after people and making things better around you**?"
- **Regulatory focus (Higgins):** "When you chase a goal, what pushes you more: **the excitement of what you'll gain**, or **making sure nothing goes wrong**?"
- **SDT needs** (drip-feed, not intake): "What makes a day feel really good for you: **doing things your own way**, **getting better at something**, or **feeling close to people**?"
- **Current goal** (personal strivings, Emmons 1986 [R]; MI "elicit what matters"): "What's one thing you're working towards these days?"

**Scoring:** this-or-that → {A, B, both, neither/depends} → axis score −1 / +1 / 0. Classification uses keyword sets plus embedding similarity to the two option texts (details in §10.3).

### Recommendation
- Intake: the 2 axis questions, 1 regulatory-focus question and 1 goal question.
- Week 1–2 drip: **TIVI** (10 items, Green), shown with pronoun-appropriate wording. Mean-centre each person's ratings across the 10 items, as the developers recommend [V].
- An optional later "values chat" can use the Card Sort concept (public domain [S]).
- Never ship PVQ/SVS/BPNSFS/RFQ wording.

---

## 4. Stress, coping and support preferences

### Comparison table

| # | Instrument / source | Link | Year | Measures | Items | Licence / usage | Validity | Fit | Ver. |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **Brief COPE** (Carver) | [Carver page](https://www.psy.miami.edu/faculty/ccarver/brief-cope.html), [doi](https://doi.org/10.1207/s15327558ijbm0401_6) | 1997 | 14 coping strategies × 2 items: self-distraction, active coping, denial, substance use, emotional support, instrumental support, behavioural disengagement, venting, positive reframing, planning, humour, acceptance, religion, self-blame | 28 (4-pt) | "You are **welcome to use** all scales … or to choose selected scales … **adapt the language**" [V]. No overall score; examine scales separately [V]. | Widely used; scale-level | **Yellow-Green.** Use the 14-category *taxonomy* to code open answers. Don't administer 28 items. | [V] |
| 2 | **COPE** (full; Carver, Scheier, Weintraub) | [doi](https://doi.org/10.1037/0022-3514.56.2.267) | 1989 | 15 strategies | 60 | Same author site [S] | Strong | Too long | [S] |
| 3 | **PSS-10 / PSS-4** (Cohen, Kamarck, Mermelstein) | [doi](https://doi.org/10.2307/2136404); [Mind Garden](https://mindgarden.com/132-perceived-stress-scale) | 1983 | Perceived stress, past month | 10 / 4 | Free for research and non-profit education; "**profit making ventures … require special permission and a nominal charge**" (FAQ dated 2014) [S] | Strong | **Red** verbatim. The construct can be asked as one Stiti-original optional item. | [S] |
| 4 | **Single-item stress** (Elo, Leppänen, Jahkola) | [doi](https://doi.org/10.5271/sjweh.752) | 2003 | Overall stress | 1 | [U] | Valid vs. multi-item measures in occupational samples | Construct OK; Stiti-original wording | [R] |
| 5 | **Ways of Coping** (Folkman & Lazarus) | Mind Garden (commercial) | 1988 | 8 coping scales | 66 | Proprietary [R] | Classic | Red | [R] |
| 6 | **CISS** (Endler & Parker) | MHS (commercial) | 1990 | Task, emotion, avoidance coping | 48 | Proprietary [R] | Good | Red | [R] |
| 7 | **ERQ** (Gross & John) | [doi](https://doi.org/10.1037/0022-3514.85.2.348) | 2003 | Reappraisal vs suppression | 10 | Believed freely available for research [U] | Strong | Construct only (low priority) | [R]/[U] |
| 8 | **MSPSS** (Zimet et al.) | [doi](https://doi.org/10.1207/s15327752jpa5201_2) | 1988 | Perceived support from family, friends, significant other | 12 | Free with citation (author's site) [U] | Strong, used in India [R] | Already covered by "people" question | [R]/[U] |
| 9 | **Optimal matching** (Cutrona & Russell 1990; Cutrona & Suhr 1992) | [doi](https://doi.org/10.1177/009365092019002005) | 1990/1992 | Support type should match the stressor: controllable → informational/instrumental; uncontrollable → emotional | theory | n/a | Mixed but influential [S] | **Core logic** for choosing listen vs plan | [S] |
| 10 | **Invisible support** (Bolger, Zuckerman, Kessler) | [doi](https://doi.org/10.1037/0022-3514.79.6.953) | 2000 | Visible support can cost the recipient (feeling indebted or inadequate); "invisible" support works best | diary study | n/a | Replicated in several diary studies [S] | **Supports** "ask before advising" and low-key help | [S] |
| 11 | **Advice receptiveness** (Feng & MacGeorge 2006; MacGeorge et al. 2004; Goldsmith & Fitch 1997) | Southern Commun J (2006), doi not verified | 1997–2010 | Advice is welcome when solicited, from a trusted source, politely framed, and after emotional support | theory/experiments | n/a | Communication literature | **Supports** "listen first, then ask whether they want ideas" | [R] |
| 12 | **Personality–coping meta-analysis** (Connor-Smith & Flachsbart) | [doi](https://doi.org/10.1037/0022-3514.93.6.1080) | 2007 | E → support-seeking and problem-solving; N → wishful thinking, withdrawal, emotion-focused coping; C → problem-solving | 165 samples | n/a | Meta-analysis (small to moderate r) | Supports **weak priors** for support mode before the user says otherwise | [R] |
| 13 | **PHQ-4** (Kroenke et al.) | [doi](https://doi.org/10.1176/appi.psy.50.6.613) | 2009 | Anxiety and depression screen | 4 | Free [R] | Strong | **Exclude**: clinical screening is out of scope (non-diagnostic product) | [R] |
| 14 | **DASS-21** (Lovibond & Lovibond) | UNSW DASS site | 1995 | Depression, anxiety, stress | 21 | Described as public domain on the author site [R]/[U] | Strong | **Exclude**: clinical | [R] |
| 15 | **Brief Resilience Scale** (Smith et al.) | [doi](https://doi.org/10.1080/10705500802222972) | 2008 | Bounce-back ability | 6 | [U] | Good | Not needed | [R] |

### Asking without being clinical
- Use everyday frames ("rough day", "kharab din"), not "stress symptoms" or "anxiety". Ask **observable signals** ("what do you do or say") rather than feelings scales.
- Ask permission before the block and offer "skip this part". Tourangeau & Yan (2007) [R]: sensitive questions get more honest answers with privacy assurances and self-administration.
- Schober et al. (2015) [V]: **text yielded more sensitive disclosure than voice**, with both human and automated interviewers. Stiti should say: "You can also type this one if that's easier."
- Never score the answers into a "stress level" in the intake. Store them as *the user's own words* plus a category code.

### Recommendation
Three questions in a gated block:
1. **Personal stress markers** (open). Adds user-specific cues to the stress detector.
2. **Support preference** (4-way choice: listen / plan / joke or distraction / space). Maps to response mode, and directly encodes optimal matching and invisible support.
3. **Own coping** (open, optional). Coded with Brief COPE categories.

An optional baseline "how stressful has the last month felt, 1–5" (Stiti-original, PSS-construct) is **off by default**.

---

## 5. Communication preferences and intake conversation design

### Comparison table

| # | Source | Link | Year | Finding / mechanism | Fit for Stiti intake | Ver. |
|---|---|---|---|---|---|---|
| 1 | **Motivational Interviewing, OARS** (Miller & Rollnick, *MI* 3rd ed.) | Guilford | 2013 | Open questions, Affirmations, Reflections, Summaries. "Ask–offer–ask" (elicit–provide–elicit) before giving information or advice. | Short reflections between answers ("Got it, mornings are rough."). **Summary read-back at the end.** Ask before advising in support mode. | [R] |
| 2 | **Aron et al. 36 questions** (graded self-disclosure) | [doi](https://doi.org/10.1177/0146167297234003) | 1997 | Escalating, reciprocal self-disclosure builds closeness in about 45 min | Order from easy → personal. Stiti can make tiny reciprocal disclosures ("I'm a night owl too, I run on your Mac's schedule"). Not the questions themselves; the intake is not intimacy-building. | [R] |
| 3 | **Self-disclosure reciprocity** (Sprecher et al. 2013; Collins & Miller 1994 meta) | J Exp Soc Psychol; Psychol Bull 116(3) | 1994/2013 | Disclosure begets disclosure and liking | Supports brief Stiti self-disclosure | [R] |
| 4 | **Xiao et al. "Tell Me About Yourself"** | [arXiv](https://arxiv.org/abs/1905.10700), TOCHI 27(3) | 2020 | About 600 participants. A chatbot that asks open-ended questions, probes and handles small talk got more engagement and more **informative, relevant, specific, clear** answers than Qualtrics [S] | Open questions with one active-listening follow-up beat form-style questions | [S] |
| 5 | **Kim, Lee & Gweon** (chatbot vs web surveys) | [doi](https://doi.org/10.1145/3290605.3300316), [PDF](https://soominkim.github.io/project/CHI2019_KIM_Comparing.pdf) | 2019 | Chatbot respondents gave more differentiated answers and satisficed less; 2×2 with formal/casual style [S] | A conversational, casual style is worth it for Likert items | [S] |
| 6 | **Lee, Yamashita, Huang, Fu "I Hear You, I Feel You"** | [doi](https://doi.org/10.1145/3313831.3376175) | CHI 2020 | 47 participants over 3 weeks. Chatbot self-disclosure produced deeper user self-disclosure, intimacy and enjoyment [S] | Supports progressive, multi-day profiling and small reciprocal disclosures | [S] |
| 7 | **Ho, Hancock & Miner** | [doi](https://doi.org/10.1093/joc/jqy026) | 2018 | Emotional disclosure to a chatbot had psychological benefits similar to disclosure to a human | Justifies an empathic tone in the stress block | [R] |
| 8 | **Lucas et al. "It's only a computer"** | [doi](https://doi.org/10.1016/j.chb.2014.04.043) | 2014 | People disclosed more to a virtual human they believed was automated (less fear of judgement) | Say "I don't judge; this stays on your Mac" | [R] |
| 9 | **Schober, Conrad et al.** (text vs voice) | [doi](https://doi.org/10.1371/journal.pone.0128337) | 2015 | Text produced more precise answers (fewer rounded numbers), more differentiation and **more sensitive disclosure** than voice [V] | Offer typing for sensitive questions. Expect rounded times by voice ("around 11"). | [V] |
| 10 | **Tourangeau & Yan, "Sensitive questions in surveys"** | [doi](https://doi.org/10.1037/0033-2909.133.5.859) | 2007 | Self-administration, privacy and neutral wording reduce misreporting | Gate plus privacy assurance before the stress block | [R] |
| 11 | **Krosnick satisficing** | [doi](https://doi.org/10.1002/acp.2350050305) | 1991 | Fatigue and low motivation → "don't know", acquiescence, non-differentiation | Keep it short, vary formats, put the 5-item block mid-way, not at the end | [R] |
| 12 | **Dillman, Smyth & Christian, Tailored Design** | Wiley, 4th ed. | 2014 | Begin with easy, salient, non-threatening questions; put sensitive ones later; explain why you ask | Order: name → people → rhythm → likes → … → stress | [R] |
| 13 | **Woebot RCT** (Fitzpatrick, Darcy, Vierhile) | [doi](https://doi.org/10.2196/mental.7785) | 2017 | Brief, friendly onboarding with explicit limits ("not a therapist") | Copy the honesty pattern: "I'm not a doctor or therapist" | [R] |
| 14 | **Woebot bond** (Darcy et al.) | [doi](https://doi.org/10.2196/27868) | 2021 | Working-alliance scores comparable to human therapy within days | Warmth and consistency matter more than intake length | [R] |
| 15 | **Wysa** (Inkster, Sarda, Subramanian) | [doi](https://doi.org/10.2196/12106) | 2018 | Indian-built empathetic chatbot; engaged users improved more | Indian cultural precedent; a non-clinical framing works | [R] |
| 16 | **Relational agents** (Bickmore & Picard) | [doi](https://doi.org/10.1145/1067860.1067867) | 2005 | Social dialogue, continuity and remembering user details build long-term relationships | Recall intake facts naturally later ("How was Priya's wedding?") | [R] |
| 17 | **Conversational agents in healthcare** (Laranjo et al., systematic review) | [doi](https://doi.org/10.1093/jamia/ocy072) | 2018 | Safety issues arise in unconstrained NLU; constrained flows are safer | Rule-based intake is a strength, not a weakness | [R] |

### Design rules derived
1. **Consent and expectations first:** time ("about 5 minutes"), controls ("skip", "pause", "go back"), privacy ("stays on this computer"), and the role limit ("I'm not a doctor").
2. **Order:** easy facts → fun → quick-fire Likert (mid-way, when motivation is still high) → values → communication → **permission gate** → stress/support → boundaries → **summary read-back**.
3. **Voice ergonomics:** at most 3 options per prompt where possible (the support question has 4, so repeat them once if there is no answer). Repeat the anchors before the quick-fire round. Accept rounded times.
4. **Active listening:** one short reflection after each open answer (MI). Probe once at most, and only if the answer is under 3 words and the question is core (Xiao 2020).
5. **Skip semantics:** "skip / pass / chhodo / aage" → store `skipped`. **Don't re-ask a skipped sensitive item for 30 days.** Repeated skips on a topic make it a boundary.
6. **Pause and resume:** this already exists in `src/stiti/brain/onboarding.py` (`PAUSE_RX`, state file). Reuse it.
7. **End with a summary:** read back 4–6 items, flag guesses as guesses, and ask "anything wrong or to forget?" (MI Summary plus scrutable user modelling).

---

## 6. Inferring traits and preferences from everyday language without an LLM

### Comparison table

| # | Tool / study | Link | Year | What it does | Licence | Accuracy / evidence | Fit (local, Hinglish) | Ver. |
|---|---|---|---|---|---|---|---|---|
| 1 | **LIWC-22** (Boyd, Ashokkumar, Seraj, Pennebaker) | [liwc.app](https://www.liwc.app) | 2022 | ~100 psychological word categories | **Proprietary**, paid dictionary | Large literature; trait correlations small | Red; English only | [R] |
| 2 | **Empath** (Fast, Chen, Bernstein) | [GitHub](https://github.com/Ejhfast/empath-client), [arXiv](https://arxiv.org/abs/1602.06979) | 2016 | ~200 topic/emotion categories built from embeddings and crowd validation; user-definable categories | **MIT** [V] | r = .906 with LIWC across overlapping categories [S] | Green; English only. Hinglish needs custom seed lists. | [V]/[S] |
| 3 | **NRC EmoLex** (Mohammad & Turney) | [page](https://saifmohammad.com/WebPages/NRC-Emotion-Lexicon.htm) | 2013 | 14,182 words × 8 emotions + 2 sentiments; Google-translated into 100+ languages incl. Hindi [V] | Non-commercial research only; "**Do not redistribute**"; commercial licence for a fee [V] | Widely used | **Red for bundling.** At most, an optional user-run download script. Machine translations are noisy [V]. | [V] |
| 4 | **VADER** (Hutto & Gilbert) | [GitHub](https://github.com/cjhutto/vaderSentiment) | 2014 | Rule-based sentiment for social text (intensifiers, negation, "but", caps) | **MIT** [V] | Strong on English social media | Green. Extend the lexicon with Hinglish tokens ("bakwaas", "mast", "bekaar", "zabardast"). | [V] |
| 5 | **AFINN** (Nielsen) | [GitHub](https://github.com/fnielsen/afinn), [arXiv](https://arxiv.org/abs/1103.2903) | 2011 | Word valence −5…+5 | **Apache-2.0** repo [V] | Simple, decent | Green; simpler than VADER | [V] |
| 6 | **SentiWordNet 3.0** (Baccianella et al.) | [GitHub](https://github.com/aesuli/SentiWordNet) | 2010 | Synset positivity/negativity | Not stated in the GitHub API [U] | Noisy | Skip | [U] |
| 7 | **Pennebaker & King** (LIWC and personality) | [doi](https://doi.org/10.1037/0022-3514.77.6.1296) | 1999 | Linguistic styles are stable and related to traits | n/a | Correlations small (≈ .1–.2) | Evidence of *limits* | [R] |
| 8 | **Yarkoni** (personality in 100,000 words) | [doi](https://doi.org/10.1016/j.jrp.2010.04.001) | 2010 | Word-level Big Five correlations in blogs | n/a | Small effects; needs large text volume | Limits | [R] |
| 9 | **Schwartz et al.** (open-vocabulary, 75k Facebook users) | [doi](https://doi.org/10.1371/journal.pone.0073791) | 2013 | Data-driven words and phrases linked to traits, age and gender | n/a | Better than closed vocabularies at scale | Needs training data Stiti lacks | [R] |
| 10 | **Park et al.** (automatic personality assessment) | [doi](https://doi.org/10.1037/pspp0000020) | 2015 | Model trained on 66,732 users, tested on 4,824 | n/a | Converges with self and informant reports, stable over 6 months [S]; average r about .38 [R] | Not reproducible for one user offline | [S]/[R] |
| 11 | **Mairesse et al.** (personality from conversation and text) | [doi](https://doi.org/10.1613/jair.2349) | 2007 | LIWC/MRC features → Big Five, incl. spoken (EAR) data | n/a | Modest; best for E (observer ratings) | Limits | [R] |
| 12 | **Azucar, Marengo, Settanni** (meta-analysis) | [doi](https://doi.org/10.1016/j.paid.2017.12.018) | 2018 | Digital footprints → Big Five | n/a | r ≈ .30–.40; similar across traits; better with multiple footprint types [S] | **Ceiling even with big data** | [S] |
| 13 | **Mehl, Gosling, Pennebaker** (EAR, everyday spoken language) | [doi](https://doi.org/10.1037/0022-3514.90.5.862) | 2006 | Personality in everyday talk | n/a | Some cues valid (e.g., E ↔ talkativeness) | Talk *amount* is a weak E cue Stiti could log | [R] |
| 14 | **Kosinski, Stillwell, Graepel** (private traits from Likes) | [doi](https://doi.org/10.1073/pnas.1218772110) | 2013 | Sensitive attributes predictable from digital traces | n/a | Accurate for some attributes | **Ethics warning** (see §7) | [R] |
| 15 | **SentiMix SemEval-2020 Task 9** (Patwa et al.) | [arXiv](https://arxiv.org/abs/2008.04277) | 2020 | About 20k Hinglish tweets with sentiment and word-level language tags [S] | Paper CC BY; dataset licence not found [U] | Benchmark | Use only as an *evaluation* source if the licence allows; don't bundle | [S]/[U] |
| 16 | **EmbeddingGemma-300M** (already in Stiti) | `src/stiti/embed.py` | 2025 | Multilingual sentence embeddings, 768-d, about 7 ms/query | Gemma Terms of Use | Romanized-Hinglish quality **unmeasured** [U] | Prototype-similarity classifier for key-thing categories | local |

### Accuracy limits (why Stiti should not infer Big Five from text)
- Even with thousands of words and big training sets, text → trait correlations peak around r ≈ .3–.4 (Azucar 2018 [S]; Park 2015 [S]/[R]). That is about 10–15% shared variance.
- For one user with a few hundred voice turns and no labelled data, a lexicon-based Big Five estimate would be mostly noise. It is also biased for code-mixed Hinglish, because LIWC-style dictionaries are English.
- **Decision:** use text **only** for (a) explicit statements of preferences and facts, and (b) *momentary* affect (VADER/AFINN plus the existing emotion model) as a state cue, never a trait.
- Trait estimates come only from self-report items, plus small nudges from **revealed behaviour** that matches the adaptation itself (e.g., ignoring check-ins → fewer check-ins). This is safer and more accurate.

### Pattern-based extraction (English + Hinglish), no LLM
Run on each final user utterance after STT. Normalise first: lowercase; map common spellings (h/hai/he → hai, nhi/nai/nahin → nahi, bohot/bahut/bhot → bahut, acha/accha/achha → accha, pasand/psnd → pasand); strip fillers (yaar, na, matlab, like, basically).

| Category | English patterns (regex sketch) | Hinglish patterns (regex sketch) | Output |
|---|---|---|---|
| Like | `\bi (really |totally )?(love|like|enjoy|adore|am into|'m into)\s+(?P<x>.+)`; `\bi'?m (a (big|huge) )?fan of (?P<x>.+)`; `\bmy fav(ou?rite)? (?P<k>\w+) is (?P<x>.+)`; `\bnothing beats (?P<x>.+)` | `mujhe (?P<x>.+?) (bahut |kaafi |sach mein )?(pasand|accha lag(ta|ti|te)|pyaar) (hai|h)\b`; `(?P<x>.+?) mera fav(ourite)? (hai|h)\b`; `mera fav(ourite)? (?P<k>\w+) (?P<x>.+?) (hai|h)\b`; `main (?P<x>.+?) ka (bada )?fan (hoon|hu)` | `like(x, strength)` |
| Dislike | `\bi (really )?(hate|can'?t stand|dislike|don'?t like|am not (a fan of|into))\s+(?P<x>.+)`; `(?P<x>.+) (annoys|irritates|bugs) me` | `mujhe (?P<x>.+?) (bilkul |zara bhi )?(pasand nahi|accha nahi lag(ta|ti)|se nafrat|se chid(h)?) (hai|h)?`; `(?P<x>.+?) (bakwaas|bekaar|irritating) (hai|h|lagta)` | `dislike(x, strength)` |
| Routine | `\bi (usually|always|normally|generally) (?P<act>wake|sleep|eat|go to gym|work out|...) (at|around) (?P<t>TIME)`; `\bevery (morning|evening|night|day) i (?P<act>.+)` | `main (roz|daily|har roz|aksar) (?P<t>TIME)? ?(baje)? (?P<act>uth|so|kha|gym ja)(ta|ti|te) (hoon|hu|hai)`; `subah|shaam|raat (?P<t>TIME) baje` | `routine(act, time, days)` |
| Person | `\bmy (?P<rel>sister|brother|mom|dad|wife|husband|partner|boss|friend|best friend|...) (?P<name>[A-Z]\w+)` | `(meri|mera|mere) (?P<rel>behen|bhai|mummy|papa|dost|boss|wife|husband|didi|bhaiya) (?P<name>\w+)` | `person(name, relation)` (existing `parse_people`) |
| Preference about Stiti | `\b(don'?t|stop|never) (talk so much|interrupt|lecture|remind me (about|to) (?P<x>.+))`; `\b(keep it|be) (short|brief)` | `(itna|zyada) mat bolo`; `chhota (bolo|rakho)`; `(baar baar|roz) yaad mat dilao` | Directive (high confidence) |
| Explicit memory | `\bremember (that|this)\b`; `\bnote (that|down)\b` | `yaad rakh(na|o)`; `note kar lo` | Store immediately, confidence 0.95 |
| Boundary | `\bdon'?t (ask|talk) (me )?about (?P<x>.+)` | `(?P<x>.+?) (ke baare mein|ki) baat mat (karo|karna)` | Boundary rule |
| Stress marker (own) | user's own Q15 phrases + `\b(so tired|exhausted|done with|can'?t (deal|handle))` | `(thak gaya|thak gayi|thaka hua|pak gaya|dimaag kharab|tension (hai|ho rahi))` | State cue (P2) |

**Guards.** Negation scope ("I don't hate it" ≠ dislike) and question form ("do you like X?" is not a statement about the user). Third-person subjects ("my sister loves X" → `like` attached to the *sister*). Hedges ("kinda", "thoda") → strength 0.5. Sarcasm is not handled; low confidence and confirmation catch it.

**Embedding prototype router (no LLM).** For utterances that no regex matched:
- Compute cosine similarity to about 15–30 prototype sentences per category (English and Hinglish), e.g., like: "I really enjoy filter coffee", "mujhe biryani bahut pasand hai"; routine: "I go to the gym every morning", "main roz 6 baje uthti hoon".
- If max similarity is ≥ τ_c and the margin over the second-best category is ≥ 0.05 → candidate key thing. Extract the object with the category's loose regex, or the noun span after the verb.
- **Thresholds τ_c must be calibrated** on a hand-labelled set of about 300 utterances (half Hinglish) to reach precision ≥ 0.9 for auto-store, and 0.7–0.9 for "ask to confirm". EmbeddingGemma's romanized-Hinglish quality is unknown [U]. Measure it before shipping.

**Confidence and consolidation.**
- Explicit "remember" or regex like/dislike with a first-person subject: 0.85.
- Embedding-only: 0.5.
- Seen again on a different day: +0.15.
- Contradicted: open a new temporal fact and close the old one. Never average.
- The nightly job (`brain/sleep.py`) batches candidates scoring 0.5–0.85 into **at most one confirmation question per day**: "Quick check: you mentioned you can't stand early meetings. Should I remember that?"
- Unconfirmed inferred items expire after 90 days.

---

## 7. Ethics and safety

### Comparison table

| # | Source | Link | Year | Key requirement / risk | Stiti design consequence | Ver. |
|---|---|---|---|---|---|---|
| 1 | **Belmont Report** | [HHS](https://www.hhs.gov/ohrp/regulations-and-policy/belmont-report/index.html) | 1979 | Respect for persons (informed consent), beneficence, justice | Consent screen; voluntary; benefits explained | [R] |
| 2 | **APA Ethics Code §9** (assessment) | [APA](https://www.apa.org/ethics/code) | 2017 | Use assessments for appropriate purposes, explain results, note limitations | Never present intake scores as a psychological assessment; explain limits | [R] |
| 3 | **ITC Guidelines for Translating and Adapting Tests** (2nd ed.) | [intestcom.org](https://www.intestcom.org) | 2017 | Translated items need equivalence evidence | Mark Hinglish items unvalidated | [R] |
| 4 | **GDPR Art. 9** (special categories incl. health) and **Art. 22** (automated decisions) | [EUR-Lex 2016/679](https://eur-lex.europa.eu/eli/reg/2016/679/oj) | 2016 | Health data needs explicit consent; profiling transparency | P2 tier for health and mental-health data; profile visibility. Local, personal use may fall under the household exemption [R], but design as if it doesn't. | [R] |
| 5 | **India DPDP Act 2023** (and DPDP Rules 2025) | [MeitY](https://www.meity.gov.in/data-protection-framework) | 2023 | Notice and consent, purpose limitation, erasure rights, children's data (verifiable parental consent) | Clear notice; "forget everything" command; skip personality profiling if the user says they are under 18 | [R]/[U] (Rules date not re-verified) |
| 6 | **EU AI Act** Art. 5 (prohibited: manipulative techniques, exploiting vulnerabilities, emotion recognition at work and in education) and Art. 50 (transparency) | [EUR-Lex 2024/1689](https://eur-lex.europa.eu/eli/reg/2024/1689/oj); [FPF explainer](https://fpf.org/blog/red-lines-under-eu-ai-act-unpacking-the-prohibition-of-emotion-recognition-in-the-workplace-and-education-institutions/) | 2024 | No manipulation that exploits vulnerabilities. Emotion recognition is prohibited at work and in schools and high-risk elsewhere [S]. Disclose emotion recognition. | Stiti tells users it reads tone of voice. No emotion inference if deployed in employer or school settings. No vulnerability-exploiting nudges. | [S] |
| 7 | **Scrutable user models** (Kay & Kummerfeld) | [TiiS 2012 overview](https://www.bohrium.com/paper-details/creating-personalized-systems-that-people-can-scrutinize-and-control/813259710495981569-2711) | 2001–2012 | Users should see what is held, how it was gathered and how it is used, and control it [S] | "What do you know about me?" plus the USER.md "Key things" section with source, confidence and "why" | [S] |
| 8 | **Online manipulation** (Susser, Roessler, Nissenbaum) | [doi](https://doi.org/10.14763/2019.2.1410) | 2019 | Manipulation = hidden influence that exploits vulnerabilities and bypasses agency | Adaptations must be disclosable ("I said it gently because you told me…") and serve the user's own goals | [R] |
| 9 | **Privacy in psychological targeting** (Matz, Appel, Kosinski) | [doi](https://doi.org/10.1016/j.copsyc.2019.08.010) | 2020 | Trait inference enables persuasion at scale; consent is often illusory | No trait inference from text; no third-party use | [R] |
| 10 | **Generative AI personalised persuasion** (Matz et al.) | [doi](https://doi.org/10.1038/s41598-024-53755-0) | 2024 | Trait-matched messages from an LLM were more persuasive | Even phrasing LLMs must not get raw trait scores; send generic style directives only | [R] |
| 11 | **Barnum/Forer effect** | [doi](https://doi.org/10.1037/h0059240) | 1949 | People accept vague personality feedback as accurate | Don't "reveal" personality results dramatically; show tentatively with "your answers suggest…" | [R] |
| 12 | **Burr, Cristianini, Ladyman** (intelligent agents and users) | [doi](https://doi.org/10.1007/s11023-018-9479-0) | 2018 | Agent–user interaction can shade into persuasion or coercion | Log every adaptation; the user can turn adaptations off | [R] |
| 13 | **Kosinski et al. 2013** | [doi](https://doi.org/10.1073/pnas.1218772110) | 2013 | Sensitive traits (orientation, religion, politics) are predictable from traces | **Ban list:** never infer religion, caste, sexual orientation, politics, health conditions, or ethnicity. Store them only if the user says them explicitly, in P2. | [R] |

### Rules for Stiti (implementable)
1. **Consent.** Opening consent plus a separate gate before the stress block. Skipping is free. Skipped sensitive items are not re-asked for 30 days. "Pause" resumes later.
2. **No diagnosis.**
   - No clinical words in outputs ("anxiety", "depression", "neurotic", "disorder").
   - Trait names in the UI are friendly and bidirectional: *Social energy* (E), *Warmth* (A), *Planning style* (C), *Calm under pressure* (N, reverse-scored so higher = calmer), *Curiosity and imagination* (O).
   - Never show numbers by voice. In USER.md: "leans …" plus source plus confidence.
3. **Crisis safety.**
   - If self-harm or suicide phrases occur at any time (regex in English and Hinglish, e.g., "khud ko khatam", "marna chahta/chahti", "kill myself"), stop the intake and give a calm, supportive message plus a **configurable helpline list**. India: Tele-MANAS 14416 / 1-800-891-4416 ([R]; verify before shipping). Default to the country locale.
   - The intake never asks about self-harm.
4. **Privacy tiers** (matching the existing `privacy` 0/1/2 in `engine.py`):
   - P1: name, people, rhythm, likes, values, personality leanings, communication preferences.
   - **P2: stress markers, coping (esp. substance use and religion-as-coping), support preferences, boundaries that reveal health or trauma.**
   - P2 content never goes to a cloud LLM. Only **generic derived directives** may ("use a gentle tone", "offer to listen before suggesting fixes"). Never "user gets anxious" or "user drinks when stressed".
5. **Tentative, correctable labels.**
   - Every item stores `source ∈ {told_me, quick_fire, inferred_text, inferred_behaviour}`, `confidence`, `first_seen`, `last_confirmed` and `why`.
   - "That's wrong" / "galat hai" → immediate correction with a new temporal fact.
   - User edits to USER.md win (already a house rule).
6. **Anti-manipulation.**
   - Adaptations may only (a) change tone, length or timing, or (b) help with goals *the user stated*.
   - No adaptations to increase engagement or usage time. No scarcity or urgency tricks. No pressure framing for users who lean low on Calm.
   - Every proactive message logs `adaptation_reason`. "Why did you say it like that?" reads it back.
   - Global switch: "Talk to me the same way as anyone else" disables trait-based framing.
7. **No stereotyping.** No inference from gender, age, region, accent, religion or caste. Only within-person comparisons, no population norms.
8. **Data rights.** "What do you know about me?", "Forget X", "Forget everything from the intake", and export (USER.md is already human-readable).

---

## 8. Turning the profile into assistant adaptations

### Evidence table (personalisation and persuasion literature)

| # | Study | Link | Year | Finding | Effect size / strength | Implication | Ver. |
|---|---|---|---|---|---|---|---|
| 1 | **Hirsh, Kang & Bodenhausen** | [doi](https://doi.org/10.1177/0956797611436349) | 2012 | 324 participants. Ads framed to match the dominant trait were rated more effective (E: excitement/social; N: "safe and secure"; A: community/family; C: efficiency/goals; O: creativity/intellect) [V] | Self-report ratings, not behaviour [V] | Trait-matched *framing* is plausible but light | [V] |
| 2 | **Matz, Kosinski, Nave, Stillwell** | [doi](https://doi.org/10.1073/pnas.1710966114) | 2017 | Three field experiments; trait-matched Facebook ads → more clicks and purchases [S] | Small absolute effects [R] | Works at scale, which is the manipulation risk | [S] |
| 3 | **Eckles, Gordon & Johnson** (critique) | [doi](https://doi.org/10.1073/pnas.1805363115) | 2018 | The ad platform's delivery optimisation confounds the field results [S] | Contested | Don't over-trust trait targeting | [S] |
| 4 | **Noar, Benac & Harris** (meta-analysis of tailored health messages) | [doi](https://doi.org/10.1037/0033-2909.133.4.673) | 2007 | Tailoring improves health behaviour change; 57 studies, N = 58,454 | **r = .074** [V] | Tailoring helps a little. More tailored concepts help more. | [V] |
| 5 | **Kaptein et al.** (persuasion profiles) | IJHCS (2015), doi not verified | 2015 | Individual differences in susceptibility to persuasion strategies; explicit vs implicit personalisation | Moderate | Learn per-user what works from behaviour, not only traits | [R] |
| 6 | **Orji, Nacke & Di Marco** (personality-driven persuasive health games) | [doi](https://doi.org/10.1145/3025453.3025577) | 2017 | Different Big Five profiles respond to different persuasive strategies | Survey-based SEM | Weak priors only | [R] |
| 7 | **Halko & Kientz** (personality and persuasive technology) | Persuasive 2010, LNCS 6137 | 2010 | Traits relate to preferred persuasion styles | Exploratory | Weak priors | [R] |
| 8 | **Cesario, Grant & Higgins** (regulatory fit) | [doi](https://doi.org/10.1037/0022-3514.86.3.388) | 2004 | Messages matching promotion or prevention focus feel right and persuade more | Lab; moderate | Gain framing for promotion; "stay on track/avoid slips" framing for prevention | [R] |
| 9 | **Motyka et al.** (regulatory fit meta-analysis) | J Consum Psychol 24(3), doi not verified | 2014 | Fit effects on evaluation, intention and behaviour | Small–moderate | As above | [R] |
| 10 | **Gallagher & Updegraff** (gain vs loss framing meta) | [doi](https://doi.org/10.1007/s12160-011-9308-7) | 2012 | Gain-framed messages are better for *prevention behaviours*. No loss-frame advantage for detection behaviours. | Small | Default to gain framing; loss framing only for prevention-focused users who choose it | [R] |
| 11 | **Gollwitzer & Sheeran** (implementation intentions meta) | [doi](https://doi.org/10.1016/S0065-2601(06)38002-1) | 2006 | If-then plans improve goal attainment | **d ≈ .65** [R] | Everyone gets "when X, then Y". More scaffolding for users who lean low on Planning style. | [R] |
| 12 | **Steel** (procrastination meta) | [doi](https://doi.org/10.1037/0033-2909.133.1.65) | 2007 | Procrastination correlates strongly and negatively with conscientiousness (≈ −.6) and with task aversiveness | Strong [R] | Smaller chunks, earlier first step, and reminders for users who lean low on C | [R] |
| 13 | **Connor-Smith & Flachsbart** (personality and coping meta) | [doi](https://doi.org/10.1037/0022-3514.93.6.1080) | 2007 | E → support-seeking; N → emotion-focused coping and withdrawal; C → problem-solving | Small–moderate | Priors for support mode until the user answers Q16 | [R] |
| 14 | **Mehrotra et al.** (notification receptivity) | [doi](https://doi.org/10.1145/2858036.2858566) | CHI 2016 | Content, sender and modality affect acceptance; personality traits predicted perceived disruption (small N) [S] | Exploratory | Learn receptivity per user. Personality gives at most a weak prior on check-in frequency. | [S] |
| 15 | **Su & Reeve** (autonomy-support meta); **Ng et al.** (SDT in health meta) | [doi](https://doi.org/10.1007/s10648-010-9142-7); [doi](https://doi.org/10.1177/1745691612447309) | 2011/2012 | Autonomy support improves motivation and outcomes | Moderate | **Universal:** offer choices, avoid "you should/must" | [R] |
| 16 | **Cutrona & Suhr; Bolger et al.** | see §4 | 1992/2000 | Match support type; prefer low-key ("invisible") help | Moderate | Support-mode rules | [S] |
| 17 | **May & Hasher; Schmidt et al.** (synchrony effect) | see §2 | 1993/2007 | Performance is better at the chronotype-optimal time | Moderate (lab) | Schedule demanding tasks in the user's peak window | [R] |
| 18 | **Matz et al. 2024** (generative AI persuasion) | [doi](https://doi.org/10.1038/s41598-024-53755-0) | 2024 | LLM-written trait-matched messages persuade more | Moderate | **Risk flag:** keep raw traits away from the LLM "mouth" | [R] |

**Manipulation-risk flag.** Rows 1–3, 5–7 and 18 are the persuasion-profiling literature. The same techniques sell products. In Stiti they may be used **only** for tone, length and timing, or to help with goals the user stated. They must be disclosable and switchable off (§7 rule 6). Trait-matched framing is the *lowest-priority* adaptation because its evidence is weakest and its abuse potential highest.

**Priority of adaptation sources** (highest wins on conflict):
1. **Explicit user statement now** ("not now", "keep it short").
2. **Explicit intake/profile preference** (Q13, Q14, Q16, Q18).
3. **Revealed behaviour** over at least 5 events (ignored nudges, "bas", accepted plans).
4. **Chronotype from the user's own times.**
5. **Personality leanings (Mini-IPIP).**
6. **Values and regulatory focus framing.**
7. Defaults.

---

## 9. The recommended intake: 20 turns, about 5.5–6 min

### 9.1 Opening (consent; not counted)
- **EN:** "Hi! I'd love to get to know you a bit. About 20 quick questions, roughly 5 minutes. Say 'skip' for any question, or 'pause' to stop anytime. Everything stays on this computer, and you can see or change what I learn whenever you want. I'm not a doctor or therapist, just your buddy. Shall we start?"
- **Hinglish:** "Hi! Main aapko thoda jaanna chahti hoon. Around 20 chhote sawaal, lagbhag 5 minute. Koi bhi sawaal 'skip' bol sakte ho, ya 'pause' bolke kabhi bhi ruk sakte ho. Sab kuch isi computer pe rehta hai, aur jo main seekhungi woh aap kabhi bhi dekh ya badal sakte ho. Main doctor ya therapist nahi hoon, bas aapki buddy. Shuru karein?"

Stiti's own verbs use feminine forms ("chahti", "seekhungi") to match the current persona. This should be configurable for forks. User-directed Hinglish uses gender-neutral "…te ho" forms throughout.

### 9.2 Question set

Tier: P1 = personal (local; may inform cloud prompts only as minimal directives); **P2 = most private, never leaves the Mac**.

| # | Chapter | English (spoken) | Hinglish variant | Derived from | Answer → scoring / mapping (rule-based) | Tier | Est. s |
|---|---|---|---|---|---|---|---|
| 1 | Basics | "First, the basics: what should I call you?" | "Pehle basics: aapko kya bulaun?" | Existing onboarding | Name regex (existing `_apply('name')`) → directive `call_me` | P1 | 12 |
| 1b | Basics | "And should I say he, she, or they for you, or just use your name?" | "Aur aapke liye 'he', 'she' ya 'they' bolun, ya bas naam se?" | Inclusive design (needed for open source) | enum {he, she, they, name}; skip → `name`. Replaces hard-coded "him" in prompts and USER.md. | P1 | 8 |
| 2 | Basics | "Who are two or three of the most important people in your life? Like 'Priya, my sister; Arjun, best friend.'" | "Aapki life ke 2–3 sabse important log kaun hain? Jaise 'Priya, meri sister; Arjun, best friend.'" | Social convoy / inner circle (Kahn & Antonucci 1980 [R]) | Existing `parse_people` → `person(name, relation)` facts | P1 | 25 |
| 3 | Rhythm | "On a usual work or college day, roughly when do you fall asleep and when do you wake up?" | "Normal kaam ya college wale din, aap roughly kab sote ho aur kab uthte ho?" | MCTQ construct (own wording) | Time parser (§10.2) → SO_w, WU_w | P1 | 15 |
| 4 | Rhythm | "And on a free day with no alarm, when do you sleep and wake up?" | "Aur chhutti wale din, jab koi alarm nahi hota, tab kab sote aur uthte ho?" | MCTQ construct; MSFsc; social jetlag | → SO_f, WU_f → MSF, MSFsc, social jetlag (§2) | P1 | 12 |
| 5 | Rhythm | "When does your brain feel sharpest: morning, afternoon, evening, or late night?" | "Aapka dimaag sabse tez kab chalta hai: subah, dopahar, shaam, ya raat ko late?" | Self-rated chronotype construct (Loureiro & Garcia-Marques 2015) | enum peak ∈ {morning, afternoon, evening, late_night}; agreement with MSFsc → confidence 0.8, otherwise 0.5 | P1 | 8 |
| 6 | Likes | "Tell me a few things that instantly make your day better: food, music, people, anything." | "Kuch cheezein batao jo turant aapka din accha bana deti hain: khana, gaane, log, kuch bhi." | Positive-activity / savouring idea [R]; rapport | Split on `,`/`and`/`aur` → items. Embedding category {food, music, activity, place, person, other} → `like(x)` at 0.9 | P1 | 20 |
| 7 | Likes | "And what really annoys you? Any pet peeves?" | "Aur kya cheez aapko sabse zyada irritate karti hai?" | Rapport; behaviour constraints | → `dislike(x)` at 0.9. If x matches the Stiti-behaviour lexicon (talking too much, repeating, interrupting, lecturing, "baar baar") → hard directive | P1 | 15 |
| 8 | Quick-fire intro | "Quick-fire round! I'll describe someone in a few words, and you tell me how much that's you: totally, kind of, not sure, not really, or not at all." | "Ab ek quick-fire round! Main ek line bolungi, aap batao kitna aap jaisa hai: bilkul, thoda thoda, pata nahi, zyada nahi, ya bilkul nahi." | Mini-IPIP format adapted to voice | Primes the anchors | n/a | 10 |
| 8a | Quick-fire (E−) | "Keeps in the background." | "Group mein aksar background mein rehte ho." | Mini-IPIP E, reverse-keyed ("Keep in the background.") | Likert parser → 1–5 → 6 − x → E | P1 | 6 |
| 8b | Quick-fire (A+) | "Sympathizes with others' feelings." | "Doosron ki feelings samajhte ho, unke liye humdardi rakhte ho." | Mini-IPIP A+ | → A | P1 | 6 |
| 8c | Quick-fire (C+) | "Gets chores done right away." | "Chhote-mote kaam turant nipta dete ho." | Mini-IPIP C+ | → C | P1 | 6 |
| 8d | Quick-fire (N−) | "Is relaxed most of the time." | "Zyaadatar time relaxed rehte ho." | Mini-IPIP N, reverse-keyed ("Am relaxed most of the time.") | → Calm = x (N = 6 − x) | P1 | 6 |
| 8e | Quick-fire (O+) | "Has a vivid imagination." | "Aapki imagination kaafi tez hai." | Mini-IPIP Intellect/Imagination+ | → O | P1 | 6 |
| 9 | Values | "Two quick this-or-thats. Right now in life, what matters more: stability and security, or freedom and new experiences?" | "Do quick 'ye ya woh'. Abhi life mein aapke liye kya zyada important hai: stability aur security, ya freedom aur naye experiences?" | Schwartz Conservation ↔ Openness to change (own wording) | {A: −1, B: +1, both/depends: 0} → `values.openness_vs_conservation` | P1 | 10 |
| 10 | Values | "And: getting ahead and achieving big things, or looking after people and making things better around you?" | "Aur: aage badhna aur bade goals achieve karna, ya logon ka khayal rakhna aur aas-paas cheezein behtar karna?" | Schwartz Self-enhancement ↔ Self-transcendence (own wording) | {A: −1, B: +1, 0} → `values.transcendence_vs_enhancement` | P1 | 10 |
| 11 | Goals | "What's one thing you're working towards these days?" | "Aajkal aap kis cheez ki taraf kaam kar rahe ho? Koi ek goal?" | Personal strivings (Emmons 1986 [R]); MI | Free text → `goal(text)` at 0.9; embedding domain tag {health, career, study, money, relationships, skill, other} | P1 | 20 |
| 12 | Motivation | "When you chase a goal, what pushes you more: the excitement of what you'll gain, or making sure nothing goes wrong?" | "Jab aap koi goal chase karte ho, toh aapko zyada kya push karta hai: jo milega uska excitement, ya ye ensure karna ki kuch galat na ho?" | Regulatory focus theory (Higgins) (own wording) | {promotion, prevention, both} → framing default | P1 | 10 |
| 13 | Communication | "How should I talk to you: short and to the point, or more chatty? And English, Hindi, or a mix?" | "Main aapse kaise baat karun: short aur to-the-point, ya thoda chatty? English, Hindi, ya mix? Aur 'aap' bolun ya 'tum'?" | User preference (explicit beats inferred) | length ∈ {short ≤ 2 sentences, medium ≤ 4, chatty}; lang ∈ {en, hi, mix}; honorific ∈ {aap, tum} | P1 | 15 |
| 14 | Communication | "How often should I check in on my own: a few times a day, once a day, or only when you call me?" | "Main khud se kitni baar check-in karun: din mein kuch baar, din mein ek baar, ya sirf jab aap bulao?" | Notification receptivity (Mehrotra 2016); autonomy (SDT) | proactivity budget {3/day, 1/day, 0 (user-set reminders only)} | P1 | 10 |
| G | **Gate** | "Next few are a bit more personal, about tough days. They stay in my most private memory and never leave this computer. You can also type them. Okay to go on, or skip this part?" | "Agle 2–3 sawaal thode personal hain, mushkil dinon ke baare mein. Ye mere sabse private memory mein rahenge, is computer se bahar kabhi nahi jaayenge. Chaho toh type bhi kar sakte ho. Chalein, ya ye part skip karein?" | Tourangeau & Yan 2007; Schober 2015 | yes → 15–17; no → mark block skipped (30-day no-re-ask) | n/a | 10 |
| 15 | Stress | "How can I tell you're having a rough day? What do you usually do or say?" | "Mujhe kaise pata chalega ki aapka din kharab chal raha hai? Aise mein aap kya karte ya bolte ho?" | Stress-signature idea; Brief COPE "behavioural" cues | Store verbatim phrases plus normalised tokens → per-user stress-marker lexicon (detector boosts) | **P2** | 20 |
| 16 | Support | "On a rough day, what helps most from me: just listening, helping you make a plan, a joke or a distraction, or giving you some space?" | "Kharab din pe mujhse kya sabse zyada help karega: bas sunna, plan banane mein help, koi joke ya distraction, ya aapko thoda space dena?" | Brief COPE (emotional/instrumental support, planning, humour, self-distraction); optimal matching; invisible support; MI | Ranked `support_mode` ⊂ {listen, plan, lighten, space} (multi-select allowed; first mentioned = primary) | **P2** | 15 |
| 17 | Coping (optional) | "And what do you usually do yourself to feel better?" | "Aur aap khud kya karte ho better feel karne ke liye?" | Brief COPE 14-category taxonomy | Keyword → COPE category (§10.4); substance use → stored P2, **never commented on or nudged unless the user asks** | **P2** | 15 |
| 18 | Boundaries | "Is there anything I should never do or bring up?" | "Koi aisi cheez jo main kabhi na karun, ya kabhi na chhedun?" | Consent / boundaries | → hard `never` directives. Tier P2 if they mention health, trauma, family conflict or religion; else P1. | P1/P2 | 15 |
| 19 | Role | "Last one: what do you want me to be for you: an assistant, a coach, a buddy, or a mix?" | "Last sawaal: aap mujhe kya banana chahte ho: assistant, coach, dost, ya thoda sab kuch?" | Relational agents (Bickmore) | role weights: coach → accountability nudges allowed; buddy → small talk allowed; assistant → task-only | P1 | 10 |
| 20 | Read-back | "Here's what I got: [4–6 items, e.g., 'You're a night owl, sharpest late evening. You like short replies in Hinglish. On rough days you want me to just listen first.'] My guess from the quick round is that you [1 leaning, tentative]. Anything wrong, or anything I should forget?" | "Toh maine ye samjha: [...]. Quick round se mera andaaza hai ki aap [...]. Kuch galat hai, ya kuch bhool jaun?" | MI Summary; scrutable user models | Corrections → new temporal facts. "Forget X" → delete. Silence or "sahi hai" → confirm (+0.1 confidence) | n/a | 30 |

**Counts.** 20 numbered turns, 24 spoken prompts plus opening, gate and quick-fire intro.

### 9.3 Time budget
- Opening 15 s + Q1–7 (12+8+25+15+12+8+20+15) 115 s + quick-fire intro and items 10 + 5×6 = 40 s + Q9–14 (10+10+20+10+15+10) 75 s + gate 10 s + Q15–17 (20+15+15) 50 s + Q18–19 25 s + read-back 30 s.
- That is **about 360 s ≈ 6.0 min**, or about 5.2 min if the optional Q17 and the gated block are short.
- Per-turn estimates assume about 3–5 s of TTS per question, a 5–15 s answer and a 1–2 s acknowledgement. They should be **measured** with the real voice loop (Smart Turn end-of-turn detection adds latency).
- If the run goes over 6.5 min, drop Q17 and Q19 to the drip-feed queue.

### 9.4 After the intake: drip-feed queue (opt-in: "Can I sometimes ask you a quick one?")
At most 1 per day, only in idle moments, never during stress or late at night (per chronotype). Order:
1. Remaining 15 Mini-IPIP items. By day ~15 every trait has 4 items, with 2 positive and 2 negative keys.
2. Workdays per week (refines MSFsc).
3. SDT needs (Stiti-original, §3).
4. TIVI 10 items (Green; pronoun-branched).
5. Meal and exercise times.
6. "Anything about your culture, festivals or routines I should know?" (user-led; stored only if volunteered).

---

## 10. Scoring and parsing details (all rule-based)

### 10.1 Spoken Likert parser (English + Hinglish)
Check in this order (first match wins). Negated phrases must be matched before their positive substrings.

| Score | Phrases |
|---|---|
| 1 | not at all, never, no way, absolutely not, bilkul nahi, bilkul bhi nahi, kabhi nahi, ekdum nahi, zara bhi nahi |
| 2 | not really, not much, rarely, hardly, zyada nahi, itna nahi, nahi yaar, kam hi, mostly not |
| 3 | not sure, depends, sometimes, kabhi kabhi, 50-50, fifty fifty, pata nahi, both, medium, beech mein, kuch kuch |
| 4 | kind of, kinda, mostly, somewhat, pretty much, thoda thoda, haan thoda, kaafi had tak, mostly yes, yeah, haan |
| 5 | totally, definitely, absolutely, 100 percent, exactly me, that's me, bilkul, ekdum, pakka, haan bilkul, sau percent |

- **Fallback:** embed the answer and compare to the anchor phrases. If the margin is < 0.05, re-ask once with two options ("More like 'kind of' or 'not really'?"). If still unclear, score 3 and flag `uncertain`.
- **Elaborated answers** ("only with close friends") get score 3 and the elaboration stored verbatim as context.

### 10.2 Time parser (sleep and wake)
- Digits ("11", "11:30", "1130", "1 am") plus Hindi number words: ek 1, do 2, teen 3, char 4, paanch 5, chhe 6, saat 7, aath 8, nau 9, das 10, gyarah 11, barah 12.
- Fractions: sawa +15 min, saadhe +30, paune −15, dedh = 1:30, dhai = 2:30.
- Markers: subah/morning → AM; dopahar → PM (12–4); shaam → PM (4–8); raat/night → PM if 7–11, AM if 12–5.
- Context default when no marker: **sleep onset** 7–11 → PM, 12–6 → AM. **Wake** 4–11 → AM, 12–2 → PM.
- "after 12", "12 ke baad" → 00:30. "around"/"lagbhag" → exact value, flag `rounded`.
- `dateparser` (BSD) supports Hindi and can serve as a backup [R]. A hand-rolled parser is fine and faster.

### 10.3 This-or-that classifier (Q9, Q10, Q12, Q14, Q16, Q19)
1. Keyword sets per option. Example for Q9: A = {stability, security, stable, secure, settled, safe, sukoon, tikaav}; B = {freedom, new, adventure, explore, change, azaadi, naya}.
2. Both/depends keywords: {both, dono, depends, mix, thoda thoda}.
3. Ordinal cues: "first one / pehla" → A; "second / doosra / last wala" → B.
4. Otherwise compare the embedding of the answer with the option texts (the margin rule as above).
5. If unresolved, re-ask once.

### 10.4 Brief COPE keyword coder (Q17; English + Hinglish)
| COPE category (Carver 1997) | Example cues |
|---|---|
| Emotional support | talk to (friend/mom/someone), call (name), share, baat karta/karti, dost se baat |
| Instrumental support | ask for help/advice, salah leta/leti |
| Planning / Active coping | make a list, plan, sort it out, kaam pe lag jaata/jaati, solve |
| Self-distraction | movie, series, Netflix, reels, music, gaane, games, walk, gym, sleep it off |
| Humour | joke, memes, hasna |
| Positive reframing | look at the bright side, sab theek ho jaayega, positive sochta/sochti |
| Acceptance | let it go, jaane do, it is what it is, chalo theek hai |
| Religion | pray, meditate, puja, namaz, path, mandir, gurudwara, church, bhagwan |
| Venting | rant, cry, rona, gussa nikaal |
| Behavioural disengagement | give up, shut down, chup ho jaata/jaati, kisi se baat nahi |
| Substance use | drink, smoke, cigarette, daaru, sutta (**P2; no judgement; no nudges**) |
| Self-blame / Denial | blame myself, khud ko blame; pretend it's fine (low-confidence codes) |

Coded categories inform the support playbook. For example, if "self-distraction: music" → when the user picks "lighten" on a rough day, Stiti offers their music. Religion-as-coping is P2 and used only if the user brings it up.

### 10.5 Trait estimate and confidence
```
trait_score = mean(item scores answered)               # 1..5, Calm = reversed N
conf = {1 item: 0.30, 2: 0.45, 3: 0.55, 4: 0.65}[n]     # self-report items
conf += 0.02 per consistent behavioural event (cap +0.10); −0.05 per contradiction
label = "leans high" if score >= 4.0 and conf >= 0.3
        "leans low"  if score <= 2.0 and conf >= 0.3
        else "middle / not sure yet"
act_on_trait_only_if conf >= 0.45 and no explicit preference covers the same decision
```

### 10.6 Profile record (stored as facts and directives; mirrored to USER.md "Key things I know")
```json
{"key": "chronotype", "value": {"msf_sc": "04:50", "peak": "evening", "social_jetlag_h": 1.8},
 "source": "told_me", "confidence": 0.8, "privacy": 1,
 "why": "From your sleep times on work vs free days (intake, 2026-11-10)",
 "first_seen": "2026-11-10", "last_confirmed": "2026-11-10", "expires": null}
{"key": "trait.calm", "value": 2.0, "label": "leans low", "source": "quick_fire", "items": ["8d"],
 "confidence": 0.30, "privacy": 1, "why": "You said 'not really' to 'relaxed most of the time'"}
{"key": "support_mode", "value": ["listen", "space"], "source": "told_me", "confidence": 0.9, "privacy": 2}
```

---

## 11. Local psychology guide (signal → interpretation → adaptation)

Confidence: **H** = based on the user's explicit statement, or strong evidence; **M** = moderate evidence or own-times-based; **L** = weak or lab-only evidence, used as a prior only. "Override" says what beats it.

| # | Signal (source) | Interpretation (tentative) | Assistant adaptation | Evidence | Conf. | Overridden by |
|---|---|---|---|---|---|---|
| 1 | Q14 check-in = "only when I call" | Wants low proactivity | Zero unsolicited check-ins; only user-set reminders and alarms | Explicit preference; SDT autonomy | **H** | New explicit statement |
| 2 | Q14 = "few times a day" | Welcomes proactivity | Up to 3/day, inside the awake window, spaced ≥ 2 h | Explicit preference | **H** | Revealed ignores (row 20) |
| 3 | Work-day wake WU_w; free-day WU_f | Body-clock timing | No proactive messages before wake + 45–60 min, or after sleep onset − 60 min (except user alarms) | Sleep inertia (Tassi & Muzet 2000); MCTQ timing | **M–H** | User-set reminder times |
| 4 | MSFsc late and/or peak = evening | Evening type | Morning brief later (e.g., wake + 60 min); suggest focus work in the evening window; avoid "you slept late" judgement | Synchrony effect (May & Hasher; Schmidt 2007); social jetlag (Wittmann 2006) | **M** | Explicit schedule |
| 5 | MSFsc early and/or peak = morning | Morning type | Early brief OK; suggest hard tasks before noon; quieter after ~21:00 | Same | **M** | Explicit schedule |
| 6 | Social jetlag > 2 h | Weekday sleep debt | Protect free-day mornings (no nudges). Optionally (if coach role) offer one gentle sleep-timing tip per month. | Wittmann 2006 [R] | **M** | User declines tips |
| 7 | Q16 = "listen" | Prefers emotional support | On stress: reflect first (OARS), no advice until asked; then "Want ideas, or just want to vent?" | MI; advice receptiveness (Feng & MacGeorge); invisible support (Bolger 2000) | **H** | In-the-moment request |
| 8 | Q16 = "plan" | Prefers instrumental support | On stress: a brief acknowledgement, then 1–3 concrete next steps and an if-then plan | Optimal matching (Cutrona & Suhr); implementation intentions | **H** | If the stressor is uncontrollable (loss, illness), still lead with listening |
| 9 | Q16 = "joke/distraction" | Prefers lightening | Light humour, offer their liked music or activity (Q6/Q17); if distress persists for more than 2 turns, switch to listening | Brief COPE humour and self-distraction | **H** (preference) / M (switch rule) | Severity cues |
| 10 | Q16 = "space" | Prefers solitude | One short "I'm here when you want" message, then silence on that topic for the rest of the day | Explicit preference | **H** | User re-engages |
| 11 | Personal stress markers (Q15) seen ≥ 2 times today, or a negative VADER trend plus the emotion model | Probable rough day (state, not trait) | Switch to the support mode from rows 7–10; shorter replies; postpone non-urgent nudges | User-provided markers; emotion state | **M** | User says "I'm fine" (respect it) |
| 12 | Calm leans low (8d, later 4 N items) | Stress gets to them more easily | Gentler, calmer framing; reassurance; no "you're behind" or deadline-pressure wording; frame reminders as "safety net"; fewer late-evening task nudges | Hirsh 2012 (safety framing for high N) [V]; Connor-Smith & Flachsbart 2007 [R] | **L–M** | Explicit tone preference |
| 13 | Planning style (C) leans low | Structure is harder | Smaller task chunks (≤ 15–25 min first step); "when X, then Y" plans; reminder at the start time, not only the deadline | Steel 2007; Gollwitzer & Sheeran 2006 | **M** (chunking helps everyone; trait sets the degree) | User wants big-picture only |
| 14 | Planning style (C) leans high | Likes structure | Offer full plans, checklists and progress summaries; "efficiency/goal" framing | Hirsh 2012 | **L** | Explicit preference |
| 15 | Social energy (E) leans low | Prefers less social stimulation | Brief, calm check-ins; don't push social plans; text-like brevity | Hirsh 2012 (inverse) [V]; Mehrotra 2016 (weak) [S] | **L** | Q14 answer (always wins) |
| 16 | Social energy (E) leans high | Enjoys interaction | Warmer, more conversational; social or "excitement" framing; mention people from Q2 | Hirsh 2012 [V] | **L** | Q13 length preference |
| 17 | Warmth (A) leans high | Communal orientation; may over-commit | Communal framing ("this helps your family/team"); occasional gentle boundary prompt when they take on many tasks for others | Hirsh 2012 [V] | **L** | Explicit preference |
| 18 | Curiosity (O) leans high | Likes novelty | Vary suggestions, offer "try something new" options, creativity framing | Hirsh 2012 [V] | **L** | Explicit preference |
| 19 | Q12 = promotion | Gain-oriented | Frame nudges as gains ("you'll have Sunday free"); eager strategies | Regulatory fit (Cesario 2004; Motyka 2014) | **L–M** | Global "same as anyone" switch |
| 20 | Q12 = prevention | Avoid-mistakes orientation | Frame as staying on track or avoiding slips ("so nothing piles up"); checklists. **Never fear-based.** | Regulatory fit; gain-frame default (Gallagher & Updegraff 2012) | **L–M** | Same |
| 21 | Q9 openness vs conservation | Value emphasis | Openness → "new options/freedom" framing; Conservation → "stability/routine" framing | Schwartz theory; value-congruent messaging [R] | **L** | Same |
| 22 | Q10 transcendence vs enhancement | Value emphasis | Transcendence → "helps people you care about"; Enhancement → "moves you ahead" | Schwartz; Hirsh 2012 (A ↔ communal) | **L** | Same |
| 23 | Everyone (universal) | Autonomy need | Offer choices ("want to do X now or after lunch?"); avoid "should/must"; give a rationale | Su & Reeve 2011; Ng 2012 | **H** (universal) | n/a |
| 24 | Q13 length = short | Prefers brevity | Cap ≤ 2 sentences by voice; offer "want more?" | Explicit preference | **H** | "Explain in detail" request |
| 25 | Q13 lang = mix / hi; honorific | Language comfort | Reply in the same code-mix; use the chosen aap/tum | Explicit preference; Communication Accommodation Theory (Giles) [R] | **H** | Per-turn language detection |
| 26 | Q7 pet peeve about Stiti behaviour, or "bas/stop" during replies ≥ 3 times in 7 days | Dislikes the behaviour | Hard directive (e.g., shorter answers, no repeats) | Revealed preference | **H** | Explicit reversal |
| 27 | Proactive messages ignored or dismissed in ≥ 3 of the last 5 | Low receptivity now | Halve the proactivity budget for 7 days, then probe once ("Too many check-ins?") | Mehrotra 2016; revealed preference | **M** | Explicit Q14 update |
| 28 | Accepted ≥ 3 plan offers during stress | Plans actually help | Raise "plan" in the support ranking (Beta-Bernoulli count) | Revealed preference | **M** | Explicit preference |
| 29 | Repeated "skip" on a topic | Boundary | Don't raise the topic; don't re-ask for 30+ days | Consent | **H** | User raises it |
| 30 | Q19 role = coach | Wants accountability | Allow follow-up on stated goals (Q11) at agreed times; celebrate progress (affirmations, OARS) | Explicit preference; MI | **H** | "Stop coaching" |
| 31 | Text sentiment negative (VADER/AFINN) alone | Momentary mood only | At most: soften tone for that turn. **Never update traits.** | Lexicon limits (§6) | **L** | Everything above |

---

## 12. Continuous learning after the intake (summary of the pipeline)
1. **Per utterance (< 5 ms regex + about 7 ms embedding):** regex extractors (§6) → candidate key things. Unmatched utterances go to the embedding prototype router.
2. **Explicit commands** ("remember", "yaad rakhna", "forget", "galat hai") → act immediately.
3. **Behaviour counters:** proactive message accepted/ignored, "bas/stop" interruptions, support-mode acceptance, interaction times. Each is a Beta(α, β) per adaptation arm, decayed weekly (factor 0.9).
4. **Nightly consolidation** (existing `brain/sleep.py`): dedupe, temporal supersession, and select the **single** most valuable confirmation question for the next day.
5. **Drift checks:** sleep-time drift (§2); a preference contradicted twice → ask.
6. **Re-check:** every ~6 months offer a 1-minute "refresh" of Q13, Q14 and Q16 (preferences change more than traits).
7. **Everything visible:** "What do you know about me?" reads the top items by category with source words ("you told me", "I noticed", "my guess").

---

## 13. Fit with the existing code (observations only; no files changed)
- `src/stiti/brain/onboarding.py` already has a 10-question, about 3-minute flow with skip/pause/resume, people parsing and directive writing. The proposed intake is a superset. Its questions 1, 4, 5, 9, 10 and 8 map to the new Q1, Q2, Q3/Q4, Q16 and Q18.
- The current wording writes **"Call him …"** (e.g., `_directive(f"Call him “{name}”", …)`). For an open-source "any user" release, this should use the pronoun from Q1b.
- Privacy tiers already exist (`privacy` 0/1/2 in `engine.py`; P2 is kept off the cloud). The P2 mapping in §7 rule 4 fits as-is.
- Embeddings: EmbeddingGemma-300M is multilingual. Romanized-Hinglish routing accuracy must be measured (§6), and there is no data on it yet.

---

## 14. Gaps and open questions
- **Licences not resolved:** BFI-10 item reuse; MEQ/rMEQ/MCTQ verbatim text (thewep.org unreachable, TLS error); RFQ/GRFM; BHI-24; SentiWordNet; SentiMix dataset; ERQ; MSPSS.
  - None of these are needed for the recommended design. Brief COPE commercial use is not explicitly addressed by Carver; only its taxonomy is used.
- **No Indian or Hinglish validation** of Mini-IPIP, TIPI or TIVI wording was verified. All Hinglish items are Stiti translations.
- **Exact psychometric numbers** marked [R] (TIPI retest .72, BFI-10 .75, Steel −.6, Gollwitzer d = .65, Park r ≈ .38) come from memory. Check the PDFs before quoting them publicly.
- **Timing** (5.5–6 min) is an estimate; measure it with the real voice loop.
- **Intake drop-off:** no data on completion rates for 20-turn *voice* intakes. Xiao 2020 and Kim 2019 are text chat. Log completion locally (opt-in) to tune.
- **Helpline numbers** (Tele-MANAS) must be verified before shipping, and should be locale-configurable.
- **Persona gender** for Stiti's own Hinglish verbs should be configurable for forks.

---

## Sources fetched or searched this session (key primary pages)
- IPIP permission: https://ipip.ori.org/newPermission.htm [V]; Mini-IPIP key: https://ipip.ori.org/MiniIPIPKey.htm [V]
- TIPI: https://gosling.psy.utexas.edu/scales-weve-developed/ten-item-personality-measure-tipi/ [V]
- TIVI/TwIVI: https://gosling.psy.utexas.edu/two-short-measures-of-values-tivi-and-twivi/ [V]
- BFI/BFI-2 terms: https://www.ocf.berkeley.edu/~johnlab/bfi.html [V]; BFI-10 MDA article: https://mda.gesis.org/index.php/mda/article/view/2013.013 [S]
- HEXACO terms: https://hexaco.org/hexaco-inventory , https://hexaco.org/nonacademicuse.htm [S]
- CSDT BPNSFS terms: https://selfdeterminationtheory.org/basic-psychological-need-satisfaction-and-frustration-scale/ [S]
- Brief COPE: https://www.psy.miami.edu/faculty/ccarver/brief-cope.html [V]
- PSS terms: https://mindgarden.com/132-perceived-stress-scale ; CMU PSS FAQ https://www.cmu.edu/dietrich/psychology/stress-immunity-disease-lab/scales/.doc/pssfaqs.doc [S]
- MEQ/MCTQ registry: https://www.thoracic.org/assemblies/srn/questionaires/meq.php , https://www.thoracic.org/assemblies/srn/questionaires/mctq.php ; CET: https://www.cet.org/assessment/ [S]
- µMCTQ: https://www.pubmed.gov/31791166/ [S]; single-item chronotype: https://doi.org/10.1016/j.paid.2015.06.022 [S]
- Values Card Sort: https://casaa.unm.edu/assets/inst/personal-values-card-sort-2.pdf , https://motivationalinterviewing.org/node/4481 [S]
- NRC EmoLex terms: https://saifmohammad.com/WebPages/NRC-Emotion-Lexicon.htm [V]
- Empath MIT: https://github.com/Ejhfast/empath-client [V]; VADER MIT: https://github.com/cjhutto/vaderSentiment [V]; AFINN Apache-2.0: https://github.com/fnielsen/afinn [V]
- Xiao et al. 2020: https://arxiv.org/abs/1905.10700 [S]; Kim et al. 2019: https://soominkim.github.io/project/CHI2019_KIM_Comparing.pdf [S]; Lee et al. 2020: https://doi.org/10.1145/3313831.3376175 [S]
- Schober et al. 2015: https://pmc.ncbi.nlm.nih.gov/articles/PMC4465184/ [V]
- Hirsh et al. 2012: https://www.psychologicalscience.org/news/releases/marketing-is-more-effective-when-targeted-to-personality-profiles.html [V]
- Matz 2017 / Eckles 2018: https://pmc.ncbi.nlm.nih.gov/articles/PMC6003367 , https://brgordon1.github.io/publication/2018-psychologically-targeted-ads [S]
- Noar et al. 2007: https://pubmed.ncbi.nlm.nih.gov/17592961/ [V]
- Park et al. 2015: https://www.gsb.stanford.edu/faculty-research/publications/automatic-personality-assessment-through-social-media-language [S]; Azucar et al. 2018: https://iris.unito.it/handle/2318/1774688 [S]
- Woods & Hampson 2005: https://research.aston.ac.uk/en/publications/measuring-the-big-five-with-single-items-using-a-bipolar-response/ [S]; Credé et al. 2012: https://neoacademic.com/2012/03/21/dont-use-abbreviated-personality-measures/ (secondary) [S]
- Mehrotra et al. 2016: https://discovery.ucl.ac.uk/1502364/1/CHI16.pdf [S]
- EU AI Act Art. 5 explainer: https://fpf.org/blog/red-lines-under-eu-ai-act-unpacking-the-prohibition-of-emotion-recognition-in-the-workplace-and-education-institutions/ [S]
- Kay & Kummerfeld scrutable user models: https://ercim.eu/publication/Ercim_News/enw46/kay.html [S]
- SentiMix: https://arxiv.org/abs/2008.04277 [S]
