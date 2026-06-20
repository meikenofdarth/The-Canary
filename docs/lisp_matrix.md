# The Lisp Matrix — Dynamic Phonetic Intent Matching

An algorithmic accessibility feature. Speech-to-text errors are **phonetic**
(the model types what it *heard*), so correcting them with letter-level fuzzy
matching or an LLM spell-fixer is the wrong tool. The Lisp Matrix matches intent
in **phonetic space** with a **per-user confusion cost matrix**, so a speaker
with a speech difference (lisp, rhotacism, …) is understood reliably even when
the ASR transcript is "wrong".

> Module: `computation/intelligence/phonetic_matcher.py` · Tests:
> `tests/test_phonetic_matcher.py` · Pure Python, no neural network, no training.

## How it works

1. **Phonetic encoding** — the (possibly garbled) transcript and each valid
   command are encoded with **Double Metaphone** (`metaphone` library). Example:
   `sing → SNK`, `thing → 0NK`, `some → SM`, `thome → 0M` (`S`=/s/, `0`=/th/).
2. **Customisable confusion matrix** — for each speaker profile, specific code
   pairs are declared *equivalent* (zero substitution cost). The `lisp` profile
   sets `S ↔ 0` (and related), i.e. /s/ and /th/ are mathematically identical
   for that user.
3. **Needleman-Wunsch alignment** — global-alignment edit distance between the
   transcript's phonetic code and each command's code, using the confusion
   matrix as the substitution cost and a fixed gap cost. The normalized distance
   (0 = identical) ranks candidate commands; below a threshold it is accepted.

Built-in profiles (extensible / per-user overridable):

| Profile | Confusions (Double-Metaphone codes) | Speech difference |
|---|---|---|
| `default` | — | none |
| `lisp` | S↔0, S↔T, S↔F, X↔S | sibilants ↔ dental fricatives |
| `rhotacism` | R↔L, R↔W, R↔A | /r/ realised as /l/ or /w/ |
| `frontal` | T↔0, D↔0, K↔T, G↔T | fronting substitutions |

## Demonstration (from the test suite)

A lisping user says **"play thome muthic"** (for *"play some music"*):

```
default profile -> "play some music"   distance 0.2857
lisp    profile -> "play some music"   distance 0.0      ← exact phonetic match
```

- `sing` vs `thing` align at **zero cost** under the lisp profile.
- A clean transcript still matches at distance 0.0 under the default profile.
- Ambient chatter (*"i think we should grab lunch later"*) does **not**
  confidently match any command (distance 0.71) — no false triggers.

## API

```python
from computation.intelligence.phonetic_matcher import match_command, best_intent

match_command("play thome muthic", COMMANDS, profile="lisp")
# -> {"command": "play some music", "distance": 0.0, "matched": True, "ranking": [...]}

best_intent("play thome muthic", {"play some music": "SONGS", ...}, profile="lisp")
# -> {..., "intent": "SONGS"}
```

A user's confusion profile (e.g. `"lisp"`) and any `extra_pairs` can be stored
in their enrolled voice profile, so the assistant adapts per speaker.

## Why it's novel

- Operates in **phonetic space**, not lexical space — it targets the actual
  failure mode of STT.
- **Per-user** confusion matrices make it an inclusivity feature for atypical
  speech, not a generic spell-corrector.
- Fully **deterministic and explainable** (an alignment score), with zero added
  model parameters — it complements, and is far cheaper than, an LLM corrector.

## Integration

`best_intent()` is designed to slot in as a **fallback** after the regex
utterance analyzer: when a wakeword is detected but the literal transcript fails
to classify, route the transcript through the Lisp Matrix against the known
command lexicon using the identified speaker's profile to recover the intent.
(Standalone module + tests landed first; live-pipeline wiring is the next step.)
