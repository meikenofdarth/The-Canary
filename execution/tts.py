"""
execution/tts.py
================
Cross-platform Text-to-Speech and audio playback using gTTS and pygame.
"""

import os
import tempfile
from gtts import gTTS
import pygame
import time

def init_mixer():
    if not pygame.mixer.get_init():
        pygame.mixer.init()

def speak(text: str, lang: str = 'en'):
    """Converts text to speech and plays it immediately."""
    if not text:
        return
        
    print(f"    [TTS] 🗣️  Speaking: '{text}'")
    
    # Generate speech
    tts = gTTS(text=text, lang=lang)
    
    # Save to temp file
    temp_dir = tempfile.gettempdir()
    temp_file = os.path.join(temp_dir, "canary_tts_output.mp3")
    tts.save(temp_file)
    
    # Play
    play_audio_file(temp_file)
    
    # Cleanup
    try:
        os.remove(temp_file)
    except OSError:
        pass

def play_audio_file(filepath: str, max_duration_sec: int = 0):
    """Plays an audio file (MP3, WAV, OGG) using pygame mixer."""
    if not os.path.exists(filepath):
        print(f"    [Audio] Error: File not found {filepath}")
        return
        
    init_mixer()
    
    try:
        pygame.mixer.music.load(filepath)
        pygame.mixer.music.play()
        
        # Block until playback finishes or max_duration is reached
        start_time = time.time()
        while pygame.mixer.music.get_busy():
            if max_duration_sec > 0 and (time.time() - start_time > max_duration_sec):
                pygame.mixer.music.stop()
                break
            pygame.time.Clock().tick(10)
            
        # Pygame mixer has a known bug where it stops slightly before the audio buffer is fully flushed.
        # Adding a 1 second sleep ensures the final words of the TTS are completely spoken out!
        time.sleep(1)
        
    except Exception as e:
        print(f"    [Audio] Error playing {filepath}: {e}")
