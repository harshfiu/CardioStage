"""Helpers for tests that drive the real app with Streamlit's AppTest."""


def accept_consent(at):
    """Tick the consent box and press Continue, as a visitor must before using the app."""
    at.checkbox(key="consent_ack").check().run()
    at.button(key="consent_continue").click().run()
    return at
