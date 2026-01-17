import os
import streamlit as st
from authlib.integrations.requests_client import OAuth2Session
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from typing import Optional
from auth.models import CurrentUser
from auth.providers.base import OAuthProvider

ALLOWED_DOMAINS = {"charlotte.edu"}


class GoogleProvider(OAuthProvider):
    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    SCOPE = "openid email profile"

    REDIRECT_URI = os.getenv(
        "GOOGLE_REDIRECT_URI",
        "https://tot-uncc.streamlit.app",  #/oauth/callback",
    )

    CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
    CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

    # ------------------------------------------------------------------
    # Step 1: Start login (redirect user to Google)
    # ------------------------------------------------------------------
    def start_login(self) -> str:
        #st.write("google - start_login()")
        sess = OAuth2Session(
            client_id=self.CLIENT_ID,
            scope=self.SCOPE,
            redirect_uri=self.REDIRECT_URI,
        )

        auth_url, state = sess.create_authorization_url(
            self.AUTH_URL,
            prompt="consent",
        )

        # Persist state for validation after redirect
        st.session_state["google_oauth_state"] = state

        return auth_url

    # ------------------------------------------------------------------
    # Step 2: Handle callback from Google
    # ------------------------------------------------------------------
    def handle_callback(self) -> Optional[CurrentUser]:
        st.write("google - handle_callback()")
        q = st.query_params

        code = q.get("code")
        returned_state = q.get("state")

        if not code or not returned_state:
            return None

        expected_state = st.session_state.get("google_oauth_state")

        if returned_state != expected_state:
            st.error("Invalid login state")
            return None

        sess = OAuth2Session(
            client_id=self.CLIENT_ID,
            redirect_uri=self.REDIRECT_URI,
        )

        token = sess.fetch_token(
            self.TOKEN_URL,
            code=code,
            client_secret=self.CLIENT_SECRET,
        )

        # Verify ID token
        idinfo = id_token.verify_oauth2_token(
            token["id_token"],
            google_requests.Request(),
            self.CLIENT_ID,
        )

        email = idinfo["email"]
        domain = email.split("@")[-1]

        if domain not in ALLOWED_DOMAINS:
            st.error("Unauthorized domain")
            return None

        user = CurrentUser(
            email=email,
            name=idinfo.get("name", email),
            picture=idinfo.get("picture"),
            sub=idinfo.get("sub"),
            provider="google",
        )

        # Clean up one-time values
        st.session_state.pop("google_oauth_state", None)
        st.query_params.clear()

        return user
