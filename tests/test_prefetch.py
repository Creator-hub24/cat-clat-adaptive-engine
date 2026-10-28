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


def test_after_50_cap_pro_gets_bank_questions():
    import guard
    used = {"n": 0}
    pf, c = prefetch.Prefetcher(), Calls()
    c.ok_serve = c.ok_start = None  # replaced by cap-driven gates below

    def gate():
        return not guard.pro_cap_reached(used["n"])

    def make_job():
        c.started += 1
        return lambda: {"id": f"AI-{c.started}", "source": "AI"}

    def go(bank_id):
        return prefetch.serve_pro(pf, ("T", "Easy"), bank=lambda: {"id": bank_id}, may_serve_ai=gate,
                                  may_start_ai=gate, make_job=make_job,
                                  on_ai_served=lambda q: used.__setitem__("n", used["n"] + 1))
    assert guard.PRO_DAILY_AI_CAP == 50
    srcs = []
    for i in range(60):
        settle(pf)
        srcs.append(go(f"B{i}")[1])
    assert used["n"] == 50                      # exactly the cap is served as AI
    assert srcs[-5:] == ["bank"] * 5            # afterwards: bank questions, no errors
    started_at_cap = c.started
    go("Bx")
    assert c.started == started_at_cap          # no new AI generation once capped


def test_solver_uses_primary_model_first():
    import llm
    import prompts
    assert prompts.MODEL_CANDIDATES[0] == "gemini-3.6-flash"
    seen = []

    class M:
        def generate_content(self, model, contents, config):
            seen.append(model)
            return type("R", (), {"text": '{"answer": "A", "ambiguous": false}'})()

    client = type("C", (), {"models": M()})()
    llm.independent_solve(client, list(prompts.MODEL_CANDIDATES),
                          {"question_text": "q", "options": {"A": "1", "B": "2"}}, "gemini-3.6-flash")
    assert seen == ["gemini-3.6-flash"]
