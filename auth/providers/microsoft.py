import os
import streamlit as st
from authlib.integrations.requests_client import OAuth2Session
from auth.models import CurrentUser
from auth.providers.base import OAuthProvider

ALLOWED_DOMAINS = {"theopportunitytree.org"}

class MicrosoftProvider(OAuthProvider):

    AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
    TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    SCOPE = "openid email profile"
    REDIRECT_URI = os.getenv("MICROSOFT_REDIRECT_URI")

    def start_login(self) -> str:
        sess = OAuth2Session(
            client_id=os.getenv("MICROSOFT_CLIENT_ID"),
            scope=self.SCOPE,
            redirect_uri=self.REDIRECT_URI,
        )
        uri, _ = sess.create_authorization_url(self.AUTH_URL)
        return uri

    def handle_callback(self) -> Optional[CurrentUser]:
        q = st.query_params
        if "code" not in q:
            return None

        sess = OAuth2Session(
            client_id=os.getenv("MICROSOFT_CLIENT_ID"),
            redirect_uri=self.REDIRECT_URI,
        )

        token = sess.fetch_token(
            self.TOKEN_URL,
            code=q["code"],
            client_secret=os.getenv("MICROSOFT_CLIENT_SECRET"),
        )

        userinfo = sess.get("https://graph.microsoft.com/v1.0/me").json()

        email = userinfo.get("mail") or userinfo.get("userPrincipalName")
        domain = email.split("@")[-1]

        if domain not in ALLOWED_DOMAINS:
            st.error("Unauthorized domain.")
            return None

        return CurrentUser(
            email=email,
            name=userinfo.get("displayName", email),
            sub=userinfo.get("id"),
            provider="microsoft",
        )
