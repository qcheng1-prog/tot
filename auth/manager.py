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
        # 1. Generate the URL (This sets the 'state' in session_state)
        url = cls.PROVIDERS[provider_name].start_login()
    
        # 2. Use JavaScript to redirect the browser IMMEDIATELY
        # window.parent is used because Streamlit apps run in an iframe
        st.components.v1.html(
            f"""
            <script>
                window.parent.location.href = "{url}";
            </script>
            """,
            height=0,
        )
    
        # 3. Stop the rest of the script so it doesn't render more buttons
        st.write(f"Redirecting to {provider_name.title()}...")
        st.stop()
        
    @classmethod
    def handle_callback(cls):
        #st.write("auth manager handle_callback()")
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
