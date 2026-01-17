import os
import streamlit as st
from authlib.integrations.requests_client import OAuth2Session
from google.oauth2 import id_token
from google.auth.transport import requests
from auth.models import CurrentUser
from auth.providers.base import OAuthProvider
from typing import Optional

ALLOWED_DOMAINS = {"charlotte.edu"}

class GoogleProvider(OAuthProvider):

    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    SCOPE = "openid email profile"
    
    # Fallback to localhost if environment variable is not set
    #REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8501/oauth/callback") #"https://tot-uncc.streamlit.app") #/oauth/callback" )
    REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "https://tot-uncc.streamlit.app/oauth/callback")
    #REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "https://tot-uncc.streamlit.app/")
    def start_login(self) -> str:
        sess = OAuth2Session(
            client_id=os.getenv("GOOGLE_CLIENT_ID"),
            scope=self.SCOPE,
            redirect_uri=self.REDIRECT_URI,
        )
        uri, _ = sess.create_authorization_url(self.AUTH_URL, prompt="consent")
        return uri

    #def handle_callback() -> Optional[CurrentUser]:   #handle_oauth_callback()
    def handle_callback(self) -> Optional[CurrentUser]:
        #q = st.query_params
        #if "code" not in q or "state" not in q:
        #    return None
        q = st.query_params #st.experimental_get_query_params()
        #code = st.experimental_get_query_params().get("code", [None])[0]
        returned_state = q.get("state")
        code = q.get("code")
        
        store = _pkce_store()

        # Optional: prune old entries (10 min)
        now = time.time()
        for s in list(store.keys()):
            if now - store[s]["ts"] > 600:
                store.pop(s, None)

        entry = store.get(returned_state)
        if not entry:
            st.error("Invalid login state.")
            return None

        verifier = entry["verifier"]

        client_id, client_secret = _get_client()
        sess = _oauth_session(client_id)

        token = sess.fetch_token(
            self.TOKEN_URL,
            code=code,
            code_verifier=verifier,
            client_secret=client_secret,
        )

        idinfo = id_token.verify_oauth2_token(
            token["id_token"],
            google_requests.Request(),
            client_id,
        )   
        user = CurrentUser(
            email=idinfo["email"],
            name=idinfo.get("name", idinfo["email"]),
            picture=idinfo.get("picture"),
            sub=idinfo.get("sub"),
        )

        # Persist logged-in user
        st.session_state["current_user"] = user

        # One-time use: remove verifier + clear query params
        store.pop(returned_state, None)
        st.query_params.clear()

        return user
    
    def handle_callback_old(self) -> Optional[CurrentUser]:
        # Streamlit query params
        #q = st.experimental_get_query_params()
        q = st.query_params

        if "code" not in q:
            return None

        sess = OAuth2Session(
            client_id=os.getenv("GOOGLE_CLIENT_ID"),
            redirect_uri=self.REDIRECT_URI,
        )

        # Authlib requires code as a string
        code = q["code"][0] if isinstance(q["code"], list) else q["code"]

        token = sess.fetch_token(
            self.TOKEN_URL,
            code=code,
            client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        )
           
        idinfo = id_token.verify_oauth2_token(
            token["id_token"],
            requests.Request(),
            os.getenv("GOOGLE_CLIENT_ID"),
        )

        email = idinfo["email"]
        domain = email.split("@")[-1]

        if domain not in ALLOWED_DOMAINS:
            st.error("Unauthorized domain.")
            return None

        return CurrentUser(
            email=email,
            name=idinfo.get("name", email),
            picture=idinfo.get("picture"),
            sub=idinfo.get("sub"),
            provider="google",
        )
