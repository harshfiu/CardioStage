"""
A small sliding-window rate limiter (security finding SEC-02).

"At most N events in any W-second window": we keep the timestamps of recent
events, drop those older than W seconds, and allow a new event only if fewer
than N remain.

It's pure logic (the caller stores the timestamps, e.g. in Streamlit's
session_state, and passes the current time), so it's easy to test.

Two scopes:
  - check_and_record: ONE browser session (the caller keeps the timestamps
    in Streamlit's session_state).
  - SharedLimiter: ALL sessions of one running app together, so opening many
    tabs can't overload a public server. One instance is shared by every
    session; a lock makes it safe when sessions run at the same time.
Neither replaces a reverse proxy for a serious deployment, but together they
keep the free public demo responsive.
"""

import threading

from cardiostage import config


def check_and_record(
    timestamps: list,
    now: float,
    max_events: int = config.RATE_LIMIT_MAX_ASSESSMENTS,
    window_seconds: float = config.RATE_LIMIT_WINDOW_SECONDS,
):
    """
    Decide whether a new event is allowed at time `now`.

    Returns (allowed, updated_timestamps, seconds_until_allowed).
    The new event is recorded only if allowed.
    """
    recent = [t for t in timestamps if now - t < window_seconds]
    if len(recent) >= max_events:
        wait = window_seconds - (now - min(recent))
        return False, recent, max(wait, 0.0)
    return True, recent + [now], 0.0


class SharedLimiter:
    """Sliding-window limit shared by every session of one app process."""

    def __init__(
        self,
        max_events: int = config.GLOBAL_RATE_LIMIT_MAX_ASSESSMENTS,
        window_seconds: float = config.GLOBAL_RATE_LIMIT_WINDOW_SECONDS,
    ):
        self.max_events, self.window_seconds = max_events, window_seconds
        self._times: list = []
        self._lock = threading.Lock()  # sessions run in parallel threads

    def try_acquire(self, now: float) -> tuple:
        """Returns (allowed, seconds_until_allowed); records the event if allowed."""
        with self._lock:
            allowed, self._times, wait = check_and_record(
                self._times, now, self.max_events, self.window_seconds
            )
            return allowed, wait
