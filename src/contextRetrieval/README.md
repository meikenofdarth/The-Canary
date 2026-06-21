# Context Retrieval

Per-user activity logs surfacing prior runs of The Canary, used by the UI to
show each user their recent commands at a glance and to provide the assistant
with conversational continuity across sessions.

Each enrolled user has one append-only JSON-Lines file. Lines are written in
chronological order; UI consumers should read from the tail (most recent
first).

## Layout

```
contextRetrieval/
├── deepkumar.jsonl
├── hemang.jsonl
└── sanchit.jsonl
```

## Schema

Each line is one historical interaction with these fields:

| Field | Meaning |
|---|---|
| `timestamp` | ISO-8601 local time of the run |
| `session_id` | matches the `outputs/<timestamp>/` folder for that run |
| `wakeword` | the wakeword that was active at the time of the request |
| `transcript` | the user's utterance as transcribed by the ASR stage |
| `domain` | classified intent domain (`WEATHER` / `NEWS` / `SONGS` / …) |
| `polarity` | `POSITIVE` / `NEGATIVE` / `NEUTRAL` |
| `entities` | structured fields the intent engine extracted |
| `route` | `EXECUTE` / `CLARIFY` / `MULTI_EXECUTE` / `IGNORE` |
| `decision_reason` | one-line reason from the arbitration engine |
| `response` | the assistant's spoken response |
| `confidence` | speaker-identity confidence at decision time |
| `drs_mode` | scene-complexity mode (`A` / `B` / `C`) |
| `latency_ms` | end-to-end response latency |
