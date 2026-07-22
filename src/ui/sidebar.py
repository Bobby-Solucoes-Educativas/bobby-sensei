# TAI7-9: barra lateral com a lista de conversas. Só apresentação — a
# criação/renomeação/exclusão em si é feita pelas funções puras de
# core/chat_state.py; este módulo só desenha e liga aos cliques.
import streamlit as st

from core.chat_state import new_conversation, rename_conversation, toggle_pinned
from ui.theme import BLACK, LIME, WHITE, rgba

_SIDEBAR_BG = BLACK
_SIDEBAR_TEXT = "#F2F2F3"
_LIME_HOVER = "#D9FF70"  # LIME um tom mais claro, pro hover do botão ativo

_CSS = f"""<style>
[data-testid="stSidebar"] {{
    background-color: {_SIDEBAR_BG};
    border-right: 1px solid {rgba(LIME, 0.25)};
}}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {{
    color: {_SIDEBAR_TEXT};
}}
[data-testid="stSidebar"] button[kind="secondary"] {{
    background-color: {rgba(LIME, 0.08)};
    border-color: {rgba(LIME, 0.25)};
    color: {_SIDEBAR_TEXT};
}}
[data-testid="stSidebar"] button[kind="secondary"]:hover {{
    background-color: {rgba(LIME, 0.18)};
    border-color: {LIME};
    color: {WHITE};
}}
[data-testid="stSidebar"] button[kind="primary"],
[data-testid="stSidebar"] button[kind="primary"] p {{
    background-color: {LIME};
    border-color: {LIME};
    color: {BLACK} !important;
}}
[data-testid="stSidebar"] button[kind="primary"]:hover,
[data-testid="stSidebar"] button[kind="primary"]:hover p {{
    background-color: {_LIME_HOVER};
    border-color: {_LIME_HOVER};
    color: {BLACK} !important;
}}
[data-testid="stSidebar"] [data-testid="stTextInput"] input {{
    background-color: {rgba(LIME, 0.08)};
    color: {_SIDEBAR_TEXT};
}}
/* Menu "⋮" de cada conversa só aparece ao passar o mouse sobre a linha. */
div[class*="st-key-chat-row-"] [data-testid="stPopover"] {{
    opacity: 0;
    transition: opacity 0.12s ease-in-out;
}}
div[class*="st-key-chat-row-"]:hover [data-testid="stPopover"] {{
    opacity: 1;
}}
</style>"""


def render_sidebar(conversations: dict, conversation_order: list, active_id: str | None) -> str | None:
    """Desenha a barra lateral (novo chat + lista) e devolve o id da conversa ativa.

    `conversations` e `conversation_order` são mutados in-place (dict/list do
    st.session_state); `active_id` é devolvido porque strings são imutáveis.
    """

    # Sem guarda de "injetar uma vez só": o Streamlit reconstrói a árvore de
    # elementos a cada rerun, então um <style> emitido só na primeira
    # execução some do DOM assim que qualquer interação disparar um rerun.
    st.markdown(_CSS, unsafe_allow_html=True)

    with st.sidebar:
        if st.button("+ Novo chat", use_container_width=True):
            current = conversations.get(active_id)
            if current is None or current.messages:
                conversation = new_conversation()
                conversations[conversation.id] = conversation
                conversation_order.insert(0, conversation.id)
                active_id = conversation.id

        st.divider()

        ordered_ids = sorted(conversation_order, key=lambda cid: not conversations[cid].pinned)
        for conversation_id in ordered_ids:
            conversation = conversations[conversation_id]
            with st.container(key=f"chat-row-{conversation_id}"):
                col_title, col_menu = st.columns([6, 1], vertical_alignment="center")

                with col_title:
                    label = ("📌 " if conversation.pinned else "") + (
                        conversation.title or "Nova conversa"
                    )
                    if st.button(
                        label,
                        key=f"select-{conversation_id}",
                        use_container_width=True,
                        type="primary" if conversation_id == active_id else "secondary",
                    ):
                        active_id = conversation_id

                with col_menu:
                    with st.popover("⋮", use_container_width=True):
                        # A key inclui o título atual: um rename bem-sucedido
                        # troca a key e força o widget a reler `value=` com o
                        # título novo (por padrão, o Streamlit ignora `value=`
                        # em reruns seguintes ao 1º em que a key apareceu).
                        new_title = st.text_input(
                            "Renomear",
                            value=conversation.title or "",
                            key=f"rename-{conversation_id}-{conversation.title or ''}",
                            label_visibility="collapsed",
                            placeholder="Nome do chat",
                        )
                        if st.button(
                            "Salvar nome", key=f"save-{conversation_id}", use_container_width=True
                        ):
                            rename_conversation(conversation, new_title)
                            st.rerun()

                        if st.button(
                            "Desafixar" if conversation.pinned else "Fixar no topo",
                            key=f"pin-{conversation_id}",
                            use_container_width=True,
                        ):
                            toggle_pinned(conversation)
                            st.rerun()

                        if st.button(
                            "🗑 Excluir", key=f"delete-{conversation_id}", use_container_width=True
                        ):
                            del conversations[conversation_id]
                            conversation_order.remove(conversation_id)
                            if active_id == conversation_id:
                                active_id = conversation_order[0] if conversation_order else None
                            # st.rerun() interrompe a execução na hora: o
                            # "return active_id" no fim da função nunca roda,
                            # então quem chamou nunca veria essa troca se ela
                            # não for gravada direto no session_state aqui.
                            st.session_state.active_id = active_id
                            st.rerun()

    return active_id
