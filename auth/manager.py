import streamlit as st
from auth.providers.google import GoogleProvider
from auth.providers.microsoft import MicrosoftProvider

class AuthManager:

    PROVIDERS = {
        "google": GoogleProvider(),
        "microsoft": MicrosoftProvider(),
    }

    @classmethod
    def login(cls, provider_name: str):
        url = cls.PROVIDERS[provider_name].start_login()
        st.markdown(f"[Continue with {provider_name.title()}]({url})")

    @classmethod
    def handle_callback(cls):
        # ⛔ Already logged in → skip OAuth logic
        if "current_user" in st.session_state:
            return st.session_state["current_user"]
        for provider in cls.PROVIDERS.values():
            user = provider.handle_callback()
            if user:
                # 1️⃣ Persist authenticated user
                st.session_state["current_user"] = user
                # 2️⃣ Remove OAuth params to prevent loops
                st.query_params.clear()
                # 3️⃣ Force Streamlit to continue to app
                st.rerun()
        return None

    @staticmethod
    def current_user():
        return st.session_state.get("current_user")

    @staticmethod
    def logout():
        st.session_state.clear()
