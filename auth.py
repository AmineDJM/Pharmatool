"""Server-side password gate.

Security model: the check runs on the server and calls st.stop() BEFORE any
data is loaded or any page content is produced. An unauthenticated browser
never receives the app's data or layout, so the gate cannot be bypassed by
tampering with the page client-side.

The password is read from Streamlit secrets (st.secrets["app_password"]) when
available, with a fallback constant so the app also works out of the box.
For real deployments, set it in the Streamlit Cloud "Secrets" panel and keep
the GitHub repository private.
"""

import hmac
import time
from typing import Optional

import streamlit as st

_FALLBACK_PASSWORD = "24011971"
_MAX_ATTEMPTS = 5
_LOCK_SECONDS = 30


def _target_password() -> str:
    try:
        return str(st.secrets["app_password"])
    except Exception:
        return _FALLBACK_PASSWORD


def _is_correct(entered: str) -> bool:
    # constant-time comparison avoids leaking the password length/prefix via timing
    return hmac.compare_digest(str(entered), _target_password())


def _render_gate(message: Optional[str] = None):
    st.markdown(
        """
        <div class="hero" style="max-width:520px;margin:8vh auto 0 auto;text-align:center;">
          <div class="badge">🔒 Accès protégé</div>
          <h1 style="font-size:clamp(26px,4vw,40px);">Algeria Pharma<br/>Intelligence</h1>
          <p style="margin-left:auto;margin-right:auto;">Cet outil est réservé. Entre le mot de passe pour continuer.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    left, mid, right = st.columns([1, 1.4, 1])
    with mid:
        with st.form("auth_form", clear_on_submit=True):
            pwd = st.text_input("Mot de passe", type="password", placeholder="••••••••")
            ok = st.form_submit_button("Entrer", use_container_width=True)
        if message:
            st.error(message)
    return pwd if ok else None


def require_password() -> None:
    """Block the app until the correct password is entered. Call right after the
    theme is applied and BEFORE loading data or rendering any page."""
    if st.session_state.get("auth_ok"):
        return

    # brute-force throttle (per session)
    locked_until = st.session_state.get("auth_locked_until", 0)
    now = time.time()
    if now < locked_until:
        _render_gate(f"Trop de tentatives. Réessaie dans {int(locked_until - now)} s.")
        st.stop()

    entered = _render_gate()
    if entered is not None:
        if _is_correct(entered):
            st.session_state["auth_ok"] = True
            st.session_state["auth_attempts"] = 0
            st.rerun()
        else:
            attempts = st.session_state.get("auth_attempts", 0) + 1
            st.session_state["auth_attempts"] = attempts
            if attempts >= _MAX_ATTEMPTS:
                st.session_state["auth_locked_until"] = time.time() + _LOCK_SECONDS
                st.session_state["auth_attempts"] = 0
                _render_gate(f"Trop de tentatives. Verrouillé {_LOCK_SECONDS} s.")
            else:
                _render_gate(f"Mot de passe incorrect ({attempts}/{_MAX_ATTEMPTS}).")

    # Nothing below runs until authenticated: data is never loaded for a guest.
    st.stop()
