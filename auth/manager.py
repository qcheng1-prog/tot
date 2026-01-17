import streamlit as st
from auth.providers.google import GoogleProvider
from auth.providers.microsoft import MicrosoftProvider

class AuthManager:

    PROVIDERS = {
        "google": GoogleProvider(),
        #"microsoft": MicrosoftProvider(),
    }

    @classmethod
    def login(cls, provider_name: str):
        # 1. Get the URL from the provider
        url = cls.PROVIDERS[provider_name].start_login()
    
        # 2. Use a JavaScript redirect to force the browser to leave IMMEDIATELY
        # This prevents the user from seeing a second "Continue" link
        js = f"""
        <script>
            window.location.href = "{url}";
        </script>
        """
        st.components.v1.html(js, height=0)
    
        # 3. Fallback for browsers with JS blocked
        st.markdown(f"Redirecting to {provider_name.title()}... [Click here if not redirected]({url})")
        
    @classmethod
    def handle_callback(cls):
        st.write("auth manager handle_callback()")
        # ⛔ Already logged in → skip OAuth logic
        #st.write("handle_callback()\n")
        #st.write(st.session_state)
        if "current_user" in st.session_state:
            return st.session_state["current_user"]
        for provider in cls.PROVIDERS.values():
            user = provider.handle_callback()
            #st.write(user)
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
