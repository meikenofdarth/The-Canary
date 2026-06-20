# Adaptive VAD for Disfluent / Stuttering Speech

Standard voice assistants use a rigid silence threshold: pause for >0.5–1.0 s and
the assistant assumes you're done and cuts you off. For people who stutter or
have disfluent speech, a physiological block mid-sentence gets truncated into a
fragment. The Adaptive VAD makes the silence tolerance **per-speaker**.

> Module: `computation/audio/vad_segmenter.py` · Tests:
> `tests/test_adaptive_vad.py` · Built on Silero VAD (already in the pipeline).

## How it works

Each speaker has a disfluency profile selecting a VAD parameter set
(`adaptive_vad_config`):

| Profile | silence_timeout | min_silence_ms | threshold | max_duration |
|---|---|---|---|---|
| `default` | 1.8 s | 400 ms | 0.40 | 15 s |
| `disfluent` | 2.5 s | 1200 ms | 0.35 | 22 s |
| `stutter` | 3.0 s | 1800 ms | 0.35 | 25 s |

- **`silence_timeout`** — how long the live recorder waits after speech before
  finalizing. Larger for disfluent speakers, so a block isn't treated as "done".
- **`min_silence_ms`** — gaps shorter than this are merged into one segment, so a
  mid-utterance block doesn't split one command into two.
- **`threshold`** — lower (more permissive) so quiet/strained phonation still
  registers as speech.

Both `get_vad_segments(audio, sr, profile=...)` and
`record_until_silence(profile=...)` take the profile; explicit arguments still
override it (backward compatible).

## Demonstration (from the test suite)

Audio = speech + a **1.2 s silent block** + speech:

```
default profile -> 2 segment(s)   (block splits the command)
stutter profile -> 1 segment(s)   (block tolerated — command kept whole)
```

## Integration

The speaker's `phonetic_profile` / disfluency profile lives in their enrolled
voice profile, so once a household member is identified, their VAD tolerance is
applied automatically — the same per-speaker adaptation used by the Lisp Matrix.
