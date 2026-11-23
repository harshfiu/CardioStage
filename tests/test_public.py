"""
Tests for what matters once the app is public: the consent screen, hidden
error details, and the rate limit shared by all visitors. None need models.
"""

import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = str(ROOT / "app" / "streamlit_app.py")
sys.path.insert(0, str(ROOT / "app"))

import consent  # noqa: E402
from cardiostage import ratelimit  # noqa: E402


# ---- consent screen -----------------------------------------------------------
def test_nothing_runs_before_consent():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    labels = [b.label for b in at.button]
    assert "Assess risk" not in labels  # the screener hasn't loaded
    assert at.button(key="consent_continue").disabled  # can't continue without ticking
    assert any("not a medical device" in w.value for w in at.warning)


def test_consent_unlocks_the_app():
    from streamlit.testing.v1 import AppTest

    from app_helpers import accept_consent

    at = accept_consent(AppTest.from_file(APP, default_timeout=180).run())
    assert not at.exception
    assert at.session_state.consented is True
    labels = [b.label for b in at.button]
    assert "Continue" not in labels  # the consent screen is gone
    # The screener now runs. Without trained models (e.g. in CI) it stops with a
    # friendly "models not found" message; with models it shows the Stage 1 form.
    models_message = any("models" in e.value.lower() for e in at.error)
    assert "Assess risk" in labels or models_message


def test_public_and_local_wording(monkeypatch):
    monkeypatch.setenv("CARDIOSTAGE_DEPLOYMENT", "public")
    assert consent.is_public_deployment()
    public = consent.data_handling_text(True)
    assert "United States" in public and "usage statistics" in public
    assert "does not store, log or share" in public
    monkeypatch.delenv("CARDIOSTAGE_DEPLOYMENT")
    assert not consent.is_public_deployment()
    local = consent.data_handling_text(False)
    assert "never sent anywhere" in local and "usage statistics" not in local


def test_error_details_forced_to_none():
    """Community Cloud overrides config.toml with `false` (= tracebacks); the app resets it."""
    from streamlit import config
    from streamlit.testing.v1 import AppTest

    config.set_option("client.showErrorDetails", "full")  # simulate a host override
    AppTest.from_file(APP, default_timeout=60).run()
    assert config.get_option("client.showErrorDetails") == "none"


# ---- rate limit shared by all visitors ----------------------------------------
def test_shared_limiter_caps_all_sessions_together():
    limiter = ratelimit.SharedLimiter(max_events=3, window_seconds=60)
    assert [limiter.try_acquire(100.0)[0] for _ in range(3)] == [True, True, True]
    allowed, wait = limiter.try_acquire(101.0)
    assert not allowed and wait > 0
    assert limiter.try_acquire(161.0)[0]  # window has passed


def test_shared_limiter_is_thread_safe():
    limiter = ratelimit.SharedLimiter(max_events=50, window_seconds=60)
    results = []

    def worker():
        for _ in range(20):
            results.append(limiter.try_acquire(1000.0)[0])

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(results) == 50  # exactly the cap, never more, despite 200 parallel attempts
