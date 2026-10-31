import datetime as dt

import pytest

import payments
import store


class FakeResp:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class FakeHttp:
    def __init__(self, links=None):
        self.links, self.posted = links or [], None

    def post(self, url, json, auth, timeout):
        self.posted = json
        return FakeResp({"short_url": "https://rzp.io/x"})

    def get(self, url, params, auth, timeout):
        return FakeResp({"payment_links": self.links})


def test_plan_prices_and_days():
    assert {k: v[:2] for k, v in payments.PLANS.items()} == {
        "launch": (19900, 30), "monthly": (49900, 30), "quarterly": (99900, 90)}
    assert payments.LAUNCH_SEATS == 500 and payments.MRP_PAISE == 99900


def test_plans_for_launch_seats():
    new = store.clean_profile({})
    assert payments.plans_for(new, 0) == ["launch", "quarterly"]
    assert payments.plans_for(new, 499) == ["launch", "quarterly"]
    assert payments.plans_for(new, 500) == ["monthly", "quarterly"]      # all 500 seats taken
    assert payments.plans_for(new, None) == ["monthly", "quarterly"]     # can't count => never over-promise
    assert payments.plans_for({"pro_purchases": 1}, 0) == ["monthly", "quarterly"]  # launch is first month only
    assert payments.plans_for({"pro_until": "2026-01-01"}, 0) == ["monthly", "quarterly"]
    assert payments.price_for(new, 0) == 19900 and payments.price_for(new, 500) == 49900


def test_plans_payable():
    assert payments.plans_payable(store.clean_profile({})) == ["launch", "monthly", "quarterly"]
    assert payments.plans_payable({"pro_purchases": 1}) == ["monthly", "quarterly"]


def test_extend_pro_days_and_marker():
    p = payments.extend_pro(store.clean_profile({}), today=dt.date(2026, 10, 27))
    assert p["pro_purchases"] == 1 and p["pro_until"] == "2026-11-26" and p["plan"] == "pro"
    p = payments.extend_pro(p, today=dt.date(2026, 10, 27), days=90)   # 3-month plan stacks on remaining time
    assert p["pro_until"] == "2027-02-24" and p["pro_purchases"] == 2


def test_create_link_plans():
    h = FakeHttp()
    for plan, amt, desc in [("launch", 19900, "Founding 500"), ("monthly", 49900, "Pro (30 days)"),
                            ("quarterly", 99900, "Pro (3 months)")]:
        out = payments.create_link("k", "s", "u" * 64, plan, http=h)
        assert h.posted["amount"] == amt and desc in h.posted["description"]
        assert h.posted["notes"]["plan"] == plan and out["plan"] == plan and out["amount"] == amt
    with pytest.raises(ValueError):
        payments.create_link("k", "s", "u", 100, http=h)


def test_paid_plan_matches_amount_and_allowed():
    def link(amt, plan=None, **kw):
        notes = {"exam_family": "mgmt_law", **({"plan": plan} if plan else {})}
        return {"status": "paid", "reference_id": "r", "amount": amt, "amount_paid": amt, "currency": "INR",
                "notes": notes, **kw}
    allp = ["launch", "monthly", "quarterly"]
    assert payments.paid_plan("k", "s", "r", allp, http=FakeHttp([link(99900, "quarterly")])) == "quarterly"
    assert payments.paid_plan("k", "s", "r", allp, http=FakeHttp([link(19900, "launch")])) == "launch"
    # launch link no longer accepted once the user has bought Pro before
    assert payments.paid_plan("k", "s", "r", ["monthly", "quarterly"], http=FakeHttp([link(19900, "launch")])) is None
    # amount must match the plan note: a Rs 499 link can't claim 3 months
    assert payments.paid_plan("k", "s", "r", allp, http=FakeHttp([link(49900, "quarterly")])) is None
    assert payments.paid_plan("k", "s", "r", allp, http=FakeHttp([link(49900)])) == "monthly"  # older link, no note
    assert payments.paid_plan("k", "s", "r", allp, http=FakeHttp([link(99900, status="created")])) is None
    assert payments.paid_plan("k", "s", "r2", allp, http=FakeHttp([link(99900)])) is None
    assert payments.paid_plan("k", "s", "r", allp, http=FakeHttp([link(99900)]), exam_family="cuet") is None
    assert payments.paid_plan("k", "s", "r", allp, http=FakeHttp([{**link(99900), "amount_paid": 49900}])) is None


def test_launch_claims_counted_per_family():
    m = store.MemoryStore("cuet")
    m.consume_payment("p1", "u1", "launch")
    m.consume_payment("p2", "u2", "quarterly")
    law = store.MemoryStore("mgmt_law")
    law.consumed = m.consumed
    law.consume_payment("p3", "u3", "launch")
    assert m.launch_claims() == 1 and law.launch_claims() == 1


def test_verify_paid_checks_amount():
    link = {"status": "paid", "reference_id": "r1", "amount": 49900, "amount_paid": 49900, "currency": "INR"}
    h = FakeHttp([link])
    assert payments.verify_paid("k", "s", "r1", 49900, http=h)
    assert not payments.verify_paid("k", "s", "r1", 99900, http=h)  # intro link can't pay a full month
    assert not payments.verify_paid("k", "s", "r2", 49900, http=h)
    h.links = [{**link, "amount_paid": 0, "status": "created"}]
    assert not payments.verify_paid("k", "s", "r1", 49900, http=h)


def test_supabase_save_tolerates_missing_column():
    calls = []

    class T:
        def upsert(self, row):
            calls.append(row)
            self.row = row
            return self

        def execute(self):
            if "pro_purchases" in self.row:
                raise Exception("Could not find the 'pro_purchases' column of 'profiles'")

    class DB:
        def table(self, name):
            return T()

    st = store.SupabaseStore.__new__(store.SupabaseStore)
    st.db = DB()
    st.save_profile("u", {"pro_purchases": 1, "pro_until": "2026-11-26"})
    assert len(calls) == 2 and "pro_purchases" not in calls[1] and calls[1]["pro_until"] == "2026-11-26"
