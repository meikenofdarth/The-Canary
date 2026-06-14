"""
context_engine/intent_engine.py
=================================
Intent classification engine for The Canary.

Covers the three primary action domains requested:
    - WEATHER   : weather, temperature, forecast queries
    - NEWS      : news, headlines, current events queries
    - SONGS     : music playback, song requests

For each domain both a POSITIVE intent (the speaker WANTS the action)
and a NEGATIVE intent (the speaker explicitly does NOT want it) are
detected.

Additionally the engine extracts lightweight entities:
    - WEATHER  : location, time_reference (today / tomorrow / weekend...)
    - NEWS     : topic (sport, politics, tech...), source
    - SONGS    : artist, genre, song title (best-effort, regex-free extraction)

Output
------
analyze_intent(text: str) -> IntentResult (dict)

    {
        "domain":         "WEATHER" | "NEWS" | "SONGS" | "UNKNOWN",
        "polarity":       "POSITIVE" | "NEGATIVE" | "NEUTRAL",
        "confidence":     float,          # 0.0 – 1.0
        "entities":       dict,           # domain-specific key/value pairs
        "raw_signals":    list[str],      # matched keywords that fired
        "original_text":  str
    }

Design principles
-----------------
- Zero ML models.  Pure rule-based regex + keyword matching.
- No side-effects.  Stateless function — no global state is mutated.
- Deterministic.  Same input always produces same output.
"""

from __future__ import annotations

import re
from typing import TypedDict


# =============================================================================
#  TYPE
# =============================================================================
class IntentResult(TypedDict):
    domain:        str          # WEATHER | NEWS | SONGS | UNKNOWN
    polarity:      str          # POSITIVE | NEGATIVE | NEUTRAL
    confidence:    float        # 0.0 – 1.0
    entities:      dict         # extracted entities (domain-specific)
    raw_signals:   list         # keywords/phrases that matched
    original_text: str


# =============================================================================
#  NEGATION PREFIXES
#  These turn a positive match into a NEGATIVE polarity.
#  Applied to a window of 5 tokens before the matched keyword.
# =============================================================================
_NEGATION_WORDS: frozenset[str] = frozenset({
    "no", "not", "don't", "dont", "do not", "never", "stop",
    "cancel", "skip", "skip the", "i don't want", "i dont want",
    "turn off", "disable", "no more", "enough", "quit", "end",
    "nothing", "none",
})

_NEGATION_RE = re.compile(
    r"\b(?:no|not|don'?t|never|stop|cancel|skip|turn\s+off|disable|"
    r"no\s+more|enough|quit|end|nothing|none|i\s+don'?t\s+want)\b",
    re.IGNORECASE,
)


def _has_negation(text: str, match_start: int) -> bool:
    """
    Return True if a negation word appears anywhere in the prefix before match_start.
    """
    prefix = text[:match_start]
    return bool(_NEGATION_RE.search(prefix))


# =============================================================================
#  DOMAIN SIGNAL TABLES
#  Each domain has:
#      POSITIVE_SIGNALS  — list of (regex_string, weight)
#      NEGATIVE_SIGNALS  — list of (regex_string, weight)   [explicit opt-out]
# =============================================================================

# ── WEATHER ──────────────────────────────────────────────────────────────────
_WEATHER_POSITIVE: list[tuple[str, float]] = [
    (r"\bweather\b",                           1.0),
    (r"\bforecast\b",                          1.0),
    (r"\btemperature\b",                       0.9),
    (r"\bhumidity\b",                          0.85),
    (r"\brain(ing|fall)?\b",                   0.8),
    (r"\bsnow(ing|fall)?\b",                   0.8),
    (r"\bwind(y|speed|chill)?\b",              0.75),
    (r"\bsunny\b",                             0.75),
    (r"\bcloudy\b",                            0.75),
    (r"\bstorm(y)?\b",                         0.8),
    (r"\bhow\s+(hot|cold|warm|cool)\b",        0.8),
    (r"\bwhat'?s\s+it\s+like\s+outside\b",    0.9),
    (r"\bshould\s+i\s+(bring\s+an?\s+umbrella|wear\s+a\s+jacket|carry\s+a\s+coat)\b", 0.9),
    (r"\bwhat\s+to\s+wear\b",                  0.7),
    (r"\bcheck\s+(the\s+)?weather\b",          1.0),
    (r"\bweather\s+report\b",                  1.0),
    (r"\bweather\s+update\b",                  1.0),
]

_WEATHER_NEGATIVE: list[tuple[str, float]] = [
    (r"\bno\s+weather\b",                      1.0),
    (r"\bdon'?t\s+(tell|show)\s+me.{0,20}weather\b", 1.0),
    (r"\bskip.{0,15}weather\b",                1.0),
    (r"\bi\s+don'?t\s+care.{0,20}weather\b",  1.0),
    (r"\bstop.{0,10}weather\b",               1.0),
]

# ── NEWS ──────────────────────────────────────────────────────────────────────
_NEWS_POSITIVE: list[tuple[str, float]] = [
    (r"\bnews\b",                              1.0),
    (r"\bheadlines?\b",                        1.0),
    (r"\blatest\s+news\b",                     1.0),
    (r"\bcurrent\s+events?\b",                 0.9),
    (r"\bwhat'?s\s+(happening|going\s+on)\b",  0.85),
    (r"\btop\s+stories?\b",                    0.9),
    (r"\bbriefing\b",                          0.85),
    (r"\bbreaking\s+news\b",                   1.0),
    (r"\bupdate\s+(me\s+)?on\b",               0.8),
    (r"\bwhat\s+(happened|is\s+happening)\b",  0.75),
    (r"\bnewsfeed\b",                          0.9),
    (r"\bmorning\s+brief\b",                   0.9),
    (r"\bsports?\s+news\b",                    0.9),
    (r"\bpolitics?\b",                         0.7),
    (r"\btech\s+news\b",                       0.85),
    (r"\bfinance\s+news\b",                    0.85),
    (r"\bglobal\s+news\b",                     0.9),
    (r"\blocal\s+news\b",                      0.9),
    (r"\bstock\s+market\b",                    0.75),
]

_NEWS_NEGATIVE: list[tuple[str, float]] = [
    (r"\bno\s+news\b",                         1.0),
    (r"\bskip.{0,15}news\b",                   1.0),
    (r"\bdon'?t.{0,20}news\b",                 1.0),
    (r"\bstop.{0,10}news\b",                   1.0),
    (r"\bi\s+don'?t\s+want.{0,20}news\b",      1.0),
    (r"\benough\s+news\b",                      1.0),
]

# ── SONGS ──────────────────────────────────────────────────────────────────
_SONGS_POSITIVE: list[tuple[str, float]] = [
    (r"\bplay\b",                              0.8),   # low alone — context-dependent
    (r"\bsong(s)?\b",                          1.0),
    (r"\bmusic\b",                             1.0),
    (r"\btrack\b",                             0.9),
    (r"\balbum\b",                             0.9),
    (r"\bartist\b",                            0.85),
    (r"\bplaylist\b",                          1.0),
    (r"\bspotify\b",                           1.0),
    (r"\bshuffle\b",                           0.85),
    (r"\bgaana\b",                             1.0),
    (r"\bjio\s*saavn\b",                       1.0),
    (r"\byoutube\s+music\b",                   1.0),
    (r"\bapple\s+music\b",                     1.0),
    (r"\bplay\s+(me\s+)?(some|a|an)\b",        0.95),
    (r"\bsomething\s+to\s+(listen|hear)\b",    0.9),
    (r"\bput\s+on\s+(some\s+)?music\b",        1.0),
    (r"\bstart\s+(the\s+)?music\b",            1.0),
    (r"\bplay\s+(some\s+)?(english|hindi|bollywood|punjabi|tamil|telugu|classical|jazz|rock|pop|rap|hiphop|hip-hop|lofi|lo-fi|chill|sad|happy|romantic|party)\b", 1.0),
    (r"\bgood\s+songs?\b",                     0.9),
    (r"\bnew\s+songs?\b",                      0.9),
    (r"\bold\s+songs?\b",                      0.85),
    (r"\bbest\s+songs?\b",                     0.9),
    (r"\bplay\s+.{1,40}\s+songs?\b",           0.95),
]

_SONGS_NEGATIVE: list[tuple[str, float]] = [
    (r"\bstop\s+(the\s+)?music\b",             1.0),
    (r"\bpause\s+(the\s+)?music\b",            1.0),
    (r"\bno\s+music\b",                        1.0),
    (r"\bturn\s+off.{0,15}music\b",            1.0),
    (r"\bskip.{0,15}(song|track|music)\b",     0.9),
    (r"\bdon'?t\s+play.{0,20}music\b",         1.0),
    (r"\bi\s+don'?t\s+want.{0,20}(music|song)\b", 1.0),
    (r"\bstop\s+(the\s+)?song\b",              1.0),
    (r"\bchange\s+(the\s+)?song\b",            0.7),  # not purely negative; could want next
]


# =============================================================================
#  COMPILE ALL PATTERNS ONCE AT IMPORT
# =============================================================================
def _compile(signal_table: list[tuple[str, float]]) -> list[tuple[re.Pattern, float]]:
    return [(re.compile(p, re.IGNORECASE), w) for p, w in signal_table]


_W_POSITIVE = {
    "WEATHER": _compile(_WEATHER_POSITIVE),
    "NEWS":    _compile(_NEWS_POSITIVE),
    "SONGS":   _compile(_SONGS_POSITIVE),
}
_W_NEGATIVE = {
    "WEATHER": _compile(_WEATHER_NEGATIVE),
    "NEWS":    _compile(_NEWS_NEGATIVE),
    "SONGS":   _compile(_SONGS_NEGATIVE),
}


# =============================================================================
#  ENTITY EXTRACTORS (lightweight, no ML)
# =============================================================================

# ── WEATHER entities ──────────────────────────────────────────────────────────
_TIME_REFS = re.compile(
    r"\b(today|tonight|tomorrow|this\s+week(end)?|next\s+week|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekend)\b",
    re.IGNORECASE,
)
_LOCATION_PREP = re.compile(
    r"\b(?:in|at|for|around|near|of|about|from)\s+([A-Za-z][a-zA-Z\s]{2,24})",
    re.IGNORECASE,
)


def _extract_weather_entities(text: str) -> dict:
    # Strip punctuation first so "ammi, what is the weather in luxembourg?" works
    clean = re.sub(r"[^\w\s]", " ", text.lower())

    entities: dict = {}

    time_m = _TIME_REFS.search(clean)
    if time_m:
        entities["time_reference"] = time_m.group(0).lower()

    loc_m = _LOCATION_PREP.search(clean)
    if loc_m:
        candidate = loc_m.group(1).strip().split()
        # Take consecutive non-stopword words
        _STOP = {"music", "news", "songs", "song", "weather", "forecast",
                 "here", "home", "the", "a", "an", "me", "my", "us", "this", "that"}
        loc_words = []
        for w in candidate:
            if w.lower() in _STOP:
                break
            loc_words.append(w)
        candidate_str = " ".join(loc_words).strip()
        if candidate_str and len(candidate_str) > 1 and candidate_str.lower() not in _STOP:
            # Title-case it for display / API calls
            entities["location"] = candidate_str.title()

    return entities


# ── NEWS entities ─────────────────────────────────────────────────────────────
_NEWS_TOPICS = re.compile(
    r"\b(sport(?:s)?|cricket|football|soccer|basketball|"
    r"politics?|election|government|parliament|"
    r"technology|tech|science|health|covid|pandemic|"
    r"business|finance|economy|stock(?:s)?|market|"
    r"entertainment|bollywood|hollywood|"
    r"world|international|global|local|national|"
    r"weather|environment|climate)\b",
    re.IGNORECASE,
)
_NEWS_SOURCES = re.compile(
    r"\b(bbc|cnn|ndtv|times\s+of\s+india|hindustan\s+times|the\s+hindu|"
    r"reuters|ap\s+news|bloomberg|the\s+guardian|espn|zee\s+news|"
    r"india\s+today|aaj\s+tak)\b",
    re.IGNORECASE,
)


def _extract_news_entities(text: str) -> dict:
    clean = re.sub(r"[^\w\s]", " ", text.lower())
    entities: dict = {}

    topics = _NEWS_TOPICS.findall(clean)
    if topics:
        entities["topics"] = list(dict.fromkeys(t.lower() for t in topics))

    src_m = _NEWS_SOURCES.search(clean)
    if src_m:
        entities["source"] = src_m.group(0).lower()

    time_m = _TIME_REFS.search(clean)
    if time_m:
        entities["time_reference"] = time_m.group(0).lower()

    # Also extract location for news (e.g. "news of south africa")
    loc_m = _LOCATION_PREP.search(clean)
    if loc_m:
        candidate_words = loc_m.group(1).strip().split()
        _STOP = {"music", "news", "songs", "weather", "the", "a", "an",
                 "me", "my", "us", "this", "that", "here", "home"}
        loc_words = [w for w in candidate_words if w.lower() not in _STOP]
        candidate_str = " ".join(loc_words).strip()
        if candidate_str and len(candidate_str) > 1:
            entities["location"] = candidate_str.title()

    return entities


# ── SONGS entities ─────────────────────────────────────────────────────────────
_GENRE_RE = re.compile(
    r"\b(english|hindi|bollywood|punjabi|tamil|telugu|kannada|marathi|"
    r"classical|jazz|rock|pop|rap|hip-?hop|lofi|lo-?fi|chill|sad|happy|"
    r"romantic|party|retro|old|new|latest|trending|instrumental)\b",
    re.IGNORECASE,
)

_PLAY_SONG_RE = re.compile(
    r"\bplay\s+(?:me\s+)?(?:the\s+song\s+)?[\"']?([A-Za-z][a-zA-Z\s,'\-\.]{2,40})[\"']?",
    re.IGNORECASE,
)

_PLAYLIST_RE = re.compile(
    r"\b(?:playlist|mix|radio)\b",
    re.IGNORECASE,
)


def _extract_songs_entities(text: str) -> dict:
    entities: dict = {}

    genres = _GENRE_RE.findall(text)
    if genres:
        entities["genres"] = list(dict.fromkeys(g.lower() for g in genres))

    # Find "by " and extract consecutive title case words for artist
    by_m = re.search(r"\bby\s+([A-Za-z\s]+)", text, re.IGNORECASE)
    if by_m:
        after_by = by_m.group(1).strip()
        words = after_by.split()
        artist_words = []
        for i, w in enumerate(words):
            w_clean = w.rstrip(".,?!;")
            if not w_clean:
                break
            if w_clean[0].isupper():
                artist_words.append(w_clean)
            elif w_clean.lower() in ("the", "of", "and", "feat", "featuring") and i + 1 < len(words) and words[i+1].rstrip(".,?!;")[0].isupper():
                artist_words.append(w_clean)
            else:
                break
        if artist_words:
            entities["artist"] = " ".join(artist_words)

    if _PLAYLIST_RE.search(text):
        entities["is_playlist"] = True

    # Best-effort song title: "play [song name]"
    play_m = _PLAY_SONG_RE.search(text)
    if play_m:
        title = play_m.group(1).strip()
        # Remove trailing suffixes
        suffixes = ["on spotify", "on youtube", "please", "now", "again", "for me"]
        title_lower = title.lower()
        for suff in suffixes:
            if title_lower.endswith(suff):
                title = title[:-len(suff)].strip()
                title_lower = title.lower()
        # Filter out pure genre matches or artist names to avoid duplication
        if not _GENRE_RE.fullmatch(title.strip()):
            entities["song_title_candidate"] = title

    return entities


# =============================================================================
#  CORE SCORER
# =============================================================================
def _score_domain(
    text: str,
    positive_patterns: list[tuple[re.Pattern, float]],
    negative_patterns: list[tuple[re.Pattern, float]],
) -> tuple[float, float, list[str], list[str]]:
    """
    Score a piece of text for a given domain.

    Returns
    -------
    (positive_score, negative_score, pos_signals, neg_signals)
        positive_score : raw accumulated weight of positive matches
        negative_score : raw accumulated weight of negative (explicit opt-out) matches
        pos_signals    : matched positive keyword phrases
        neg_signals    : matched negative keyword phrases
    """
    pos_score = 0.0
    neg_score = 0.0
    pos_signals: list[str] = []
    neg_signals: list[str] = []

    for pat, weight in positive_patterns:
        m = pat.search(text)
        if m:
            # Check if the match is immediately negated in context
            if _has_negation(text, m.start()):
                # Treat this as a negative signal instead
                neg_score += weight * 0.8
                neg_signals.append(f"[negated] {m.group(0)}")
            else:
                pos_score += weight
                pos_signals.append(m.group(0))

    for pat, weight in negative_patterns:
        m = pat.search(text)
        if m:
            neg_score += weight
            neg_signals.append(m.group(0))

    return pos_score, neg_score, pos_signals, neg_signals


# =============================================================================
#  PUBLIC API
# =============================================================================
def analyze_intent(text: str) -> IntentResult:
    """
    Classify the intent of an utterance into one of the three domains
    (WEATHER, NEWS, SONGS) with positive or negative polarity.

    Parameters
    ----------
    text : str
        Raw transcript text from ASR.

    Returns
    -------
    IntentResult dict:
        {
            "domain":        "WEATHER" | "NEWS" | "SONGS" | "UNKNOWN",
            "polarity":      "POSITIVE" | "NEGATIVE" | "NEUTRAL",
            "confidence":    float,
            "entities":      dict,
            "raw_signals":   list[str],
            "original_text": str,
        }
    """
    if not text or not text.strip():
        return IntentResult(
            domain="UNKNOWN",
            polarity="NEUTRAL",
            confidence=0.0,
            entities={},
            raw_signals=[],
            original_text=text or "",
        )

    text_clean = text.strip()

    # Score all three domains
    results: dict[str, tuple] = {}
    for domain in ("WEATHER", "NEWS", "SONGS"):
        pos_s, neg_s, pos_sig, neg_sig = _score_domain(
            text_clean,
            _W_POSITIVE[domain],
            _W_NEGATIVE[domain],
        )
        results[domain] = (pos_s, neg_s, pos_sig, neg_sig)

    # Pick the domain with the highest combined absolute signal
    def _total_signal(d: str) -> float:
        pos_s, neg_s, _, _ = results[d]
        return pos_s + neg_s

    best_domain = max(results, key=_total_signal)
    pos_s, neg_s, pos_sig, neg_sig = results[best_domain]
    total = pos_s + neg_s

    # If no domain produced any signal, return UNKNOWN
    if total < 0.5:
        return IntentResult(
            domain="UNKNOWN",
            polarity="NEUTRAL",
            confidence=0.0,
            entities={},
            raw_signals=[],
            original_text=text_clean,
        )

    # Determine polarity
    if neg_s > pos_s * 1.2:
        # Explicit negative clearly dominates
        polarity = "NEGATIVE"
        dominant_score = neg_s
    elif pos_s > 0 and neg_s == 0:
        polarity = "POSITIVE"
        dominant_score = pos_s
    elif pos_s > 0 and neg_s > 0:
        # Both signals present — whichever is stronger wins
        if pos_s >= neg_s:
            polarity = "POSITIVE"
            dominant_score = pos_s
        else:
            polarity = "NEGATIVE"
            dominant_score = neg_s
    elif neg_s > 0:
        polarity = "NEGATIVE"
        dominant_score = neg_s
    else:
        polarity = "NEUTRAL"
        dominant_score = 0.0

    # Confidence: normalise the dominant score to 0–1 using a soft cap at 3.0
    # (because weighted sums can exceed 1.0 when multiple patterns fire)
    confidence = round(min(dominant_score / 3.0, 1.0), 4)
    # Raise minimum confidence to 0.55 once any domain fires
    confidence = max(confidence, 0.55)

    # Extract entities for the winning domain
    all_signals = pos_sig + neg_sig
    if best_domain == "WEATHER":
        entities = _extract_weather_entities(text_clean)
    elif best_domain == "NEWS":
        entities = _extract_news_entities(text_clean)
    else:  # SONGS
        entities = _extract_songs_entities(text_clean)

    return IntentResult(
        domain=best_domain,
        polarity=polarity,
        confidence=confidence,
        entities=entities,
        raw_signals=all_signals,
        original_text=text_clean,
    )


def analyze_intents_for_speakers(speakers: list[dict]) -> list[dict]:
    """
    Run analyze_intent on every speaker that has a transcript and a wakeword.

    Parameters
    ----------
    speakers : list[dict]
        Speaker records from context_builder.

    Returns
    -------
    Same list, with an "intent_result" key attached to each speaker.
    """
    for spk in speakers:
        transcript = spk.get("transcript", "")
        if transcript:
            spk["intent_result"] = analyze_intent(transcript)
        else:
            spk["intent_result"] = IntentResult(
                domain="UNKNOWN",
                polarity="NEUTRAL",
                confidence=0.0,
                entities={},
                raw_signals=[],
                original_text=transcript or "",
            )
    return speakers
