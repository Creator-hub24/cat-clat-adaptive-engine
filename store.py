"""Privacy-first persistence layer.

The only identifier ever stored is user_id = HMAC-SHA256(lowercased email, PEPPER).
Email, name and photo are never written anywhere.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import hmac

ATTEMPT_FIELDS = ("question_id", "topic", "difficulty", "correct", "trap_type", "time_taken_s",
                  "timing_class", "created_at")
REPORT_FIELDS = ("topic", "question_ref", "reason", "created_at")
REPORT_REASONS = ("Wrong answer key", "Ambiguous / two answers", "Explanation is wrong", "Typo or formatting", "Other")
PROFILE_DEFAULTS = {
    "streak": 0, "best_streak": 0, "usage_day": None, "ai_used": 0,
    "plan": "free", "pro_until": None, "review_queue": {}, "pending_payment_ref": None,
    "topic_levels": {}, "pro_purchases": 0,
}
OPTIONAL_COLUMNS = ("pro_purchases",)  # added by supabase/migrations/2026-10-27_pro_purchases.sql
DEFAULT_FAMILY = "mgmt_law"
# Per-app Pro (supabase/migrations/2026-10-28_pro_entitlements.sql): one row per (user_id, exam_family).
ENTITLEMENT_FIELDS = ("pro_until", "pro_purchases", "pending_payment_ref")
ENTITLEMENT_TABLE = "pro_entitlements"
PAYMENTS_TABLE = "consumed_payments"  # one row per Razorpay payment ref: Pro is extended once per payment
USER_TABLES = ("attempts", ENTITLEMENT_TABLE, "usage_guard", "abuse_events", PAYMENTS_TABLE)  # rows keyed by user_id
GUARD_TABLE = "usage_guard"      # per (user_id, exam_family): session token, IST-day AI count, cooldown
ABUSE_TABLE = "abuse_events"     # append-only log of speed-check triggers (for manual review only)
GUARD_FIELDS = ("session_token", "session_started_at", "ai_day", "ai_used", "cooldown_until")


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
        "time_taken_s": int(a["time_taken_s"]) if a.get("time_taken_s") is not None else None,
        "timing_class": str(a.get("timing_class") or "")[:32] or None,
        "created_at": a.get("created_at") or dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def clean_report(r: dict) -> dict:
    """Reports are anonymous: no user_id, only what is needed to fix the question."""
    reason = r.get("reason") if r.get("reason") in REPORT_REASONS else "Other"
    return {"topic": str(r.get("topic", ""))[:64], "question_ref": str(r.get("question_ref", ""))[:64],
            "reason": reason, "created_at": dt.datetime.now(dt.timezone.utc).isoformat()}


def question_ref(q: dict) -> str:
    """Seed IDs as-is; AI questions as a short content hash so reports can be de-duplicated."""
    if not str(q.get("id", "")).startswith("AI-"):
        return str(q.get("id"))
    return "AI-" + hashlib.sha256(q.get("question_text", "").encode()).hexdigest()[:16]


def clean_profile(p: dict) -> dict:
    return {k: p.get(k, v) for k, v in PROFILE_DEFAULTS.items()}


def _later(a, b):
    if not a or not b:
        return a or b
    return max(str(a)[:10], str(b)[:10])


def apply_entitlement(profile: dict, ent: dict | None, family: str) -> dict:
    """Overlay this app's Pro state on the shared profile.

    mgmt_law (the original app) still also keeps Pro on the profiles row, so it merges both (latest
    pro_until, highest purchase count). Every other family uses only its own entitlement row: Pro bought
    in one app never unlocks another, and each app has its own first-ever intro offer."""
    p = dict(profile)
    ent = ent or {}
    if family == DEFAULT_FAMILY:
        p["pro_until"] = _later(p.get("pro_until"), ent.get("pro_until"))
        p["pro_purchases"] = max(int(p.get("pro_purchases") or 0), int(ent.get("pro_purchases") or 0))
        p["pending_payment_ref"] = p.get("pending_payment_ref") or ent.get("pending_payment_ref")
    else:
        p["pro_until"] = ent.get("pro_until")
        p["pro_purchases"] = int(ent.get("pro_purchases") or 0)
        p["pending_payment_ref"] = ent.get("pending_payment_ref")
        p["plan"] = "pro" if p.get("pro_until") else "free"
    return p


def entitlement_row(uid: str, family: str, profile: dict) -> dict:
    return {"user_id": uid, "exam_family": family, "pro_until": profile.get("pro_until"),
            "pro_purchases": int(profile.get("pro_purchases") or 0),
            "pending_payment_ref": profile.get("pending_payment_ref")}


def shared_profile_row(profile: dict, family: str) -> dict:
    """Columns written to the shared profiles row. Non-default families never touch its Pro columns."""
    row = clean_profile(profile)
    if family != DEFAULT_FAMILY:
        for k in ("plan", *ENTITLEMENT_FIELDS):
            row.pop(k, None)
    return row


class MemoryStore:
    """In-memory backend (used for tests and as a stand-in)."""
    def __init__(self, family: str = DEFAULT_FAMILY):
        self.family = family
        self.entitlements_ok = True
        self.profiles: dict[str, dict] = {}
        self.entitlements: dict[tuple[str, str], dict] = {}
        self.attempts: list[dict] = []
        self.reports: list[dict] = []
        self.guards: dict[tuple[str, str], dict] = {}
        self.consumed: dict[str, dict] = {}  # shared across families, like the DB table
        self.abuse: list[dict] = []

    def consume_payment(self, ref, uid, plan=None):
        """True = first use of this payment ref (extend Pro); False = already used (do not extend)."""
        if ref in self.consumed:
            return False
        self.consumed[ref] = {"user_id": uid, "exam_family": self.family, "plan": plan}
        return True

    def launch_claims(self):
        """How many Founding-500 (launch) payments this app has recorded."""
        return sum(1 for v in self.consumed.values() if v["exam_family"] == self.family and v.get("plan") == "launch")

    def load_guard(self, uid):
        return copy.deepcopy(self.guards.get((uid, self.family)))

    def save_guard(self, uid, fields):
        g = self.guards.setdefault((uid, self.family), {})
        g.update({k: v for k, v in fields.items() if k in GUARD_FIELDS})
        return True

    def log_abuse(self, uid, kind, detail=""):
        self.abuse.append({"user_id": uid, "exam_family": self.family, "kind": kind, "detail": str(detail)[:200]})
        return True

    def add_report(self, report):
        self.reports.append(clean_report(report))

    def load(self, uid):
        p = copy.deepcopy(self.profiles.get(uid)) or clean_profile({})
        p = apply_entitlement(p, self.entitlements.get((uid, self.family)), self.family)
        return p, [{k: a[k] for k in ATTEMPT_FIELDS} for a in self.attempts
                   if a["user_id"] == uid and a.get("exam_family", DEFAULT_FAMILY) == self.family]

    def save_profile(self, uid, profile):
        row = {**clean_profile(self.profiles.get(uid) or {}), **shared_profile_row(copy.deepcopy(profile), self.family)}
        self.profiles[uid] = row
        self.entitlements[(uid, self.family)] = entitlement_row(uid, self.family, profile)

    def add_attempt(self, uid, attempt):
        self.attempts.append({"user_id": uid, "exam_family": self.family, **clean_attempt(attempt)})

    def delete_all(self, uid):
        self.profiles.pop(uid, None)
        self.entitlements = {k: v for k, v in self.entitlements.items() if k[0] != uid}
        self.attempts = [a for a in self.attempts if a["user_id"] != uid]
        self.guards = {k: v for k, v in self.guards.items() if k[0] != uid}
        self.consumed = {k: v for k, v in self.consumed.items() if v["user_id"] != uid}
        self.abuse = [a for a in self.abuse if a["user_id"] != uid]


class SupabaseStore:
    """Supabase backend. Uses the service-role key, which must stay server-side (Streamlit secrets)."""
    family = DEFAULT_FAMILY
    _ent_loaded = False     # mirror mgmt_law Pro into pro_entitlements only once the table is known to exist
    _family_col = True      # attempts.exam_family exists (False until the migration is run)
    entitlements_ok = True  # False once we learn the pro_entitlements table is missing

    def __init__(self, url, key, client=None, family: str = DEFAULT_FAMILY):
        if client is None:
            from supabase import create_client
            client = create_client(url, key)
        self.db = client
        self.family = family
        self.entitlements_ok = True

    def _load_entitlement(self, uid):
        try:
            rows = (self.db.table(ENTITLEMENT_TABLE).select("*").eq("user_id", uid)
                    .eq("exam_family", self.family).execute().data)
            self.entitlements_ok = self._ent_loaded = True
            return rows[0] if rows else None
        except Exception:
            # Migration not run yet: mgmt_law keeps working from profiles; other apps disable Pro.
            self.entitlements_ok = False
            return None

    def load(self, uid):
        rows = self.db.table("profiles").select("*").eq("user_id", uid).execute().data
        profile = clean_profile(rows[0]) if rows else clean_profile({})
        profile = apply_entitlement(profile, self._load_entitlement(uid), self.family)
        att = self._load_attempts(uid)
        return profile, att

    def _load_attempts(self, uid):
        """Only this app's attempts (attempts.exam_family). Before the migration every row is mgmt_law."""
        q = self.db.table("attempts").select(",".join(ATTEMPT_FIELDS)).eq("user_id", uid)
        try:
            return q.eq("exam_family", self.family).order("created_at").execute().data or []
        except Exception:
            self._family_col = False
            if self.family != DEFAULT_FAMILY:
                return []
            return (self.db.table("attempts").select(",".join(ATTEMPT_FIELDS))
                    .eq("user_id", uid).order("created_at").execute().data) or []

    def save_profile(self, uid, profile):
        row = {"user_id": uid, **shared_profile_row(profile, self.family),
               "updated_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        try:
            self.db.table("profiles").upsert(row).execute()
        except Exception as e:
            # Tolerate a DB where the migration hasn't been run yet: retry without the new column(s).
            # payments.is_first_purchase() then falls back to "pro_until present => not first".
            if not any(c in str(e) for c in OPTIONAL_COLUMNS):
                raise
            self.db.table("profiles").upsert({k: v for k, v in row.items() if k not in OPTIONAL_COLUMNS}).execute()
        self._save_entitlement(uid, profile)

    def _save_entitlement(self, uid, profile):
        if self.family == DEFAULT_FAMILY and not self._ent_loaded:
            return  # table not confirmed yet: the profiles row is the source of truth for mgmt_law
        row = {**entitlement_row(uid, self.family, profile),
               "updated_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        try:
            self.db.table(ENTITLEMENT_TABLE).upsert(row).execute()
            self.entitlements_ok = True
        except Exception:
            self.entitlements_ok = False
            if self.family != DEFAULT_FAMILY and (profile.get("pro_until") or profile.get("pending_payment_ref")):
                raise  # other apps store Pro only here: never silently lose a paid entitlement  # mgmt_law: profiles row above already holds Pro

    def consume_payment(self, ref, uid, plan=None):
        """Insert-before-extend. True = this call consumed the ref; False = it was already consumed
        (unique violation: another session/replay won, so do NOT extend); None = table unavailable
        (caller falls back to the old behaviour). The plan is recorded so launch seats can be counted;
        before supabase/migrations/2026-10-31_launch_offer.sql the row is inserted without it."""
        row = {"payment_ref": ref, "user_id": uid, "exam_family": self.family}
        rows = [{**row, "plan": plan}, row] if plan else [row]
        for i, r in enumerate(rows):
            try:
                self.db.table(PAYMENTS_TABLE).insert(r).execute()
                return True
            except Exception as e:
                msg = f"{getattr(e, 'code', '')} {e}".lower()
                if "23505" in msg or "duplicate key" in msg or "unique" in msg:
                    return False
                if i == 0 and len(rows) > 1 and "plan" in msg:
                    continue  # plan column not migrated yet: record the ref without it
                return None
        return None

    def launch_claims(self):
        """Founding-500 (launch) payments recorded for this app, or None if they can't be counted
        (migration not run): the launch offer then stays hidden rather than over-promising seats."""
        try:
            res = (self.db.table(PAYMENTS_TABLE).select("payment_ref", count="exact")
                   .eq("exam_family", self.family).eq("plan", "launch").execute())
            return int(res.count) if res.count is not None else None
        except Exception:
            return None

    # ---- fair use (all best-effort: a missing table never breaks practice)
    def load_guard(self, uid):
        try:
            rows = (self.db.table(GUARD_TABLE).select("*").eq("user_id", uid)
                    .eq("exam_family", self.family).execute().data)
            return rows[0] if rows else {}
        except Exception:
            return None  # None = table missing/unavailable

    def save_guard(self, uid, fields):
        row = {"user_id": uid, "exam_family": self.family,
               **{k: v for k, v in fields.items() if k in GUARD_FIELDS},
               "updated_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        try:
            self.db.table(GUARD_TABLE).upsert(row).execute()
            return True
        except Exception:
            return False

    def log_abuse(self, uid, kind, detail=""):
        try:
            self.db.table(ABUSE_TABLE).insert({"user_id": uid, "exam_family": self.family, "kind": kind,
                                                 "detail": str(detail)[:200]}).execute()
            return True
        except Exception:
            return False

    def add_report(self, report):
        self.db.table("question_reports").insert(clean_report(report)).execute()

    def add_attempt(self, uid, attempt):
        row = {"user_id": uid, **clean_attempt(attempt)}
        if self._family_col:
            try:
                self.db.table("attempts").insert({**row, "exam_family": self.family}).execute()
                return
            except Exception as e:
                if "exam_family" not in str(e):
                    raise
                self._family_col = False
        self.db.table("attempts").insert(row).execute()

    def delete_all(self, uid):
        # Explicit deletes (not only FK cascade) so erasure works even if a table lacks the FK.
        # question_reports holds no user identifier, so there is nothing to delete there.
        for table in USER_TABLES:
            try:
                self.db.table(table).delete().eq("user_id", uid).execute()
            except Exception:
                if table == "attempts":
                    raise
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
