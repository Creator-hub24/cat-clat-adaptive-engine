"""Razorpay Payment Links for the Pro plan. No card data ever touches this app."""
from __future__ import annotations

import datetime as dt
import time

import requests

API = "https://api.razorpay.com/v1"
PRO_PRICE_PAISE = 99900   # Rs 999 per 30 days
INTRO_PRICE_PAISE = 59900  # Rs 599 for the first-ever Pro month
PRO_DAYS = 30


def make_reference(uid: str) -> str:
    # Razorpay reference_id: max 40 chars, unique per link
    return f"{uid[:24]}-{int(time.time())}"


def is_first_purchase(profile: dict) -> bool:
    """True only if this user has never had Pro. Uses the explicit pro_purchases counter, and also
    treats any pro_until ever set as a past purchase (covers DBs without the pro_purchases column)."""
    return not (int(profile.get("pro_purchases") or 0) > 0 or profile.get("pro_until"))


def price_for(profile: dict) -> int:
    """Amount in paise for this user's next Pro purchase."""
    return INTRO_PRICE_PAISE if is_first_purchase(profile) else PRO_PRICE_PAISE


def create_link(key_id, key_secret, uid, amount=PRO_PRICE_PAISE, callback_url=None, http=requests) -> dict:
    if amount not in (INTRO_PRICE_PAISE, PRO_PRICE_PAISE):
        raise ValueError(f"unexpected amount {amount}")
    ref = make_reference(uid)
    desc = "Pro - first month offer" if amount == INTRO_PRICE_PAISE else "Pro (30 days)"
    body = {"amount": amount, "currency": "INR", "reference_id": ref,
            "description": f"CAT/CLAT Adaptive Engine - {desc}",
            "notes": {"user_id": uid}, "reminder_enable": False}
    if callback_url:
        body.update(callback_url=callback_url, callback_method="get")
    r = http.post(f"{API}/payment_links", json=body, auth=(key_id, key_secret), timeout=15)
    r.raise_for_status()
    return {"reference_id": ref, "short_url": r.json()["short_url"], "amount": amount}


def verify_paid(key_id, key_secret, reference_id, expected_amount, http=requests) -> bool:
    """Paid only if the link for this reference is 'paid' AND both its amount and amount_paid equal
    the amount we expected to charge (so an Rs 599 link can't be passed off for a later Rs 999 month)."""
    r = http.get(f"{API}/payment_links", params={"reference_id": reference_id},
                 auth=(key_id, key_secret), timeout=15)
    r.raise_for_status()
    links = r.json().get("payment_links", [])
    return any(l.get("status") == "paid" and l.get("reference_id") == reference_id
               and l.get("currency", "INR") == "INR"
               and int(l.get("amount") or 0) == expected_amount
               and int(l.get("amount_paid") or 0) == expected_amount for l in links)


def extend_pro(profile: dict, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    cur = profile.get("pro_until")
    base = max(today, dt.date.fromisoformat(str(cur)[:10])) if cur else today
    profile["plan"] = "pro"
    profile["pro_until"] = (base + dt.timedelta(days=PRO_DAYS)).isoformat()
    profile["pending_payment_ref"] = None
    profile["pro_purchases"] = int(profile.get("pro_purchases") or 0) + 1  # intro offer now used
    return profile
