"""Razorpay Payment Links for the Pro plan. No card data ever touches this app."""
from __future__ import annotations

import datetime as dt
import time

import requests

API = "https://api.razorpay.com/v1"
PRO_DAYS = 30
LAUNCH_SEATS = 500  # "Founding 500": the first 500 paying users of each app get their first month at Rs 199
MRP_PAISE = 99900   # shown struck through next to the launch price

# plan key -> (amount in paise, days of Pro, description). The user picks a plan; the amount is fixed per plan.
PLANS = {
    "launch": (19900, 30, "Founding 500 offer - first month"),
    "monthly": (49900, 30, "Pro (30 days)"),
    "quarterly": (99900, 90, "Pro (3 months)"),
}
LAUNCH_PRICE_PAISE, PRO_PRICE_PAISE, QUARTERLY_PRICE_PAISE = (PLANS[k][0] for k in ("launch", "monthly", "quarterly"))


def make_reference(uid: str) -> str:
    # Razorpay reference_id: max 40 chars, unique per link
    return f"{uid[:24]}-{int(time.time())}"


def is_first_purchase(profile: dict) -> bool:
    """True only if this user has never had Pro. Uses the explicit pro_purchases counter, and also
    treats any pro_until ever set as a past purchase (covers DBs without the pro_purchases column)."""
    return not (int(profile.get("pro_purchases") or 0) > 0 or profile.get("pro_until"))


def launch_open(claims: int | None) -> bool:
    """Seats left in the Founding 500 offer. None (count unavailable, e.g. migration not run) = closed,
    so we never promise a seat we can't count."""
    return claims is not None and claims < LAUNCH_SEATS


def plans_for(profile: dict, launch_claims: int | None = None) -> list[str]:
    """Plans this user can buy now: a first-time buyer gets the Rs 199 first month while seats last
    (instead of monthly); everyone can pick the 3-month plan."""
    first = "launch" if is_first_purchase(profile) and launch_open(launch_claims) else "monthly"
    return [first, "quarterly"]


def plans_payable(profile: dict) -> list[str]:
    """Plans whose paid link we accept at verification. Launch needs a first purchase but not an open
    seat: the link was only created while a seat was open."""
    return (["launch"] if is_first_purchase(profile) else []) + ["monthly", "quarterly"]


def price_for(profile: dict, launch_claims: int | None = None) -> int:
    """Amount in paise of this user's default (first-listed) plan."""
    return PLANS[plans_for(profile, launch_claims)[0]][0]


DEFAULT_APP_NAME = "CAT/CLAT Adaptive Engine"


def create_link(key_id, key_secret, uid, plan="monthly", callback_url=None, http=requests,
                app_name: str = DEFAULT_APP_NAME, exam_family: str = "mgmt_law") -> dict:
    """One Razorpay account/keys for every app; the app name, exam_family and plan go in the description
    and notes so the dashboard shows which app and plan each payment came from."""
    if plan not in PLANS:
        raise ValueError(f"unexpected plan {plan}")
    amount, _days, desc = PLANS[plan]
    ref = make_reference(uid)
    body = {"amount": amount, "currency": "INR", "reference_id": ref,
            "description": f"{app_name} - {desc}",
            "notes": {"user_id": uid, "exam_family": exam_family, "app": app_name, "plan": plan},
            "reminder_enable": False}
    if callback_url:
        body.update(callback_url=callback_url, callback_method="get")
    r = http.post(f"{API}/payment_links", json=body, auth=(key_id, key_secret), timeout=15)
    r.raise_for_status()
    return {"reference_id": ref, "short_url": r.json()["short_url"], "amount": amount, "plan": plan}


def verify_paid(key_id, key_secret, reference_id, expected_amount, http=requests,
                exam_family: str | None = None) -> bool:
    """Paid only if the link for this reference is 'paid' AND both its amount and amount_paid equal
    the amount we expected to charge (so a cheaper link can't be passed off for a dearer plan)."""
    r = http.get(f"{API}/payment_links", params={"reference_id": reference_id},
                 auth=(key_id, key_secret), timeout=15)
    r.raise_for_status()
    links = r.json().get("payment_links", [])
    return any(l.get("status") == "paid" and l.get("reference_id") == reference_id
               and l.get("currency", "INR") == "INR"
               and int(l.get("amount") or 0) == expected_amount
               and int(l.get("amount_paid") or 0) == expected_amount
               and _family_ok(l, exam_family) for l in links)


def paid_plan(key_id, key_secret, reference_id, allowed_plans, http=requests,
              exam_family: str | None = None) -> str | None:
    """The plan a paid link for this reference bought, or None. The paid amount must equal the amount of
    one of allowed_plans (and the plan note, when present, must agree), so a cheaper link can't buy a
    longer plan and a launch link can't be used once the user is no longer a first-time buyer."""
    r = http.get(f"{API}/payment_links", params={"reference_id": reference_id},
                 auth=(key_id, key_secret), timeout=15)
    r.raise_for_status()
    for l in r.json().get("payment_links", []):
        if not (l.get("status") == "paid" and l.get("reference_id") == reference_id
                and l.get("currency", "INR") == "INR" and _family_ok(l, exam_family)):
            continue
        amt, paid = int(l.get("amount") or 0), int(l.get("amount_paid") or 0)
        note = (l.get("notes") or {}).get("plan")
        for plan in allowed_plans:
            if PLANS[plan][0] == amt == paid and note in (None, plan):
                return plan
    return None


def _family_ok(link: dict, exam_family: str | None) -> bool:
    """A link created by another app can't unlock this one. Old links without the note count as mgmt_law."""
    if exam_family is None:
        return True
    return ((link.get("notes") or {}).get("exam_family") or "mgmt_law") == exam_family


def extend_pro(profile: dict, today: dt.date | None = None, days: int = PRO_DAYS) -> dict:
    today = today or dt.date.today()
    cur = profile.get("pro_until")
    base = max(today, dt.date.fromisoformat(str(cur)[:10])) if cur else today
    profile["plan"] = "pro"
    profile["pro_until"] = (base + dt.timedelta(days=days)).isoformat()
    profile["pending_payment_ref"] = None
    profile["pro_purchases"] = int(profile.get("pro_purchases") or 0) + 1  # first-purchase (launch) offer now used
    return profile
