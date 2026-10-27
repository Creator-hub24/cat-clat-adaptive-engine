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


def test_price_for_first_purchase_only():
    assert payments.price_for(store.clean_profile({})) == payments.INTRO_PRICE_PAISE == 59900
    assert payments.price_for({"pro_purchases": 1}) == payments.PRO_PRICE_PAISE == 99900
    # expired Pro user on a DB without the new column: pro_until fallback => full price
    assert payments.price_for({"pro_until": "2026-01-01"}) == 99900


def test_extend_pro_sets_marker_and_next_price_is_full():
    p = payments.extend_pro(store.clean_profile({}), today=dt.date(2026, 10, 27))
    assert p["pro_purchases"] == 1 and p["pro_until"] == "2026-11-26" and p["plan"] == "pro"
    assert payments.price_for(p) == 99900
    assert payments.extend_pro(p, today=dt.date(2026, 10, 27))["pro_purchases"] == 2


def test_create_link_amount_and_description():
    h = FakeHttp()
    payments.create_link("k", "s", "u" * 64, payments.INTRO_PRICE_PAISE, http=h)
    assert h.posted["amount"] == 59900 and "first month offer" in h.posted["description"]
    payments.create_link("k", "s", "u" * 64, payments.PRO_PRICE_PAISE, http=h)
    assert h.posted["amount"] == 99900 and "Pro (30 days)" in h.posted["description"]
    with pytest.raises(ValueError):
        payments.create_link("k", "s", "u", 100, http=h)


def test_verify_paid_checks_amount():
    link = {"status": "paid", "reference_id": "r1", "amount": 59900, "amount_paid": 59900, "currency": "INR"}
    h = FakeHttp([link])
    assert payments.verify_paid("k", "s", "r1", 59900, http=h)
    assert not payments.verify_paid("k", "s", "r1", 99900, http=h)  # intro link can't pay a full month
    assert not payments.verify_paid("k", "s", "r2", 59900, http=h)
    h.links = [{**link, "amount_paid": 0, "status": "created"}]
    assert not payments.verify_paid("k", "s", "r1", 59900, http=h)


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
