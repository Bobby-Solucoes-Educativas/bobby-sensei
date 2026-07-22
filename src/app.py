import streamlit as st

from core.chat_state import add_message, new_conversation
from core.chatbot_core import answer_question
from ui.chat_bubbles import (
    render_assistant_message,
    render_loading_message,
    render_user_message,
    scroll_to_bottom,
)
from ui.sidebar import render_sidebar
from ui.theme import BACKGROUND

st.set_page_config(page_title="Bobby Sensei", page_icon="./src/icon/Logo.png", layout="wide")

st.markdown(
    f"""<style>
        [data-testid="stAppViewContainer"],
        [data-testid="stBottom"],
        [data-testid="stBottom"] > div {{
            background-color: {BACKGROUND};
        }}
    </style>""",
    unsafe_allow_html=True,
)

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
            render_assistant_message(message.content, message.chunks)

    # A última mensagem sem resposta ainda é a pergunta recém-enviada pelo
    # usuário (ver bloco do chat_input abaixo, que só adiciona a mensagem do
    # usuário e dá rerun) — busca e gera a resposta agora, com o indicador de
    # carregamento já desenhado na tela antes da chamada bloqueante ao RAG.
    if active_conversation.messages[-1].role == "user":
        render_loading_message()
        scroll_to_bottom()
        pergunta = active_conversation.messages[-1].content
        resposta, chunks = answer_question(pergunta)
        add_message(active_conversation, "assistant", resposta, chunks)
        st.rerun()

scroll_to_bottom()

question = st.chat_input("Digite sua pergunta...")
if question:
    add_message(active_conversation, "user", question)
    st.rerun()
