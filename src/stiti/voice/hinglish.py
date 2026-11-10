"""Hinglish → Kokoro phonemes: Hindi words through espeak `hi`, English words through `en-us` (D22).

Roman Hinglish read with English phonemes sounds foreign ("Aaj ka" → "Ajka", "kaisa raha" → "Kaisar Raha").
espeak `hi` can't read Roman letters (it switches back to English), and rule transliteration (ITRANS) mangles casual
spelling, so: a lexicon of common Roman Hinglish words → Devanagari, everything else stays English. Each run of
same-language words is phonemized in its own language and the pieces are joined into one phoneme string for a
Kokoro Hindi voice. Measured on the M2: round-trip WER 68% → 26%, first clause 262–384 ms
(docs/research/hinglish_voice.md).

Words that are also English (to, do, main, me, hi, the…) follow their context. Hinglish puts English words inside
a Hindi sentence frame (the matrix-language idea), so an ambiguous word is Hindi when its nearest clear neighbour
in the same clause is Hindi.
"""
from __future__ import annotations

import re
import threading

# Roman spellings (space-separated variants) → Devanagari. ~500 everyday words, grouped by kind.
_RAW = """
main mai|मैं  mein|में  mujhe muje|मुझे  mujhko|मुझको  mera|मेरा  meri|मेरी  mere|मेरे  hum|हम  humein hume hamein|हमें
hamara humara|हमारा  hamari humari|हमारी  hamare humare|हमारे  tu|तू  tum|तुम  tumhe tumhein|तुम्हें  tujhe|तुझे
tumhara|तुम्हारा  tumhari|तुम्हारी  tumhare|तुम्हारे  tera|तेरा  teri|तेरी  tere|तेरे  aap ap|आप  aapka|आपका  aapki|आपकी
aapke|आपके  aapko|आपको  woh wo vo voh|वो  yeh|यह  ye|ये  unka|उनका  unki|उनकी  unke|उनके  unko|उनको  unhe unhein|उन्हें
uska|उसका  uski|उसकी  uske|उसके  usko|उसको  use|उसे  us|उस  iska|इसका  iski|इसकी  iske|इसके  isko|इसको  ise|इसे  is|इस
inka|इनका  inki|इनकी  inke|इनके  inko|इनको  sab|सब  sabko|सबको  sabka|सबका  sabki|सबकी  sabhi|सभी  koi|कोई  kuch kuchh|कुछ
kisi|किसी  kaun|कौन  kisko|किसको  kiska|किसका  kiski|किसकी  khud|ख़ुद  apna|अपना  apni|अपनी  apne|अपने  jo|जो  jise|जिसे
kya kia|क्या  kyun kyu kyon kyoon|क्यों  kaise kese|कैसे  kaisa kesa|कैसा  kaisi kesi|कैसी  kab|कब  kahan kaha|कहाँ
kidhar|किधर  kitna|कितना  kitni|कितनी  kitne|कितने  konsa kaunsa|कौनसा  konsi kaunsi|कौनसी
ka|का  ki|की  ke|के  ko|को  se|से  me|में  par|पर  pe|पे  tak|तक  liye|लिए  wala vala|वाला  wali vali|वाली
wale vale|वाले  aur or|और  ya|या  lekin|लेकिन  magar|मगर  kyunki kyuki kyonki|क्योंकि  toh to|तो  bhi|भी  hi|ही
na|ना  nahi nahin nai nhi|नहीं  mat|मत  haan haa han ha|हाँ  ji|जी  accha acha achha achchha|अच्छा  achhi acchi|अच्छी
achhe acche|अच्छे  theek thik|ठीक  sahi|सही  galat|ग़लत  bas|बस  abhi|अभी  ab|अब  phir fir|फिर  jab|जब  tab|तब
agar|अगर  warna varna|वरना  sirf|सिर्फ़  bilkul|बिल्कुल  zaroor jaroor jarur zarur|ज़रूर  shayad|शायद  pakka|पक्का
ekdum|एकदम  bahut bohot bahot bohut|बहुत  zyada jyada|ज़्यादा  kam|कम  thoda|थोड़ा  thodi|थोड़ी  thode|थोड़े
sabse|सबसे  itna|इतना  itni|इतनी  itne|इतने  utna|उतना  waise vaise|वैसे  aise|ऐसे  aisa|ऐसा  jaise|जैसे  jaisa|जैसा
yahan yaha|यहाँ  wahan waha|वहाँ  idhar|इधर  udhar|उधर  upar|ऊपर  neeche niche|नीचे  andar|अंदर  bahar|बाहर
saath sath|साथ  paas|पास  door|दूर  pehle pahle|पहले  baad|बाद  jaldi|जल्दी  dheere dhire|धीरे  turant|तुरंत
hamesha|हमेशा  kabhi|कभी  roz|रोज़  aaj aj|आज  kal|कल  parso parson|परसों  subah|सुबह  shaam sham|शाम  raat|रात
dopahar|दोपहर  din|दिन  hafta|हफ़्ता  hafte|हफ़्ते  mahina|महीना  mahine|महीने  saal|साल  waqt|वक़्त  samay|समय
ghanta|घंटा  ghante|घंटे  baje|बजे  baj|बज  bajkar|बजकर  sawa|सवा  saade sade|साढ़े  paune|पौने  dedh|डेढ़  dhai|ढाई
ek|एक  do|दो  teen|तीन  char chaar|चार  paanch panch|पाँच  chhe che chhah|छह  saat|सात  aath|आठ  nau|नौ  das|दस
gyarah|ग्यारह  barah|बारह  bees|बीस  pachas|पचास  sau|सौ  hazaar hazar|हज़ार  pehla|पहला  pehli|पहली
doosra dusra|दूसरा  doosri dusri|दूसरी  teesra tisra|तीसरा  dono|दोनों  kayi kai|कई  har|हर
hai he|है  hain hein|हैं  ho|हो  hoon hun hu|हूँ  tha|था  thi|थी  the|थे  hoga|होगा  hogi|होगी  honge|होंगे  hona|होना
hota|होता  hoti|होती  hote|होते  hua|हुआ  hui|हुई  hue|हुए  raha|रहा  rahi|रही  rahe|रहे  rehna rahna|रहना
kar|कर  karo|करो  karna|करना  karni|करनी  karne|करने  karta|करता  karti|करती  karte|करते  kiya|किया  kiye|किए
karunga|करूँगा  karungi|करूँगी  karenge|करेंगे  karega|करेगा  karegi|करेगी  karke|करके  kariye|करिए  kijiye|कीजिए
karu karun|करूँ  de|दे  dena|देना  diya|दिया  di|दी  diye|दिए  dunga|दूँगा  dungi|दूँगी  dijiye|दीजिए  dekh|देख
dekho|देखो  dekhna|देखना  dekha|देखा  dekhi|देखी  dekhte|देखते  dekhti|देखती  dekhta|देखता  le|ले  lo|लो  lena|लेना
liya|लिया  li|ली  lunga|लूँगा  lungi|लूँगी  ja jaa|जा  jao|जाओ  jana jaana|जाना  gaya|गया  gayi gai|गई  gaye|गए
jaunga|जाऊँगा  jaungi|जाऊँगी  jayega jaayega|जाएगा  jayegi jaayegi|जाएगी  jaate jate|जाते  jaati jati|जाती
aa|आ  aao|आओ  aana|आना  aaya aya|आया  aayi ayi|आई  aaye aye|आए  aayega|आएगा  aata|आता  aati|आती  aate|आते
bol|बोल  bolo|बोलो  bolna|बोलना  bola|बोला  boli|बोली  bata|बता  batao|बताओ  batana|बताना  bataya|बताया
batati|बताती  batata|बताता  bataun|बताऊँ  sun|सुन  suno|सुनो  sunna|सुनना  suna|सुना  samajh|समझ  samjha|समझा
samjhi|समझी  samjho|समझो  samjhao|समझाओ  soch|सोच  socho|सोचो  socha|सोचा  chal|चल  chalo|चलो  chalna|चलना
chala|चला  chali|चली  chalte|चलते  rakh|रख  rakho|रखो  rakha|रखा  laga|लगा  lagi|लगी  lage|लगे  lag|लग  lagta|लगता
lagti|लगती  lagao|लगाओ  lagana|लगाना  ruk|रुक  ruko|रुको  mil|मिल  milna|मिलना  mila|मिला  mili|मिली  mile|मिले
milte|मिलते  pata|पता  padh|पढ़  padho|पढ़ो  padhna|पढ़ना  padhai|पढ़ाई  likh|लिख  likho|लिखो  likha|लिखा
khana khaana|खाना  khaya|खाया  kha|खा  pi|पी  piyo|पियो  pani paani|पानी  so|सो  sona|सोना  soya|सोया
uth|उठ  utho|उठो  utha|उठा  uthna|उठना  baith|बैठ  baitho|बैठो  chahiye|चाहिए  chahta|चाहता  chahti|चाहती
chahte|चाहते  sakta|सकता  sakti|सकती  sakte|सकते  sake|सके  paya|पाया  yaad|याद  dila|दिला  dilana|दिलाना
dilao|दिलाओ  bhool bhul|भूल  bhoolna|भूलना  chhod chod|छोड़  chhodo chodo|छोड़ो  nikal|निकल  nikla|निकला
pahunch|पहुँच  pahuncha|पहुँचा  wapas vapas|वापस  shuru|शुरू  khatam khatm|ख़त्म  band|बंद  kaam|काम  baat|बात
baatein|बातें  cheez|चीज़  cheezein|चीज़ें  tarah|तरह  matlab|मतलब  sach|सच  jhooth|झूठ  dil|दिल  mann|मन
dimaag dimag|दिमाग़  sehat|सेहत  neend|नींद  thak|थक  thaka|थका  thaki|थकी  thake|थके  pareshan|परेशान
khush|ख़ुश  khushi|ख़ुशी  dukh|दुख  gussa|ग़ुस्सा  dar|डर  pyaar pyar|प्यार  dost|दोस्त  yaar yar|यार  bhai|भाई
behen bahen|बहन  didi|दीदी  bhaiya|भैया  maa|माँ  ghar|घर  log|लोग  logon|लोगों  duniya|दुनिया  desh|देश
shehar|शहर  naukri|नौकरी  paisa|पैसा  paise|पैसे  rupaye rupay|रुपये  sawal|सवाल  jawab|जवाब  kahani|कहानी
gaana|गाना  bada|बड़ा  badi|बड़ी  bade|बड़े  chhota|छोटा  chhoti|छोटी  chhote|छोटे  naya|नया  nayi|नई  naye|नए
purana|पुराना  purani|पुरानी  mushkil|मुश्किल  aasan asaan|आसान  zaroori jaruri|ज़रूरी  khaas|ख़ास  sundar|सुंदर
pyara|प्यारा  pyari|प्यारी  mast|मस्त  badhiya|बढ़िया  bekaar bekar|बेकार  saaf|साफ़  poora pura|पूरा  poori puri|पूरी
aadha|आधा  akela|अकेला  alag|अलग  namaste|नमस्ते  shukriya|शुक्रिया  dhanyavaad|धन्यवाद  arre arey are|अरे  wah|वाह
aaram|आराम  dhyan dhyaan|ध्यान  khayal khyaal|ख़याल  madad|मदद  koshish|कोशिश  intezaar|इंतज़ार  jagah|जगह
raasta rasta|रास्ता  kitaab kitab|किताब  sabak|सबक  nahana|नहाना  kapde|कपड़े  khel|खेल  khelna|खेलना
dawai dawa|दवाई  beemar bimar|बीमार  bukhar|बुख़ार  dard|दर्द  haal|हाल  chinta|चिंता  mehnat|मेहनत  sapna|सपना
seedha sidha|सीधा  ulta|उल्टा  jaan|जान  zindagi|ज़िंदगी  shaadi|शादी  dulha|दूल्हा
khabar|ख़बर  mausam|मौसम  baarish barish|बारिश  garmi|गर्मी  sardi|सर्दी  thanda|ठंडा  garam|गरम  chai|चाय
nashta|नाश्ता  bajaa|बजा  bajao|बजाओ  ghanti|घंटी  uthao|उठाओ  hatao|हटाओ  mitao|मिटाओ  jodo|जोड़ो
jod|जोड़  daalo dalo|डालो  daal|डाल  hata|हटा  mita|मिटा  bachao|बचाओ  bacha|बचा  sambhal|संभाल  kaafi kafi|काफ़ी
sa|सा  si|सी  sachmuch|सचमुच  isliye|इसलिए  tabhi|तभी  lagbhag|लगभग  kareeb|क़रीब
"""

LEX: dict[str, str] = {}
for _rom, _dev in re.findall(r"([a-z]+(?: [a-z]+)*)\|(\S+)", _RAW):   # "kya kia|क्या": variants share one spelling
    for _w in _rom.split():
        LEX.setdefault(_w, _dev)

# Also common English words: Hindi only when the context is Hindi (see tag()).
AMBIGUOUS = {"to", "do", "main", "me", "hi", "the", "is", "us", "use", "par", "so", "mat", "tab", "log", "band",
             "door", "mast", "sun", "din", "mile", "pi", "lag", "teen", "bees", "char", "ya", "sake", "jab", "fir",
             "are", "or", "he", "ha"}
# words after which a Hindi "main" means मैं (I) rather than में (in)
_MAIN_I_AFTER = {"aur", "toh", "to", "par", "lekin", "phir", "fir", "ab", "jab", "agar", "kyunki", "ki", "haan", "nahi",
                 "accha", "achha", "acha", "bas", "abhi", "kal", "aaj"}

_TOKEN = re.compile(r"[ऀ-ॿ]+|[A-Za-z]+(?:'[A-Za-z]+)?|\d+(?:[:.]\d+)?|[^\s]")
_CLAUSE_END = set(",.!?;:—…।()\"")
_lock = threading.Lock()          # espeak calls are serialised (cheap: < 1 ms each)
_init_lock = threading.Lock()
_g2p = None


class _G2P:
    """One cached espeak backend per language. phonemizer.phonemize() builds a new backend on every call (~20 ms
    each, several runs per line); a backend owns its own copy of the espeak library, so two can live side by side."""

    def __init__(self):
        from kokoro_onnx.tokenizer import Tokenizer                # points phonemizer at kokoro's bundled espeak
        from phonemizer.backend import EspeakBackend
        self.vocab = Tokenizer().vocab
        self.backends = {lang: EspeakBackend(lang, preserve_punctuation=True, with_stress=True)
                         for lang in ("hi", "en-us")}

    def phonemize(self, text: str, lang: str) -> str:
        with _lock:
            ph = self.backends[lang].phonemize([text], strip=True)[0]
        return "".join(p for p in ph if p in self.vocab).strip()


def _tokenizer() -> _G2P:
    global _g2p
    if _g2p is None:
        with _init_lock:
            _g2p = _g2p or _G2P()
    return _g2p


def _kind(t: str) -> str:
    if "ऀ" <= t[0] <= "ॿ":
        return "dev"
    if t[0].isalpha():
        return "word"
    if t[0].isdigit():
        return "num"
    return "punct"


def tag(text: str) -> list[tuple[str, str]]:
    """[(token, lang)] with lang in hi / en / punct. Numbers take the language of their context."""
    toks = _TOKEN.findall(text)
    kinds = [_kind(t) for t in toks]
    base: list[str | None] = []
    for t, k in zip(toks, kinds):
        w = t.lower()
        if k == "dev":
            base.append("hi")
        elif k == "word":
            base.append(None if w in AMBIGUOUS else ("hi" if w in LEX else "en"))
        elif k == "num":
            base.append(None)
        else:
            base.append("punct")

    def neighbour(i: int, step: int) -> str | None:
        j = i + step
        while 0 <= j < len(toks):
            if kinds[j] == "punct":
                if toks[j] in _CLAUSE_END:
                    return None
            elif base[j] in ("hi", "en"):
                return base[j]
            j += step
        return None

    out = []
    for i, (t, b) in enumerate(zip(toks, base)):
        if b is None:
            left, right = neighbour(i, -1), neighbour(i, 1)
            w = t.lower()
            clause_start = left is None and (i == 0 or kinds[i - 1] == "punct")
            if kinds[i] == "word" and w in ("hi", "ha") and clause_start:
                b = "en" if w == "hi" else "hi"                   # "Hi Stiti" greeting; "Ha, ..." = haan
            elif left == "hi" or right == "hi":
                b = "hi"
            else:
                b = "en"
        out.append((t, b))
    return out


def _dev(tagged: list[tuple[str, str]], i: int) -> str:
    """Devanagari for a Hindi-tagged Roman word (main → मैं or में by context)."""
    t = tagged[i][0]
    w = t.lower()
    if w in ("main", "mai"):
        prev = next((tagged[j][0].lower() for j in range(i - 1, -1, -1) if tagged[j][1] != "punct"), None)
        clause_start = i == 0 or tagged[i - 1][1] == "punct"
        return "मैं" if clause_start or prev is None or prev in _MAIN_I_AFTER else "में"
    return LEX.get(w, t)


def is_hinglish(tagged: list[tuple[str, str]]) -> bool:
    words = [lang for t, lang in tagged if lang != "punct" and not t[0].isdigit()]
    h = words.count("hi")
    return h >= 2 or (h >= 1 and 3 * h >= len(words))     # 2+ Hindi words, or a third of a short line


def phonemize(text: str) -> str | None:
    """Kokoro phoneme string for Hinglish text, or None when the text is plain English (use the normal path)."""
    tagged = tag(text)
    if not is_hinglish(tagged):
        return None
    tk = _tokenizer()
    parts: list[str] = []
    run: list[str] = []
    lang = None

    def flush():
        if run:
            ph = tk.phonemize(" ".join(run), "hi" if lang == "hi" else "en-us")
            if ph:
                parts.append(ph)
            run.clear()

    for i, (t, l) in enumerate(tagged):
        if l == "punct":
            flush()
            lang = None
            p = "." if t == "।" else ("," if t in "—()\"" else t)
            if p in tk.vocab:
                if parts and parts[-1] in ",.!?;:…":
                    parts[-1] = p if p in ".!?" else parts[-1]
                else:
                    parts.append(p)
            continue
        if l != lang:
            flush()
            lang = l
        run.append(_dev(tagged, i) if l == "hi" and _kind(t) == "word" else t)
    flush()
    out = ""
    for p in parts:
        out += p if p in ",.!?;:…" else ((" " if out else "") + p)
    out = re.sub(r"\s+", " ", out).strip()
    return out or None


def warm() -> None:
    """espeak pays ~170 ms the first time it loads each voice; do it at start-up."""
    phonemize("Haan, aaj ka kaam ho gaya.")
