import requests
import streamlit as st
from streamlit_javascript import st_javascript


st.set_page_config(page_title="Calendar Agent", page_icon="📅")
st.title("Google Calendar Assistant")

#js_tz = st_javascript("""Intl.DateTimeFormat().resolvedOptions().timeZone""")

# Initialize Chat History
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display previous messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# User Input

if prompt := st.chat_input("What would you like to do with your calendar?"):
    # Add user message to UI
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. Call the FastAPI Backend
    # We send the history and the timezone detected by JS
    try:
        with st.spinner("Consulting your calendar..."):
            response = requests.post(
                "http://localhost:8000/chat", 
                json={
                    "message": prompt,
                    "history": st.session_state.messages[:-1], # Send history minus the prompt we just added
                    "timezone": "America/Los_Angeles" #js_tz if js_tz and js_tz != 0 else "UTC"
                }
            )
            response.raise_for_status()
            ai_response = response.json()["response"]

        # 3. Display Assistant Response
        with st.chat_message("assistant"):
            st.markdown(ai_response)
        st.session_state.messages.append({"role": "assistant", "content": ai_response})
        
    except Exception as e:
        st.error(f"Failed to connect to backend: {e}")