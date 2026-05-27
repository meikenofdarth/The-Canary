"""State Store — Redis-backed session and profile management.

Provides real-time context caching, command history,
and pipeline metrics via Redis. Falls back to in-memory
dict if Redis is unavailable.
"""
import json
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class StateStore:
    """Redis-backed state store for user profiles, sessions, and history."""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.r = None
        self._connect()
        self._init_profiles()
    
    def _connect(self):
        """Connect to Redis, fall back to FallbackStateStore on failure."""
        try:
            import redis
            self.r = redis.from_url(self.redis_url, decode_responses=True)
            self.r.ping()
            logger.info("Connected to Redis at %s", self.redis_url)
        except Exception as e:
            logger.warning("Redis unavailable (%s), using in-memory fallback", e)
            self.r = None
    
    def _init_profiles(self):
        """Seed user profiles on startup."""
        profiles = {
            "hemang": {
                "role": "admin",
                "display_name": "Hemang",
                "preferences": json.dumps({"music_genre": "jazz", "language": "en"}),
                "permissions": json.dumps(["all"])
            },
            "sanchit": {
                "role": "guest",
                "display_name": "Sanchit",
                "preferences": json.dumps({"music_genre": "rock", "language": "en"}),
                "permissions": json.dumps(["lights", "music", "timer", "weather"])
            }
        }
        if self.r:
            for uid, profile in profiles.items():
                self.r.hset(f"user:{uid}", mapping=profile)
        else:
            self._fallback_profiles = profiles
    
    def get_profile(self, user_id: str) -> Optional[dict]:
        """Fetch user profile."""
        if self.r:
            data = self.r.hgetall(f"user:{user_id}")
            if data:
                # Deserialize JSON fields
                for key in ["preferences", "permissions"]:
                    if key in data:
                        data[key] = json.loads(data[key])
            return data or None
        return self._fallback_profiles.get(user_id)
    
    def get_role(self, user_id: str) -> str:
        """Get user role (admin/guest/unknown)."""
        profile = self.get_profile(user_id)
        return profile.get("role", "unknown") if profile else "unknown"
    
    def log_command(self, user_id: str, command: str, result: str):
        """Append to command history."""
        entry = json.dumps({
            "command": command, 
            "result": result, 
            "ts": time.time()
        })
        if self.r:
            self.r.lpush(f"history:{user_id}", entry)
            self.r.ltrim(f"history:{user_id}", 0, 99)
        else:
            if not hasattr(self, '_fallback_history'):
                self._fallback_history = {}
            self._fallback_history.setdefault(user_id, []).insert(0, entry)
    
    def get_command_history(self, user_id: str, limit: int = 10) -> list[dict]:
        """Get recent command history for a user."""
        if self.r:
            entries = self.r.lrange(f"history:{user_id}", 0, limit - 1)
            return [json.loads(e) for e in entries]
        history = getattr(self, '_fallback_history', {}).get(user_id, [])
        return [json.loads(e) for e in history[:limit]]
    
    def set_session(self, session_id: str, data: dict, ttl: int = 300):
        """Store session state with TTL."""
        if self.r:
            self.r.setex(f"session:{session_id}", ttl, json.dumps(data))
    
    def get_session(self, session_id: str) -> Optional[dict]:
        """Retrieve session state."""
        if self.r:
            raw = self.r.get(f"session:{session_id}")
            return json.loads(raw) if raw else None
        return None
    
    def log_pipeline_metric(self, metric_name: str, value: float):
        """Push pipeline metric for telemetry."""
        if self.r:
            self.r.lpush(f"metrics:{metric_name}", f"{time.time()}:{value}")
            self.r.ltrim(f"metrics:{metric_name}", 0, 999)
