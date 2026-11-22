"""
A small sliding-window rate limiter (security finding SEC-02).

"At most N events in any W-second window": we keep the timestamps of recent
events, drop those older than W seconds, and allow a new event only if fewer
than N remain.

It's pure logic (the caller stores the timestamps, e.g. in Streamlit's
session_state, and passes the current time), so it's easy to test.

Scope: this limits ONE browser session. It can't stop someone opening many
sessions; that needs a reverse proxy in front of the app. Because the app
listens on localhost only (.streamlit/config.toml), that's acceptable here.
"""

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
