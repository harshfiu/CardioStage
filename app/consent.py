"""
Consent screen shown before the app can be used (once per browser session).

The project owner asked for consent to be requested wherever it might be
needed. Before anyone enters health information, they're told plainly:
  - this is an educational estimate, not medical advice or a diagnosis;
  - what happens to what they type (where it's processed, that CardioStage
    stores and logs nothing);
  - when the app is online: what the hosting platform itself collects.
Nothing in the app runs until they tick the box and press Continue.

Where the app runs is set by the CARDIOSTAGE_DEPLOYMENT environment
variable: "public" on Streamlit Community Cloud (set there as a secret,
which Community Cloud exposes as an environment variable); anything else,
or unset, means a local copy on someone's own computer.
"""

import os

import streamlit as st

STREAMLIT_PRIVACY_URL = "https://streamlit.io/privacy-policy"


def is_public_deployment() -> bool:
    return os.environ.get("CARDIOSTAGE_DEPLOYMENT", "").strip().lower() == "public"


def data_handling_text(public: bool) -> str:
    """How inputs are handled, in plain language (also shown on the About page)."""
    if public:
        return (
            "**What happens to what you enter.** Your answers are sent to the server that runs "
            "this app (Streamlit Community Cloud, hosted in the United States) only to compute "
            "the estimate. CardioStage does not store, log or share them, and they're gone when "
            "you close the tab. The app never asks for your name or any identifying details, so "
            "please don't add any.\n\n"
            "**What the host collects.** Streamlit Community Cloud collects its own usage "
            "statistics from visitors' browsers and shows the app's owner an anonymous viewer "
            "count. CardioStage can't switch this off. See the "
            f"[Streamlit privacy notice]({STREAMLIT_PRIVACY_URL})."
        )
    return (
        "**What happens to what you enter.** This copy of CardioStage runs on this computer. "
        "Your answers are used only to compute the estimate. They're never sent anywhere, "
        "stored or logged, and they're gone when you close the tab."
    )


def require_consent() -> None:
    """Show the consent screen and stop the page until the visitor agrees."""
    if st.session_state.get("consented"):
        return
    public = is_public_deployment()
    st.title("🫀 CardioStage")
    st.markdown("#### Before you start")
    st.warning(
        "**This is an educational project, not a medical device.** CardioStage gives an "
        "*estimate* learned from 243 patients in a 1980s US hospital dataset. It can be wrong, "
        "it is not a diagnosis, and it must not be used to make decisions about anyone's "
        "health. **If you have chest pain or think you may be having a heart attack, call "
        "your local emergency number now.**",
        icon="⚕️",
    )
    st.markdown(data_handling_text(public))
    agreed = st.checkbox(
        "I understand that this is an educational estimate, not medical advice, and how my "
        "answers are handled.",
        key="consent_ack",
    )
    if st.button("Continue", type="primary", disabled=not agreed, key="consent_continue"):
        st.session_state.consented = True
        st.rerun()
    st.stop()
