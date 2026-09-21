# TAI7-13/14: barra de ações (👍/👎 + comentário, copiar) abaixo de cada
# resposta do assistente. Desenha e liga aos cliques; a persistência em si é
# `core.store.registrar_feedback` (mesmo padrão de ui/sidebar.py com
# core/chat_state.py). Copiar é 100% client-side (sem round-trip ao Streamlit).
import base64
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from core.chat_state import Message
from core.store import registrar_feedback
from ui.auth import logged_in_email
from ui.theme import BLACK, GREEN, WHITE, rgba

_ICONS_DIR = Path(__file__).resolve().parent.parent / "icon"
_ICON_SIZE = 14
_BUTTON_SIZE = 26


@st.cache_data
def _icon_data_uri(filename: str, color: str) -> str:
    """Lê o SVG (fill="currentColor") e cristaliza a cor pedida em base64: dentro
    de uma data URI isolada currentColor não herda a cor do botão, então precisa
    virar um hex fixo aqui antes de virar `background-image`."""
    svg = (_ICONS_DIR / filename).read_text().replace("currentColor", color)
    b64 = base64.b64encode(svg.encode()).decode()
    return f"data:image/svg+xml;base64,{b64}"


def _icon_button_css(key: str, filename: str, *, selected: bool = False) -> str:
    data_uri = _icon_data_uri(filename, WHITE if selected else BLACK)
    return f"""
    div[class*="st-key-{key}"] button {{
        background-image: url("{data_uri}");
        background-repeat: no-repeat;
        background-position: center;
        background-size: {_ICON_SIZE}px {_ICON_SIZE}px;
        color: transparent !important;
    }}
    """


def _render_copy_button(content: str) -> None:
    """Botão de copiar, 100% client-side. `st.markdown` passa HTML por um
    pipeline React (rehype) que converte `onclick="..."` num prop React
    `onClick` esperando função (não string) e quebra — por isso isto usa
    `components.html`, que roda num iframe de verdade com DOM/JS nativos
    (mesmo truque de `scroll_to_bottom` em ui/chat_bubbles.py)."""

    icon_uri = _icon_data_uri("copy.svg", BLACK)
    b64 = base64.b64encode(content.encode("utf-8")).decode()
    hover = rgba(GREEN, 0.14)
    copied_bg = rgba(GREEN, 0.3)
    html = f"""<button id="copy-btn" type="button" title="Copiar resposta" style="width:{_BUTTON_SIZE}px;height:{_BUTTON_SIZE}px;border:none;border-radius:999px;background-color:transparent;background-image:url('{icon_uri}');background-repeat:no-repeat;background-position:center;background-size:{_ICON_SIZE}px {_ICON_SIZE}px;cursor:pointer;padding:0;margin:0;"></button>
<style>html,body{{margin:0;padding:0;overflow:hidden;background:transparent;}}#copy-btn:hover{{background-color:{hover};}}#copy-btn.copied{{background-color:{copied_bg} !important;}}</style>
<script>
const btn = document.getElementById('copy-btn');
btn.addEventListener('click', () => {{
    const bytes = Uint8Array.from(atob('{b64}'), c => c.charCodeAt(0));
    const text = new TextDecoder('utf-8').decode(bytes);
    // O "copiado" (classe .copied) só acende se a promise resolver de
    // verdade — antes marcava sucesso incondicionalmente, então uma falha
    // silenciosa (ex.: clipboard bloqueado fora de HTTPS/localhost, caso
    // real do deploy de produção) mostrava confirmação falsa.
    navigator.clipboard.writeText(text).then(() => {{
        btn.classList.add('copied');
        setTimeout(() => btn.classList.remove('copied'), 1200);
    }}).catch((err) => {{
        console.error('Não foi possível copiar (precisa de HTTPS ou localhost):', err);
    }});
}});
</script>"""
    components.html(html, height=_BUTTON_SIZE, width=_BUTTON_SIZE)


def _toolbar_css(toolbar_key: str) -> str:
    """CSS que transforma o container em uma aba horizontal pequena, com
    bordas arredondadas, hospedando os 4 botões de ação lado a lado (em vez
    do layout padrão do Streamlit, que empilha verticalmente e estica as
    colunas pra largura cheia)."""

    border = rgba(BLACK, 0.15)
    hover = rgba(GREEN, 0.14)
    return f"""
    div[class*="st-key-{toolbar_key}"] {{
        display: inline-flex;
        width: fit-content;
        padding: 3px 5px;
        border-radius: 999px;
        border: 1px solid {border};
        margin: 6px 0 14px 0;
    }}
    div[class*="st-key-{toolbar_key}"] [data-testid="stHorizontalBlock"] {{
        display: flex;
        width: fit-content;
        gap: 2px;
        align-items: center;
    }}
    div[class*="st-key-{toolbar_key}"] [data-testid="column"] {{
        width: auto !important;
        min-width: 0 !important;
        flex: none !important;
        padding: 0 !important;
    }}
    div[class*="st-key-{toolbar_key}"] [data-testid="element-container"] {{
        margin: 0 !important;
    }}
    div[class*="st-key-{toolbar_key}"] button {{
        width: {_BUTTON_SIZE}px;
        height: {_BUTTON_SIZE}px;
        min-height: {_BUTTON_SIZE}px;
        padding: 0;
        border: none;
        border-radius: 999px;
    }}
    div[class*="st-key-{toolbar_key}"] button:hover {{
        background-color: {hover};
    }}
    div[class*="st-key-{toolbar_key}"] iframe {{
        display: block;
    }}
    """


def render_feedback_widget(message: Message) -> None:
    """Barra de ações (👍/👎 + comentário opcional, copiar) abaixo de uma
    resposta do assistente.

    Quem manda o 👍/👎 já está logado (app.py chama require_login() antes de
    desenhar o chat), então `criado_por` vem direto da sessão — sem pedir
    e-mail de novo aqui."""

    criado_por = logged_in_email()

    if "feedback_state" not in st.session_state:
        st.session_state.feedback_state = {}
    state = st.session_state.feedback_state.setdefault(message.id, {"rating": None, "sent": False})

    toolbar_key = f"fb-toolbar-{message.id}"
    up_key, down_key = f"fb-up-{message.id}", f"fb-down-{message.id}"

    st.markdown(
        "<style>"
        + _toolbar_css(toolbar_key)
        + _icon_button_css(up_key, "hand-thumbs-up.svg", selected=state["rating"] == "up")
        + _icon_button_css(down_key, "hand-thumbs-down.svg", selected=state["rating"] == "down")
        + "</style>",
        unsafe_allow_html=True,
    )

    with st.container(key=toolbar_key):
        col_up, col_down, col_copy = st.columns(3)
        with col_up:
            if st.button(" ", key=up_key, type="primary" if state["rating"] == "up" else "secondary"):
                registrar_feedback(message.db_id, True, criado_por=criado_por)
                st.session_state.feedback_state[message.id] = {"rating": "up", "sent": True}
                st.rerun()
        with col_down:
            if st.button(" ", key=down_key, type="primary" if state["rating"] == "down" else "secondary"):
                # Salva o 👎 na hora (igual ao 👍) — antes só marcava o estado
                # e dependia do clique em "Enviar feedback" pra persistir; se
                # o usuário saísse sem mandar comentário, o voto negativo
                # nunca ia pro banco (bug real, confirmado com teste).
                registrar_feedback(message.db_id, False, criado_por=criado_por)
                st.session_state.feedback_state[message.id] = {"rating": "down", "sent": True}
                st.rerun()
        with col_copy:
            _render_copy_button(message.content)

    if state["rating"] == "down":
        comment = st.text_area(
            "O que faltou nessa resposta? (opcional)",
            key=f"fb-comment-{message.id}",
        )
        if st.button("Enviar feedback", key=f"fb-send-{message.id}"):
            registrar_feedback(message.db_id, False, comment.strip() or None, criado_por=criado_por)
            st.session_state.feedback_state[message.id]["sent"] = True
            st.rerun()

    if state["sent"]:
        st.caption("✅ Feedback registrado. Obrigado!")
