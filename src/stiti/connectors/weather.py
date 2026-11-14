"""Weather from Open-Meteo (keyless, free for non-commercial use, data CC BY 4.0 — D39).

  "what's the weather" · "mausam kaisa hai" · "will it rain today / kal baarish hogi?" · "bahar kitni garmi hai"
  → answered from code, no LLM: "It's 24 and clear in Pune, up to 31 later, no rain."

- City: owner_profile "city" (set by voice: "my city is Pune") → STITI_CITY → the timezone's city (Asia/Kolkata →
  Kolkata, always said out loud so a wrong guess is obvious). Nothing about the owner is hard-coded.
- Network: two tiny GETs (geocoding once per city, cached on disk; forecast cached 30 min in memory), 1.5 s timeout
  each. A failed fetch falls back to a copy < 6 h old; offline with nothing cached → None (the brief just skips it).
- Only the city name leaves the Mac (it goes to Open-Meteo); nothing personal.
"""
from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote_plus

from ..config import CFG

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search?name={q}&count=1&language=en&format=json"
FC_URL = ("https://api.open-meteo.com/v1/forecast?latitude={lat:.4f}&longitude={lon:.4f}"
          "&current=temperature_2m,apparent_temperature,weather_code,is_day"
          "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code"
          "&timezone=auto&forecast_days=2")
TIMEOUT_S = 1.5
TTL_S = 30 * 60
STALE_OK_S = 6 * 3600          # a failed refresh may answer from a copy this old
BRIEF_MAX_AGE_S = 3 * 3600     # the morning brief never waits on the network; it uses a copy this fresh


@dataclass
class Day:
    day: date
    hi: float
    lo: float
    rain: int | None            # max precipitation probability, %
    code: int


@dataclass
class Weather:
    city: str
    temp: float
    feels: float
    code: int
    is_day: bool
    days: list[Day] = field(default_factory=list)
    fetched_at: float = 0.0
    utc_offset_s: int | None = None     # the city's clock ("up to 20 later" must mean later THERE)


# ---------------------------------------------------------------- city
def _tz_city() -> str:
    return CFG.tz.key.split("/")[-1].replace("_", " ")


def city() -> tuple[str, bool]:
    """(city, explicitly set?) — profile key "city", then STITI_CITY, then the timezone's city."""
    import os
    try:
        from .. import profile
        c = profile.get("city")
    except Exception:
        c = None
    if c:
        return c, True
    if os.getenv("STITI_CITY"):
        return os.environ["STITI_CITY"].strip(), True
    return _tz_city(), False


# ---------------------------------------------------------------- http (the one seam tests replace)
def _fetch_json(url: str, timeout: float = TIMEOUT_S) -> dict:
    from . import live
    return live._json(url, timeout=timeout)


_lock = threading.Lock()
_cache: dict[str, Weather] = {}
_geo_mem: dict[str, tuple[float, float, str] | None] = {}


def _geo_file():
    return CFG.home / "cache" / "geo.json"


def geocode(name: str) -> tuple[float, float, str] | None:
    """City name → (lat, lon, display name). Cached forever on disk (a city doesn't move)."""
    key = name.strip().lower()
    if key in _geo_mem:
        return _geo_mem[key]
    try:
        disk = json.loads(_geo_file().read_text())
    except Exception:
        disk = {}
    if key in disk:
        v = disk[key]
        _geo_mem[key] = (v[0], v[1], v[2]) if v else None
        return _geo_mem[key]
    js = _fetch_json(GEO_URL.format(q=quote_plus(name.strip())))      # raises when offline (not cached as "unknown")
    res = (js or {}).get("results") or []
    val = (float(res[0]["latitude"]), float(res[0]["longitude"]), str(res[0].get("name") or name)) if res else None
    _geo_mem[key] = val
    try:
        disk[key] = list(val) if val else None
        _geo_file().parent.mkdir(parents=True, exist_ok=True)
        _geo_file().write_text(json.dumps(disk))
    except Exception:
        pass
    return val


def parse(city_name: str, js: dict, fetched_at: float | None = None) -> Weather:
    cur, d = js["current"], js.get("daily") or {}
    days = []
    for i, t in enumerate(d.get("time") or []):
        rain = (d.get("precipitation_probability_max") or [None] * (i + 1))[i]
        days.append(Day(date.fromisoformat(t), float(d["temperature_2m_max"][i]), float(d["temperature_2m_min"][i]),
                        None if rain is None else int(rain), int((d.get("weather_code") or [0] * (i + 1))[i] or 0)))
    return Weather(city_name, float(cur["temperature_2m"]), float(cur.get("apparent_temperature", cur["temperature_2m"])),
                   int(cur.get("weather_code") or 0), bool(cur.get("is_day", 1)), days,
                   time.time() if fetched_at is None else fetched_at, js.get("utc_offset_seconds"))


def get(city_name: str | None = None, *, network: bool = True) -> Weather | None:
    """Cache-first. Miss → fetch (≤ 2 × 1.5 s). Failure → a copy < 6 h old, else None. Never raises."""
    name = city_name or city()[0]
    key = name.strip().lower()
    hit = _cache.get(key)
    if hit and time.time() - hit.fetched_at < TTL_S:
        return hit
    if not network:
        return hit if hit and time.time() - hit.fetched_at < STALE_OK_S else None
    try:
        g = geocode(name)
        if g is None:
            return None
        w = parse(g[2], _fetch_json(FC_URL.format(lat=g[0], lon=g[1])))
    except Exception:
        return hit if hit and time.time() - hit.fetched_at < STALE_OK_S else None
    with _lock:
        _cache[key] = w
    return w


def cached(city_name: str | None = None, max_age_s: float = BRIEF_MAX_AGE_S) -> Weather | None:
    """No network at all (for the morning brief)."""
    hit = _cache.get((city_name or city()[0]).strip().lower())
    return hit if hit and time.time() - hit.fetched_at < max_age_s else None


def fresh(city_name: str | None = None) -> bool:
    hit = _cache.get((city_name or city()[0]).strip().lower())
    return bool(hit and time.time() - hit.fetched_at < TTL_S)


def refresh_async(city_name: str | None = None) -> None:
    """Fill / refresh the cache in the background (app scheduler every 30 min, Engine start)."""
    if fresh(city_name):
        return
    threading.Thread(target=get, args=(city_name,), daemon=True, name="weather").start()


def clear_cache() -> None:
    _cache.clear()
    _geo_mem.clear()


# ---------------------------------------------------------------- speech
def describe(code: int, is_day: bool = True) -> str:
    """WMO weather code → a few spoken words (fits "It's 24 and ___")."""
    if code == 0:
        return "clear" if not is_day else "sunny"
    if code == 1:
        return "mostly clear"
    if code == 2:
        return "partly cloudy"
    if code == 3:
        return "cloudy"
    if code in (45, 48):
        return "foggy"
    if 51 <= code <= 57:
        return "drizzling"
    if 61 <= code <= 67 or 80 <= code <= 82:
        return "raining"
    if 71 <= code <= 77 or code in (85, 86):
        return "snowing"
    if code >= 95:
        return "stormy"
    return "mixed"


def _n(x: float) -> int:
    return int(round(x))


def _rain_tail(p: int | None, raining_now: bool = False) -> str:
    if p is None or raining_now:
        return ""
    if p < 20:
        return ", no rain"
    if p < 50:
        return f", maybe a little rain, {p}% chance"
    return ", and rain is likely — take an umbrella"


def _local(w: Weather, now: datetime | None) -> datetime:
    now = now or datetime.now(CFG.tz)
    if w.utc_offset_s is None:
        return now
    return now.astimezone(timezone(timedelta(seconds=w.utc_offset_s)))


def _today(w: Weather, now: datetime) -> Day | None:
    return next((d for d in w.days if d.day == now.date()), w.days[0] if w.days else None)


def _tomorrow(w: Weather, now: datetime) -> Day | None:
    return next((d for d in w.days if d.day > now.date()), None)


def one_liner(w: Weather, now: datetime | None = None, with_city: bool = True) -> str:
    """"It's 24 and clear in Pune, up to 31 later, no rain." """
    now = _local(w, now)
    desc = describe(w.code, w.is_day)
    s = f"It's {_n(w.temp)} and {desc}" + (f" in {w.city}" if with_city else "")
    d = _today(w, now)
    if d is not None:
        if now.hour < 15 and d.hi >= w.temp + 2:
            s += f", up to {_n(d.hi)} later"
        elif now.hour >= 17 and d.lo <= w.temp - 2:
            s += f", down to {_n(d.lo)} tonight"
        s += _rain_tail(d.rain, raining_now=desc in ("raining", "drizzling", "stormy"))
    return s + "."


def speak(w: Weather, focus: str = "now", day: int = 0, now: datetime | None = None) -> str:
    """focus: now | rain | heat. day: 0 today, 1 tomorrow."""
    now = _local(w, now)
    if day == 1:
        d = _tomorrow(w, now)
        if d is None:
            return "I don't have tomorrow's forecast yet."
        if focus == "rain":
            return _rain_answer(d.rain, w.city, "tomorrow")
        sky = describe(d.code)
        sky = "" if sky in ("raining", "drizzling", "snowing", "stormy", "mixed") else f", {sky}"
        if d.rain is None:
            rain = ""
        elif d.rain < 20:
            rain = ", no rain"
        elif d.rain < 50:
            rain = f", maybe a little rain, {d.rain}% chance"
        else:
            rain = ", rain likely — take an umbrella"
        return f"Tomorrow in {w.city}: {_n(d.lo)} to {_n(d.hi)}{sky}{rain}."
    if focus == "rain":
        d = _today(w, now)
        if describe(w.code, w.is_day) in ("raining", "drizzling", "stormy"):
            return f"It's {describe(w.code)} in {w.city} right now — take an umbrella."
        return _rain_answer(d.rain if d else None, w.city, "today")
    if focus == "heat":
        s = f"It's {_n(w.temp)} in {w.city} right now"
        if abs(w.feels - w.temp) >= 2:
            s += f", feels like {_n(w.feels)}"
        d = _today(w, now)
        if d is not None and now.hour < 15 and d.hi >= w.temp + 2:
            s += f", up to {_n(d.hi)} later"
        return s + "."
    return one_liner(w, now)


def _rain_answer(p: int | None, where: str, when: str) -> str:
    if p is None:
        return f"I can't see a rain forecast for {where} {when}."
    if p >= 50:
        return f"Yes, probably — {p}% chance of rain in {where} {when}. Take an umbrella."
    if p >= 20:
        return f"Maybe — {p}% chance of rain in {where} {when}."
    if p < 5:
        return f"No — no rain expected in {where} {when}."
    return f"Probably not — only {p}% chance of rain in {where} {when}."


# ---------------------------------------------------------------- understanding him (no LLM)
_NOT = re.compile(r"\b(remind\w*|reminder|alarms?|timers?|todos?|to-do|tasks?|under the weather|fair[- ]weather|"
                  r"weather (the|this|that) (storm|phase)|like (the )?weather|temperature of|body temperature|fever)\b", re.I)
WEATHER_RX = re.compile(r"\b(weather|mausam|mausum|forecast)\b", re.I)
RAIN_RX = re.compile(
    r"\b(will it|is it going to|is it gonna|gonna|going to|chance of|any|is there)\s+(be\s+)?(rain|raining|drizzle|pour)\b|"
    r"\b(baarish|barish|baris|baarsih)\b.*\b(hogi|hoga|aayegi|ayegi|aaegi|hai kya|ho rahi|hogi kya|chance|padegi|"
    r"pad rahi)\b|"
    r"\b(need|take|carry|bring|lena|le jaun|le jau|le ke jaun|chahiye)\b.*\bumbrella\b|"
    r"\bumbrella\b.*\b(need|chahiye|lena|le jaun|le jau|today|aaj)\b|\bis it raining\b", re.I)
HEAT_RX = re.compile(
    r"\b(kitni|kaisi|bahut|kitna)\s+(garmi|thand|thandi|sardi|thanda)\b|"
    r"\bhow (hot|cold|warm|chilly|humid)\b.*\b(outside|today|is it|out there|bahar|right now|now)\b|"
    r"\bbahar\b.*\b(garmi|thand|sardi|temperature|kaisa)\b|"
    r"\b(what'?s|whats|what is|kya hai|kitna)\b.*\btemperature\b|\btemperature\b.*\b(outside|today|aaj|bahar|right now|"
    r"kitna|kya hai)\b|\bis it (hot|cold|warm)\b", re.I)
TOMORROW_RX = re.compile(r"\b(tomorrow|tmrw|kal)\b", re.I)
_PLACE_STOP = {"the", "the evening", "the morning", "the afternoon", "today", "tomorrow", "my area", "here", "outside",
               "my city", "this city", "the city", "town", "the weekend", "now", "right now", "kal", "aaj", "general"}
CITY_IN_RX = re.compile(r"\b(?:in|at|for)\s+(?P<c>[A-Za-z][A-Za-z.'-]+(?:\s+[A-Za-z][A-Za-z.'-]+){0,2}?)"
                        r"(?:\s+(?:today|tomorrow|tonight|now|right now|kal|aaj|this \w+))?\s*[?.!]*$", re.I)
CITY_HI_RX = re.compile(r"^\W*(?P<c>[A-Za-z][A-Za-z.'-]+(?:\s+[A-Za-z][A-Za-z.'-]+)?)\s+(?:mein|me|ka|ki|mai)\s+"
                        r"(?:aaj |kal )?(?:mausam|weather|baarish|barish|temperature|garmi|thand)\b", re.I)
SET_CITY_RX = re.compile(
    r"\b(?:my (?:home )?city is|set (?:my |the )?(?:weather )?(?:city|location) (?:to|as)|"
    r"use (?P<c2>[A-Za-z][A-Za-z .'-]{1,40}?) for (?:the )?weather|i live in|i'?m based in|i am based in)"
    r"\s*(?P<c>[A-Za-z][A-Za-z .'-]{1,40}?)?\s*[.!]*$|"
    r"\b(?:main|mai|mein)\s+(?P<c3>[A-Za-z][A-Za-z.'-]+(?:\s+[A-Za-z][A-Za-z.'-]+)?)\s+(?:mein|me)\s+(?:rehta|rehti|rahta|rahti)\b",
    re.I)
_NOT_A_CITY = re.compile(r"^(a|an|the|my|this|that|your|our|his|her|it|here|there|hostel|pg|flat|house|home)\b", re.I)


@dataclass
class Ask:
    focus: str          # now | rain | heat
    day: int            # 0 today, 1 tomorrow
    place: str | None   # a city he named ("weather in Mumbai"), else his own


def detect(text: str) -> Ask | None:
    t = text.strip()
    if not t or _NOT.search(t):
        return None
    focus = "rain" if RAIN_RX.search(t) else "heat" if HEAT_RX.search(t) else "now" if WEATHER_RX.search(t) else None
    if focus is None:
        return None
    day = 1 if TOMORROW_RX.search(t) and not re.search(r"\byesterday\b", t, re.I) else 0
    place = None
    m = CITY_HI_RX.search(t) or CITY_IN_RX.search(t)
    if m:
        p = re.sub(r"\s+(today|tomorrow|tonight|now|kal|aaj)$", "", m.group("c").strip(), flags=re.I)
        if p.lower() not in _PLACE_STOP and not _NOT_A_CITY.match(p) and not re.match(
                r"^(kya|kaisa|kaisi|how|what|is|it|aaj|kal|bahar|will|the weather)$", p, re.I):
            place = p.title() if p.islower() else p
    return Ask(focus, day, place)


def city_from_text(text: str) -> str | None:
    m = SET_CITY_RX.search(text.strip())
    if not m:
        return None
    c = (m.group("c") or m.group("c2") or m.group("c3") or "").strip(" .,!?")
    if not c or _NOT_A_CITY.match(c) or len(c.split()) > 3:
        return None
    return c.title() if c.islower() else c


def set_city(name: str) -> str:
    """Save his city (owner_profile, local). Checked with the geocoder when online; offline it's saved anyway."""
    from .. import profile
    try:
        g = geocode(name)
        if g is None:
            return f"I couldn't find a place called {name}. Say it like “my city is Pune”."
        name = g[2]
    except Exception:
        pass
    profile.set("city", name, "owner_edit")
    refresh_async(name)
    return f"Got it — I'll use {name} for the weather."


def answer(text: str, now: datetime | None = None, on_slow=None) -> str | None:
    """Fast-path entry. None = not about the weather (or setting his city)."""
    if (c := city_from_text(text)) is not None:
        return set_city(c)
    ask = detect(text)
    if ask is None:
        return None
    name = ask.place or city()[0]
    if on_slow is not None and not fresh(name):
        on_slow()                                     # "Let me look that up." while it fetches
    w = get(name)
    if w is None:
        return "I can't reach the weather right now."
    reply = speak(w, ask.focus, ask.day, now)
    if ask.place is None and not city()[1] and not _hinted[0]:
        _hinted[0] = True
        reply += " Tell me your city and I'll use that — say “my city is …”."
    return reply


_hinted = [False]
