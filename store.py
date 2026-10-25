"""Privacy-first persistence layer.

The only identifier ever stored is user_id = HMAC-SHA256(lowercased email, PEPPER).
Email, name and photo are never written anywhere.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import hmac

ATTEMPT_FIELDS = ("question_id", "topic", "difficulty", "correct", "trap_type", "created_at")
PROFILE_DEFAULTS = {
    "streak": 0, "best_streak": 0, "usage_day": None, "ai_used": 0,
    "plan": "free", "pro_until": None, "review_queue": {}, "pending_payment_ref": None,
}


def user_id_hash(email: str, pepper: str) -> str:
    if not email or not pepper:
        raise ValueError("email and pepper are required")
    return hmac.new(pepper.encode(), email.strip().lower().encode(), hashlib.sha256).hexdigest()


def clean_attempt(a: dict) -> dict:
    """Whitelist fields so nothing personal can slip into storage."""
    return {
        "question_id": str(a.get("question_id") or a.get("id", ""))[:64],
        "topic": str(a.get("topic", ""))[:64],
        "difficulty": str(a.get("difficulty", ""))[:32],
        "correct": bool(a.get("correct")),
        "trap_type": str(a.get("trap_type", ""))[:120],
        "created_at": a.get("created_at") or dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def clean_profile(p: dict) -> dict:
    return {k: p.get(k, v) for k, v in PROFILE_DEFAULTS.items()}


class MemoryStore:
    """In-memory backend (used for tests and as a stand-in)."""
    def __init__(self):
        self.profiles: dict[str, dict] = {}
        self.attempts: list[dict] = []

    def load(self, uid):
        p = copy.deepcopy(self.profiles.get(uid)) or clean_profile({})
        return p, [ {k: a[k] for k in ATTEMPT_FIELDS} for a in self.attempts if a["user_id"] == uid]

    def save_profile(self, uid, profile):
        self.profiles[uid] = clean_profile(copy.deepcopy(profile))

    def add_attempt(self, uid, attempt):
        self.attempts.append({"user_id": uid, **clean_attempt(attempt)})

    def delete_all(self, uid):
        self.profiles.pop(uid, None)
        self.attempts = [a for a in self.attempts if a["user_id"] != uid]


class SupabaseStore:
    """Supabase backend. Uses the service-role key, which must stay server-side (Streamlit secrets)."""
    def __init__(self, url, key, client=None):
        if client is None:
            from supabase import create_client
            client = create_client(url, key)
        self.db = client

    def load(self, uid):
        rows = self.db.table("profiles").select("*").eq("user_id", uid).execute().data
        profile = clean_profile(rows[0]) if rows else clean_profile({})
        att = (self.db.table("attempts").select(",".join(ATTEMPT_FIELDS))
               .eq("user_id", uid).order("created_at").execute().data) or []
        return profile, att

    def save_profile(self, uid, profile):
        row = {"user_id": uid, **clean_profile(profile),
               "updated_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        self.db.table("profiles").upsert(row).execute()

    def add_attempt(self, uid, attempt):
        self.db.table("attempts").insert({"user_id": uid, **clean_attempt(attempt)}).execute()

    def delete_all(self, uid):
        self.db.table("attempts").delete().eq("user_id", uid).execute()
        self.db.table("profiles").delete().eq("user_id", uid).execute()


def export_data(store, uid) -> dict:
    profile, attempts = store.load(uid)
    return {"user_id": uid, "exported_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "profile": profile, "attempts": attempts,
            "note": "This is everything stored about you. No email, name or photo is stored."}


def is_pro(profile: dict, today: dt.date | None = None) -> bool:
    today = today or dt.date.today()
    pu = profile.get("pro_until")
    return bool(pu) and dt.date.fromisoformat(str(pu)[:10]) >= today
