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
from .tts import speak, play_audio_file

def get_weather(location: str = "Bengaluru") -> dict:
    """Fetch current weather from wttr.in"""
    print(f"    [Weather] 🌤️ Fetching weather for {location}...")
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

def get_news(location: str = "Bengaluru") -> dict:
    """Fetch latest top headline from Google News RSS for the location"""
    print(f"    [News] 📰 Fetching news for {location}...")
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

def play_media(query: str, fallback_query: str = "Pop") -> dict:
    """Fetch a song metadata from iTunes API and play a cross-platform MP3."""
    print(f"    [Media] 🎵 Searching for: {query}...")
    
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
            
        play_audio_file(audio_file)
        
        try:
            os.remove(audio_file)
        except OSError:
            pass
            
        return {"status": "success", "message": msg}
        
    msg = f"Sorry, I couldn't find or play any music for {query}."
    speak(msg)
    return {"status": "error", "message": msg}

def execute_intent(domain: str, transcript: str, profile: dict = None) -> dict:
    """
    Given a domain, transcript, and user profile, invoke the appropriate API tool.
    """
    profile = profile or {}
    location = profile.get("location", "Bengaluru")
    fav_music = profile.get("favorite_music_genre", "Pop")
    
    t = transcript.lower()
    
    if domain == "WEATHER":
        return get_weather(location=location)
        
    elif domain == "NEWS":
        return get_news(location=location)
        
    elif domain == "SONGS":
        # If they just said "play some music", use their favorite genre!
        if "some music" in t or "a song" in t:
            query = fav_music
        else:
            # Strip out generic words
            query = t.replace("play", "").replace("canary", "").replace("hey", "").replace("some", "").replace("music", "").replace("please", "").replace("songs from", "").strip()
            if not query:
                query = fav_music
                
        return play_media(query=query, fallback_query=fav_music)
        
    else:
        # Fallback if we don't understand
        msg = f"I'm sorry, I don't know how to handle the {domain} request yet."
        print(f"    [Agent] ❓ {msg}")
        speak(msg)
        return {"status": "ignored", "message": "No matching API"}
