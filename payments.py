"""Razorpay Payment Links for the Pro plan. No card data ever touches this app."""
from __future__ import annotations

import datetime as dt
import time

import requests

API = "https://api.razorpay.com/v1"
PRO_PRICE_PAISE = 99900
PRO_DAYS = 30


def make_reference(uid: str) -> str:
    # Razorpay reference_id: max 40 chars, unique per link
    return f"{uid[:24]}-{int(time.time())}"


def create_link(key_id, key_secret, uid, callback_url=None, http=requests) -> dict:
    ref = make_reference(uid)
    body = {"amount": PRO_PRICE_PAISE, "currency": "INR", "reference_id": ref,
            "description": "CAT/CLAT Adaptive Engine - Pro (30 days)",
            "notes": {"user_id": uid}, "reminder_enable": False}
    if callback_url:
        body.update(callback_url=callback_url, callback_method="get")
    r = http.post(f"{API}/payment_links", json=body, auth=(key_id, key_secret), timeout=15)
    r.raise_for_status()
    return {"reference_id": ref, "short_url": r.json()["short_url"]}


def verify_paid(key_id, key_secret, reference_id, http=requests) -> bool:
    r = http.get(f"{API}/payment_links", params={"reference_id": reference_id},
                 auth=(key_id, key_secret), timeout=15)
    r.raise_for_status()
    links = r.json().get("payment_links", [])
    return any(l.get("status") == "paid" and l.get("reference_id") == reference_id for l in links)


def extend_pro(profile: dict, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    cur = profile.get("pro_until")
    base = max(today, dt.date.fromisoformat(str(cur)[:10])) if cur else today
    profile["plan"] = "pro"
    profile["pro_until"] = (base + dt.timedelta(days=PRO_DAYS)).isoformat()
    profile["pending_payment_ref"] = None
    return profile
