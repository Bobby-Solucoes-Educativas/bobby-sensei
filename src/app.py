import streamlit as st

from core.chat_state import add_message, new_conversation
from core.chatbot_core import answer_question
from ui.chat_bubbles import render_assistant_message, render_user_message
from ui.sidebar import render_sidebar

st.set_page_config(page_title="Bobby Sensei", page_icon="🤖", layout="wide")

if "conversations" not in st.session_state:
    st.session_state.conversations = {}
    st.session_state.conversation_order = []
    st.session_state.active_id = None


def _start_new_conversation() -> None:
    """Cria uma conversa e a torna ativa (usado no bootstrap e após excluir a ativa)."""

    conversation = new_conversation()
    st.session_state.conversations[conversation.id] = conversation
    st.session_state.conversation_order.insert(0, conversation.id)
    st.session_state.active_id = conversation.id


if st.session_state.active_id is None:
    _start_new_conversation()

st.session_state.active_id = render_sidebar(
    st.session_state.conversations,
    st.session_state.conversation_order,
    st.session_state.active_id,
)

if st.session_state.active_id is None:
    _start_new_conversation()

active_conversation = st.session_state.conversations[st.session_state.active_id]

if not active_conversation.messages:
    st.markdown(
        """<div style="display:flex; flex-direction:column; align-items:center;
        justify-content:center; text-align:center; padding-top:16vh;">
            <div style="font-size:2.5rem;">🤖</div>
            <h1 style="margin:0.3rem 0;">Bobby Sensei</h1>
            <p style="opacity:0.7; font-size:1.05rem;">
                Assistente Pessoal da Bobby
            </p>
        </div>""",
        unsafe_allow_html=True,
    )
else:
    st.title("Bobby Sensei")
    st.caption("Assistente Pessoal da Bobby")
    for message in active_conversation.messages:
        if message.role == "user":
            render_user_message(message.content)
        else:
            render_assistant_message(message.content)

question = st.chat_input("Digite sua pergunta...")
if question:
    add_message(active_conversation, "user", question)
    add_message(active_conversation, "assistant", answer_question(question))
    st.rerun()
