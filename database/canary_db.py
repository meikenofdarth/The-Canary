
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).parent.parent
_DB_FILE      = _PROJECT_ROOT / "database" / "canary.db"

_CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    speaker_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT UNIQUE NOT NULL,
    created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    recording_count   INTEGER DEFAULT 0,
    priority          INTEGER DEFAULT 3,

    -- Voice biometric scalars (from profile.json)
    pitch_mean        REAL,
    pitch_std         REAL,
    pitch_min         REAL,
    pitch_max         REAL,
    energy_mean       REAL,
    energy_std        REAL,
    speech_rate       REAL,
    spectral_centroid REAL,
    spectral_bandwidth REAL,

    -- Personalisation preferences
    city              TEXT DEFAULT 'Bengaluru',
    news_country      TEXT DEFAULT 'India',
    favorite_genre    TEXT DEFAULT 'Pop',

    -- Numpy feature blobs stored as compact JSON strings
    embedding_centroid TEXT,   -- JSON array of 192 floats
    mfcc_mean          TEXT    -- JSON array of 40 floats
);
"""

_CREATE_RECORDINGS = """
CREATE TABLE IF NOT EXISTS recordings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    speaker_id INTEGER NOT NULL,
    filename   TEXT    NOT NULL,
    FOREIGN KEY(speaker_id) REFERENCES users(speaker_id)
);
"""


def get_db_path() -> Path:
    return _DB_FILE


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_FILE))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.execute(_CREATE_USERS)
        conn.execute(_CREATE_RECORDINGS)
        conn.commit()
        cols = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "priority" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN priority INTEGER DEFAULT 3")
            conn.commit()
    finally:
        conn.close()


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for col in ("embedding_centroid", "mfcc_mean"):
        if d.get(col) and isinstance(d[col], str):
            try:
                d[col] = json.loads(d[col])
            except (json.JSONDecodeError, TypeError):
                pass
    return d


def get_user_count() -> int:
    init_db()
    conn = get_connection()
    try:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()
        return row["cnt"] if row else 0
    finally:
        conn.close()


def get_user(name: str) -> Optional[dict]:
    init_db()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE LOWER(name) = LOWER(?)", (name,)
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def get_all_users() -> list[dict]:
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM users ORDER BY speaker_id").fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def upsert_user(name: str, voice_profile: dict, preferences: dict = None) -> int:
    init_db()
    name = name.strip()

    existing = get_user(name)
    if existing is None and get_user_count() >= 5:
        raise ValueError("Maximum of 5 users allowed.")

    pitch   = voice_profile.get("pitch", {})
    energy  = voice_profile.get("energy", {})
    spectral = voice_profile.get("spectral", {})

    emb_centroid = voice_profile.get("embedding_centroid")
    mfcc_mean    = voice_profile.get("mfcc_mean")

    emb_json  = json.dumps(emb_centroid,  separators=(",", ":")) if emb_centroid  is not None else None
    mfcc_json = json.dumps(mfcc_mean,     separators=(",", ":")) if mfcc_mean     is not None else None

    recording_count = voice_profile.get("recording_count", 0)

    prefs = {
        "city":          "Bengaluru",
        "news_country":  "India",
        "favorite_genre": "Pop",
    }
    if existing:
        prefs["city"]           = existing.get("city")           or prefs["city"]
        prefs["news_country"]   = existing.get("news_country")   or prefs["news_country"]
        prefs["favorite_genre"] = existing.get("favorite_genre") or prefs["favorite_genre"]
    if preferences:
        if preferences.get("city"):
            prefs["city"] = preferences["city"]
        if preferences.get("news_country"):
            prefs["news_country"] = preferences["news_country"]
        if preferences.get("favorite_genre"):
            prefs["favorite_genre"] = preferences["favorite_genre"]

    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO users (
                name, recording_count,
                pitch_mean, pitch_std, pitch_min, pitch_max,
                energy_mean, energy_std, speech_rate,
                spectral_centroid, spectral_bandwidth,
                city, news_country, favorite_genre,
                embedding_centroid, mfcc_mean
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                recording_count    = excluded.recording_count,
                pitch_mean         = excluded.pitch_mean,
                pitch_std          = excluded.pitch_std,
                pitch_min          = excluded.pitch_min,
                pitch_max          = excluded.pitch_max,
                energy_mean        = excluded.energy_mean,
                energy_std         = excluded.energy_std,
                speech_rate        = excluded.speech_rate,
                spectral_centroid  = excluded.spectral_centroid,
                spectral_bandwidth = excluded.spectral_bandwidth,
                city               = excluded.city,
                news_country       = excluded.news_country,
                favorite_genre     = excluded.favorite_genre,
                embedding_centroid = excluded.embedding_centroid,
                mfcc_mean          = excluded.mfcc_mean
            """,
            (
                name, recording_count,
                pitch.get("mean"),   pitch.get("std"),
                pitch.get("min"),    pitch.get("max"),
                energy.get("mean"),  energy.get("std"),
                voice_profile.get("speech_rate"),
                spectral.get("centroid"), spectral.get("bandwidth"),
                prefs["city"], prefs["news_country"], prefs["favorite_genre"],
                emb_json, mfcc_json,
            ),
        )
        conn.commit()

        row = conn.execute(
            "SELECT speaker_id FROM users WHERE LOWER(name) = LOWER(?)", (name,)
        ).fetchone()
        speaker_id = row["speaker_id"]

        recordings = voice_profile.get("recordings", [])
        if recordings:
            conn.execute("DELETE FROM recordings WHERE speaker_id = ?", (speaker_id,))
            conn.executemany(
                "INSERT INTO recordings (speaker_id, filename) VALUES (?, ?)",
                [(speaker_id, fn) for fn in recordings],
            )
            conn.commit()

        return speaker_id
    finally:
        conn.close()


def update_preferences(name: str, preferences: dict) -> bool:
    init_db()
    user = get_user(name)
    if user is None:
        return False

    updates = {}
    if "city" in preferences:
        updates["city"] = preferences["city"]
    if "news_country" in preferences:
        updates["news_country"] = preferences["news_country"]
    if "favorite_genre" in preferences:
        updates["favorite_genre"] = preferences["favorite_genre"]

    if not updates:
        return True

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values     = list(updates.values()) + [user["speaker_id"]]

    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE users SET {set_clause} WHERE speaker_id = ?", values
        )
        conn.commit()
        return True
    finally:
        conn.close()


def get_preferences(name: str) -> dict:
    init_db()
    user = get_user(name)
    if user is None:
        return {"city": "Bengaluru", "news_country": "India", "favorite_genre": "Pop"}
    return {
        "city":           user.get("city")           or "Bengaluru",
        "news_country":   user.get("news_country")   or "India",
        "favorite_genre": user.get("favorite_genre") or "Pop",
    }


def delete_user(name: str) -> bool:
    init_db()
    user = get_user(name)
    if user is None:
        return False

    speaker_id = user["speaker_id"]
    conn = get_connection()
    try:
        conn.execute("DELETE FROM recordings WHERE speaker_id = ?", (speaker_id,))
        conn.execute("DELETE FROM users WHERE speaker_id = ?", (speaker_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def update_priority(name: str, priority: int) -> bool:
    init_db()
    user = get_user(name)
    if user is None:
        return False
    priority = max(1, min(5, priority))
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE users SET priority = ? WHERE speaker_id = ?",
            (priority, user["speaker_id"]),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def list_enrolled() -> list[str]:
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT name FROM users ORDER BY speaker_id"
        ).fetchall()
        return [r["name"] for r in rows]
    finally:
        conn.close()
