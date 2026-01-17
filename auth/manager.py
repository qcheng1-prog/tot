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
        for provider in cls.PROVIDERS.values():
            user = provider.handle_callback()
            if user:
                st.session_state["current_user"] = user
                st.query_params.clear()
                return user
        return None

    @staticmethod
    def current_user():
        return st.session_state.get("current_user")

    @staticmethod
    def logout():
        st.session_state.clear()
