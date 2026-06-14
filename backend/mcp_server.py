"""
execution/mcp_server.py
========================
MCP Server that makes actual public API calls for Weather, News, and Music,
and uses cross-platform Text-to-Speech to read out the results.
"""

import os
import requests
import feedparser
import tempfile
import pygame
from .tts import speak, play_audio_file, init_mixer

def get_weather(location: str = "Bengaluru") -> dict:
    """Fetch weather for a location from wttr.in"""
    print(f"    [Weather] Fetching weather for {location}...")
    try:
        url = f"https://wttr.in/{location}?format=j1"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            data = r.json()
            cc = data.get("current_condition", [{}])[0]
            temp = cc.get("temp_C", "unknown")
            desc = cc.get("weatherDesc", [{}])[0].get("value", "")
            
            msg = f"The current weather in {location} is {temp} degrees Celsius and {desc}."
            speak(msg)
            return {"status": "success", "message": msg}
    except Exception as e:
        print(f"    [Weather] API Error: {e}")
        
    msg = f"Sorry, I couldn't fetch the weather for {location} right now."
    speak(msg)
    return {"status": "error", "message": msg}

import urllib.parse
import difflib
import re

KNOWN_CITIES = [
    # Indian cities
    "Bengaluru", "Mumbai", "Delhi", "New Delhi", "Hyderabad", "Chennai",
    "Kolkata", "Pune", "Ahmedabad", "Jaipur", "Surat", "Lucknow",
    "Chandigarh", "Himachal Pradesh", "Himachal",
    # World cities
    "New York", "London", "Tokyo", "Paris", "Dubai", "Singapore",
    "Sydney", "Toronto", "Berlin", "Beijing", "Shanghai", "Seoul",
    "Los Angeles", "Chicago", "Houston", "San Francisco",
    # Countries (for news queries)
    "India", "US", "USA", "United States", "UK", "United Kingdom",
    "Australia", "Canada", "Germany", "France", "Japan", "China",
    "South Africa", "South Korea", "Brazil", "Russia", "Italy",
    "Spain", "Mexico", "Pakistan", "Bangladesh", "Sri Lanka",
    "Nepal", "Afghanistan", "Israel", "Iran", "Ukraine",
]

def get_fuzzy_location(loc: str) -> str:
    # Case-insensitive match: compare lowercase versions, return proper-cased match
    loc_lower = loc.lower()
    for city in KNOWN_CITIES:
        if city.lower() == loc_lower:
            return city   # return the properly-cased version
    matches = difflib.get_close_matches(loc_lower,
                                        [c.lower() for c in KNOWN_CITIES],
                                        n=1, cutoff=0.75)
    if matches:
        # Return the properly-cased city
        for city in KNOWN_CITIES:
            if city.lower() == matches[0]:
                return city
    return loc   # unknown city — return as-is (wttr.in handles it fine)

def get_news(location: str = "India") -> dict:
    """Fetch latest top headline from Google News RSS for the location"""
    print(f"    [News] Fetching news for {location}...")
    try:
        safe_location = urllib.parse.quote(location)
        url = f"https://news.google.com/rss/search?q={safe_location}"
        feed = feedparser.parse(url)
        if feed.entries:
            # Get the top headline
            top_title = feed.entries[0].title
            # Google news often appends " - Publisher Name" at the end, let's keep it simple
            clean_title = top_title.rsplit(" - ", 1)[0]
            msg = f"Here is the latest news for {location}: {clean_title}."
            speak(msg)
            return {"status": "success", "message": msg}
    except Exception as e:
        print(f"    [News] API Error: {e}")
        
    msg = f"Sorry, I couldn't fetch the news for {location} right now."
    speak(msg)
    return {"status": "error", "message": msg}

def stop_media() -> dict:
    """Stop any currently playing media."""
    print("    [Media] Stopping playback...")
    init_mixer()
    if pygame.mixer.music.get_busy():
        pygame.mixer.music.stop()
        msg = "Okay, stopping the music."
    else:
        msg = "There is nothing playing right now."
    speak(msg)
    return {"status": "success", "message": msg}

def play_media(query: str, fallback_query: str = "Pop") -> dict:
    """Fetch a song metadata from iTunes API and play a cross-platform MP3."""
    print(f"    [Media] Searching for: {query}...")
    
    def search_itunes(search_term):
        try:
            url = f"https://itunes.apple.com/search?term={search_term}&entity=song&limit=1"
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                data = r.json()
                if data.get("resultCount", 0) > 0:
                    return data["results"][0]
        except Exception as e:
            print(f"    [Media] API Error: {e}")
        return None

    # First attempt with the parsed query
    track = search_itunes(query)
    
    # If it failed (e.g. transcript was messy like "raju s fifa 15"), fallback to their favorite genre!
    if not track:
        print(f"    [Media] Could not find '{query}'. Falling back to favorite genre: {fallback_query}...")
        track = search_itunes(fallback_query)
        
    if track:
        track_name = track.get("trackName", "Unknown Song")
        artist = track.get("artistName", "Unknown Artist")
        
        msg = f"Playing {track_name} by {artist}."
        speak(msg)
        
        # iTunes provides .m4a which pygame cannot play cross-platform.
        # So we download a reliable public domain MP3 for the audio demo.
        demo_mp3_url = "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3"
        
        temp_dir = tempfile.gettempdir()
        audio_file = os.path.join(temp_dir, "canary_preview.mp3")
        
        print(f"    [Media] Downloading MP3 audio stream...")
        audio_r = requests.get(demo_mp3_url, timeout=10)
        with open(audio_file, "wb") as f:
            f.write(audio_r.content)
            
        play_audio_file(audio_file, max_duration_sec=10)
        
        try:
            os.remove(audio_file)
        except OSError:
            pass
            
        return {"status": "success", "message": msg}
        
    msg = f"Sorry, I couldn't find or play any music for {query}."
    speak(msg)
    return {"status": "error", "message": msg}

def execute_intent(domain: str, transcript: str, profile: dict = None, entities: dict = None, polarity: str = "POSITIVE") -> dict:
    """
    Location priority:
      1. Personal pronoun detected ("my city", "my weather", etc.) → profile default
      2. Explicit location spoken in transcript                     → use that location
      3. Nothing found                                              → profile default
    """
    profile  = profile  or {}
    entities = entities or {}

    # Strip ALL punctuation and lowercase — clean slate for parsing
    clean = re.sub(r"[^\w\s]", " ", transcript.lower())
    clean = re.sub(r"\s+", " ", clean).strip()

    # ── Personal pronoun check ────────────────────────────────────────────
    _PERSONAL_RE = re.compile(
        r"\b(my\s+(city|town|place|home|location|country|area|region|news|weather)|"
        r"where\s+i\s+(live|am|stay|reside)|my\s+local|around\s+me|near\s+me)\b"
    )
    is_personal = bool(_PERSONAL_RE.search(clean))

    profile_city         = profile.get("location", "Bengaluru")
    profile_news_country = profile.get("news_country", profile_city)
    fav_music            = profile.get("favorite_music_genre", "Pop")

    if is_personal:
        location     = profile_city
        news_country = profile_news_country
    else:
        # ── Extract explicit spoken location from clean transcript ────────
        spoken_location: str | None = entities.get("location")

        if not spoken_location:
            match = re.search(
                r"\b(?:in|for|of|about|from|near|around)\s+([a-z][a-z\s]{1,25}?)(?:\s+(?:today|now|please|right now)|\s*$)",
                clean,
            )
            if match:
                extracted = match.group(1).strip()
                _SKIP = {"me", "my", "the", "a", "an", "some",
                         "music", "news", "weather", "songs", "here", "us"}
                if extracted not in _SKIP and len(extracted) > 1:
                    spoken_location = extracted

        if spoken_location:
            spoken_location = get_fuzzy_location(spoken_location)

        if spoken_location:
            location     = spoken_location
            news_country = spoken_location
        else:
            location     = profile_city
            news_country = profile_city  # default news to same city as weather default

    t = clean

    if domain == "WEATHER":
        return get_weather(location=location)

    elif domain == "NEWS":
        return get_news(location=news_country)

    elif domain == "SONGS":
        if polarity == "NEGATIVE":
            return stop_media()
        if "some music" in t or "a song" in t:
            query = fav_music
        else:
            query = re.sub(
                r"\b(play|amy|canary|raju|hey|some|music|please|songs from)\b",
                "", t,
            ).strip()
            if not query:
                query = fav_music
        return play_media(query=query, fallback_query=fav_music)

    else:
        msg = f"I'm sorry, I don't know how to handle the {domain} request yet."
        print(f"    [Agent] {msg}")
        speak(msg)
        return {"status": "ignored", "message": "No matching API"}
