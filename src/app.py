from pathlib import Path

import streamlit as st

from core.chat_state import Conversation, Message, add_message
from core.chatbot_core import answer_question
from core.db import ensure_schema
from core.store import (
    atualizar_titulo_conversa,
    carregar_historico,
    criar_conversa,
    papel_de_role,
    salvar_mensagem,
)
from ui.chat_bubbles import (
    render_assistant_message,
    render_user_message,
    scroll_to_bottom,
)
from ui.auth import render_logout_button, require_login
from ui.feedback import render_feedback_widget
from ui.sidebar import ensure_conversations_state, render_sidebar
from ui.theme import BACKGROUND
from ui.thinking import inject_thinking_styles, png_data_uri, thinking_indicator

st.set_page_config(page_title="Bobby Sensei", page_icon="./src/icon/Logo.png", layout="wide")
inject_thinking_styles()


@st.cache_resource
def _ensure_schema_once() -> None:
    """Executa o bootstrap idempotente do schema uma vez por processo.

    O runner aplica as migrations em `db/migrations/`, então banco novo e
    volume reaproveitado usam a mesma fonte de verdade sem recriar objetos já
    existentes.
    """

    ensure_schema()


_ensure_schema_once()

# Precisa vir depois do ensure_schema (a tabela `atendentes` só existe depois
# da migration 0009) e antes de qualquer UI do chat — barra tudo abaixo
# (st.stop()) até logar. A mesma identidade também autentica a classificação
# de feedback no dashboard (pages/1_Dashboard.py).
atendente_email = require_login()


def _persist(conversation: Conversation, message: Message, reply_to: int | None = None) -> None:
    """Salva a conversa (na 1ª mensagem) e a mensagem recém-adicionada
    (TAI7-13/14: histórico persistido pra alimentar o dashboard de feedback).

    `conversation.db_id`/`message.db_id` só existem depois do INSERT (o
    banco gera o id) — por isso a criação da conversa e o título só
    acontecem uma vez, na primeira mensagem persistida."""

    if conversation.db_id is None:
        conversation.db_id = criar_conversa(atendente=atendente_email)
        if conversation.title:
            atualizar_titulo_conversa(conversation.db_id, conversation.title)

    message.db_id = salvar_mensagem(
        conversation.db_id,
        papel_de_role(message.role),
        message.content,
        bot_respondeu=message.bot_respondeu,
        fontes=message.chunks,
        reply_to=reply_to,
    )


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

ensure_conversations_state()

st.session_state.active_id = render_sidebar(
    st.session_state.conversations,
    st.session_state.conversation_order,
    st.session_state.active_id,
)
render_logout_button()

ensure_conversations_state()

active_conversation = st.session_state.conversations[st.session_state.active_id]

if not active_conversation.messages:
    # Reaproveita a versão já reduzida da logo (mesma usada no indicador de
    # "pensando") em vez do Logo.png original (1330x1098px) — evita embutir
    # esse tanto de base64 na tela de boas-vindas a cada rerun.
    logo_uri = png_data_uri(str(Path(__file__).resolve().parent / "icon" / "logo-thinking.png"))
    st.markdown(
        f"""<div style="display:flex; flex-direction:column; align-items:center;
        justify-content:center; text-align:center; padding-top:16vh;">
            <img src="{logo_uri}" alt="" style="height:110px; width:auto; margin-bottom:0.5rem;" />
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
            render_feedback_widget(message)

    # A última mensagem sem resposta ainda é a pergunta recém-enviada pelo
    # usuário (ver bloco do chat_input abaixo, que só adiciona a mensagem do
    # usuário e dá rerun) — busca e gera a resposta agora, com o indicador de
    # "pensando" (logo respirando) já desenhado na tela antes da chamada
    # bloqueante ao RAG.
    if active_conversation.messages[-1].role == "user":
        pergunta_message = active_conversation.messages[-1]
        # Lê da tabela `mensagens` (não de active_conversation.messages em
        # memória): é a fonte de verdade persistida pela TAI7-13/14, a mesma
        # que qualquer outro canal (FastAPI/WhatsApp) usaria para montar o
        # histórico. `antes_de` exclui a própria pergunta pendente, que já foi
        # persistida (com db_id) no rerun anterior, antes deste bloco rodar.
        # O core corta esse histórico para caber na janela de contexto
        # (LIMIT_TOKENS_HISTORY_CONTEXT).
        history = carregar_historico(
            active_conversation.db_id, antes_de=pergunta_message.db_id
        )
        thinking_placeholder = st.empty()
        with thinking_indicator(thinking_placeholder):
            scroll_to_bottom()
            resposta, chunks, bot_respondeu = answer_question(
                pergunta_message.content, history
            )
        add_message(active_conversation, "assistant", resposta, chunks, bot_respondeu=bot_respondeu)
        _persist(active_conversation, active_conversation.messages[-1], reply_to=pergunta_message.db_id)
        st.rerun()

scroll_to_bottom()

question = st.chat_input("Digite sua pergunta...")
if question:
    add_message(active_conversation, "user", question)
    _persist(active_conversation, active_conversation.messages[-1])
    st.rerun()
