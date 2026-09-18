import streamlit as st
from src.agent.Chat_Router.chat_router import ChatRouter

def render_chat_tab():
    
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if user_prompt := st.chat_input("Ex: 'Où en est ma candidature chez Google ?' ou 'Envoie une relance'"):
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)

        # Délégation totale au ChatRouter
        router = ChatRouter()
        bot_response = router.route_intent(user_prompt, chat_history=st.session_state.messages[:-1])

        st.session_state.messages.append({"role": "assistant", "content": bot_response})
        with st.chat_message("assistant"):
            st.markdown(bot_response)