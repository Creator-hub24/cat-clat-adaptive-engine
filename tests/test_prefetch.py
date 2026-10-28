import threading
import time

import prefetch


class Calls:
    def __init__(self):
        self.started, self.served, self.ok_serve, self.ok_start = 0, [], True, True


def run(pf, c, bank_q=None, key=("T", "Easy"), job=None, wait=0):
    def make_job():
        c.started += 1
        return job or (lambda: {"id": f"AI-{c.started}", "source": "AI"})
    return prefetch.serve_pro(pf, key, bank=lambda: bank_q, may_serve_ai=lambda: c.ok_serve,
                              may_start_ai=lambda: c.ok_start, make_job=make_job,
                              on_ai_served=c.served.append, wait_if_empty=wait)


def settle(pf):
    if pf.future:
        pf.future.exception(timeout=5)


def test_bank_first_then_prefetched_ai_served_and_counted():
    pf, c = prefetch.Prefetcher(), Calls()
    q, src = run(pf, c, bank_q={"id": "B1"})
    assert (q["id"], src, c.started, c.served) == ("B1", "bank", 1, [])
    settle(pf)
    q, src = run(pf, c, bank_q={"id": "B2"})
    assert (q["id"], src) == ("AI-1", "prefetch") and len(c.served) == 1
    assert c.started == 2  # next one prefetching


def test_not_ready_serves_bank_without_duplicate_prefetch():
    pf, c, gate = prefetch.Prefetcher(), Calls(), threading.Event()
    run(pf, c, bank_q={"id": "B1"}, job=lambda: (gate.wait(5), {"id": "AI"})[1])
    q, src = run(pf, c, bank_q={"id": "B2"})
    assert src == "bank" and c.started == 1 and c.served == []
    gate.set()


def test_failure_falls_back_silently():
    pf, c = prefetch.Prefetcher(), Calls()

    def boom():
        raise RuntimeError("verification failed")
    run(pf, c, bank_q={"id": "B1"}, job=boom)
    settle(pf)
    q, src = run(pf, c, bank_q={"id": "B2"})
    assert (q["id"], src, c.served) == ("B2", "bank", [])


def test_cap_or_session_blocks_serving_and_starting():
    pf, c = prefetch.Prefetcher(), Calls()
    run(pf, c, bank_q={"id": "B1"})
    settle(pf)
    c.ok_serve = c.ok_start = False  # cap reached / signed in elsewhere / cooldown
    q, src = run(pf, c, bank_q={"id": "B2"})
    assert src == "bank" and c.served == [] and c.started == 1


def test_topic_change_discards_stale_prefetch():
    pf, c = prefetch.Prefetcher(), Calls()
    run(pf, c, bank_q={"id": "B1"}, key=("T", "Easy"))
    settle(pf)
    q, src = run(pf, c, bank_q={"id": "B2"}, key=("U", "Hard"))
    assert src == "bank" and c.served == [] and pf.key == ("U", "Hard")


def test_bank_exhausted_waits_for_ai():
    pf, c = prefetch.Prefetcher(), Calls()
    q, src = run(pf, c, bank_q=None, job=lambda: (time.sleep(0.05), {"id": "AI-W"})[1], wait=5)
    assert (q["id"], src, len(c.served)) == ("AI-W", "prefetch", 1)


def test_bank_exhausted_and_ai_blocked_returns_none():
    pf, c = prefetch.Prefetcher(), Calls()
    c.ok_start = c.ok_serve = False
    assert run(pf, c, bank_q=None, wait=5) == (None, "none")
