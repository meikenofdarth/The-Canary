
import os
import tempfile
import time

from gtts import gTTS
import pygame


def init_mixer():
    if not pygame.mixer.get_init():
        pygame.mixer.init()


def speak(text: str, lang: str = 'en'):
    if not text:
        return

    print(f"    [TTS] Speaking: '{text}'")
    try:
        tts = gTTS(text=text, lang=lang)
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
            tmp_path = f.name
        tts.save(tmp_path)
        play_audio_file(tmp_path)
    except Exception as e:
        print(f"    [TTS] Error: {e}")
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


def play_audio_file(filepath: str, max_duration_sec: int = 0):
    if not os.path.exists(filepath):
        print(f"    [Audio] File not found: {filepath}")
        return

    init_mixer()
    try:
        pygame.mixer.music.load(filepath)
        pygame.mixer.music.play()

        start = time.time()
        while pygame.mixer.music.get_busy():
            if max_duration_sec > 0 and (time.time() - start > max_duration_sec):
                pygame.mixer.music.stop()
                break
            pygame.time.Clock().tick(10)

        time.sleep(0.5)
    except Exception as e:
        print(f"    [Audio] Playback error: {e}")
