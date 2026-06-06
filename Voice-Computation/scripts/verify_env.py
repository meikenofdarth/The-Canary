#!/usr/bin/env python3
import sys
import time
from rich.console import Console
from rich.table import Table

console = Console()
results = []

def check(name, fn):
    try:
        result = fn()
        results.append((name, "\u2705 PASS", str(result)))
    except Exception as e:
        results.append((name, "\u274c FAIL", str(e)))

check("Python version (need 3.12)",
    lambda: f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")

check("numpy import",
    lambda: __import__("numpy").__version__)

check("torch import + MPS check",
    lambda: (lambda t: f"torch {t.__version__}, MPS={'yes' if t.backends.mps.is_available() else 'NO'}")
            (__import__("torch")))

check("onnxruntime import",
    lambda: (lambda o: f"version {o.__version__}, providers: {o.get_available_providers()}")
            (__import__("onnxruntime")))

check("silero_vad model load",
    lambda: (lambda s: f"Loaded: {type(s.load_silero_vad()).__name__}")
            (__import__("silero_vad")))

check("openwakeword import",
    lambda: __import__("openwakeword").__version__)

check("sounddevice + mic query",
    lambda: (lambda sd: f"Default input: {sd.query_devices(kind='input')['name']}")
            (__import__("sounddevice")))

check("librosa import",
    lambda: __import__("librosa").__version__)

check("scipy import",
    lambda: __import__("scipy").__version__)

check("5-second mic capture test",
    lambda: _capture_test())

def _capture_test():
    import sounddevice as sd
    import numpy as np
    captured = []
    def cb(indata, frames, time, status):
        captured.append(indata.copy())
    with sd.InputStream(samplerate=16000, channels=1, dtype='float32',
                        blocksize=512, callback=cb):
        time.sleep(1.0)
    total = sum(len(c) for c in captured)
    rms = float(np.sqrt(np.mean(np.concatenate(captured)**2)))
    return f"{total} samples captured, RMS={rms:.6f}"

table = Table(title="Canary Environment Check", show_header=True)
table.add_column("Check", style="cyan")
table.add_column("Status", style="bold")
table.add_column("Details", style="dim")

for name, status, detail in results:
    table.add_row(name, status, detail)

console.print(table)

if all("PASS" in r[1] for r in results):
    console.print("\n[bold green]\u2705 Environment is READY. Proceed to Stage 0.[/bold green]")
else:
    console.print("\n[bold red]\u274c Fix the failing checks before proceeding.[/bold red]")
