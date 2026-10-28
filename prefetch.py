"""Pro speed: serve an instant bank question while the next verified AI question is generated
in the background. No Streamlit import; the worker must never touch st.session_state."""
from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable


class Prefetcher:
    """At most one background AI generation per browser session, tagged with (topic, difficulty)."""

    def __init__(self, executor: ThreadPoolExecutor | None = None):
        self.executor = executor or ThreadPoolExecutor(max_workers=1, thread_name_prefix="ai-prefetch")
        self.future: Future | None = None
        self.key: tuple | None = None

    @property
    def busy(self) -> bool:
        return self.future is not None and not self.future.done()

    def start(self, key: tuple, fn: Callable[[], dict]) -> bool:
        if self.future is not None:  # one in flight (or a finished one not yet served)
            return False
        self.key, self.future = key, self.executor.submit(fn)
        return True

    def take(self, key: tuple, wait: float | None = 0) -> dict | None:
        """The prefetched question if ready, for this key, and successful. Failures are dropped
        silently; a finished question for another topic/level is discarded."""
        f = self.future
        if f is None:
            return None
        if not f.done():
            if not wait:
                return None
            try:
                f.result(timeout=wait)
            except Exception:
                pass
            if not f.done():
                return None
        k, self.future, self.key = self.key, None, None
        if f.exception() is not None or k != key:
            return None
        return f.result()


def serve_pro(pf: Prefetcher, key: tuple, *, bank: Callable[[], dict | None],
              may_serve_ai: Callable[[], bool], may_start_ai: Callable[[], bool],
              make_job: Callable[[], Callable[[], dict]], on_ai_served: Callable[[dict], None],
              wait_if_empty: float = 0) -> tuple[dict | None, str]:
    """Return (question, source) with source in {"prefetch", "bank", "none"}.
    1) ready prefetched AI question (if the cap/session still allow it) -> counted via on_ai_served;
    2) else an instant bank question;
    3) if the bank is exhausted, optionally wait for the in-flight prefetch.
    Then start the next prefetch if fair-use checks allow it."""
    q, src = None, "none"
    ready = pf.take(key) if may_serve_ai() else None
    if ready:
        q, src = ready, "prefetch"
    else:
        q = bank()
        if q is not None:
            src = "bank"
        elif wait_if_empty and pf.future is None and may_start_ai():
            pf.start(key, make_job())
            q = pf.take(key, wait=wait_if_empty)
            src = "prefetch" if q else "none"
        elif wait_if_empty and pf.future is not None:
            q = pf.take(key, wait=wait_if_empty)
            src = "prefetch" if q else "none"
    if src == "prefetch":
        on_ai_served(q)
    if pf.future is None and may_start_ai():
        pf.start(key, make_job())
    return q, src
