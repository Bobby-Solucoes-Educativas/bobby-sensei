# TAI7-9: apresentação das mensagens do chat (bolha do usuário / resposta corrida do
# assistente). Só desenha na tela — não faz retrieval, chamada a LLM nem acesso a banco.
import html

import streamlit as st
import streamlit.components.v1 as components

from ui.theme import GREEN, LIME, rgba

_USER_BUBBLE_BG = rgba(LIME, 0.22)
_USER_BUBBLE_BORDER = rgba(GREEN, 0.35)


def render_user_message(text: str) -> None:
    """Desenha a mensagem do usuário alinhada à direita, numa bolha arredondada."""

    escaped = html.escape(text).replace("\n", "<br>")
    st.markdown(
        f"""<div style="display:flex; justify-content:flex-end; margin:10px 0;">
            <div style="
                max-width:70%;
                width:fit-content;
                padding:11px 17px;
                border-radius:19px;
                background-color:{_USER_BUBBLE_BG};
                border:1px solid {_USER_BUBBLE_BORDER};
                white-space:pre-wrap;
                word-wrap:break-word;
            ">{escaped}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def render_assistant_message(text: str, chunks: list[dict] | None = None) -> None:
    """Desenha a resposta do assistente à esquerda, como texto corrido (sem bolha),
    seguida (se houver) dos chunks recuperados que embasaram a resposta, como anexo.

    Usa st.markdown puro para preservar negrito/listas/quebras de linha vindas do RAG.
    """

    st.markdown(text)
    if chunks:
        with st.expander(f"📎 {len(chunks)} trecho(s) da documentação consultados"):
            for i, chunk in enumerate(chunks, start=1):
                fonte = chunk.get("breadcrumb") or chunk.get("title") or "documento"
                url = chunk.get("url")
                cabecalho = f"**[{i}] {fonte}**"
                st.markdown(f"{cabecalho}  \n{url}" if url else cabecalho)
                st.caption(chunk.get("text", ""))
                if i < len(chunks):
                    st.divider()
    st.markdown('<div style="margin-bottom:14px;"></div>', unsafe_allow_html=True)


def render_loading_message() -> None:
    """Indicador de 'digitando', desenhado do lado do assistente (esquerda)
    enquanto o retrieval + LLM rodam. Some sozinho no próximo rerun, quando
    vira a resposta de verdade."""

    st.markdown(
        f"""<div style="display:flex; align-items:center; gap:10px; margin:6px 0 14px 0;">
            <div style="
                width:16px; height:16px;
                border:2.5px solid {rgba(GREEN, 0.25)};
                border-top-color:{GREEN};
                border-radius:50%;
                animation:bobby-sensei-spin 0.8s linear infinite;
            "></div>
            <span style="opacity:0.7;">Bobby Sensei está buscando na documentação...</span>
        </div>
        <style>
            @keyframes bobby-sensei-spin {{ to {{ transform:rotate(360deg); }} }}
        </style>""",
        unsafe_allow_html=True,
    )


def scroll_to_bottom() -> None:
    """Rola a tela pro fim da conversa. Chamado a cada rerun, depois de
    desenhar as mensagens, pra acompanhar tanto a mensagem nova do usuário
    quanto o indicador de carregamento e a resposta final."""

    st.markdown('<div id="chat-bottom-anchor"></div>', unsafe_allow_html=True)
    components.html(
        """<script>
            var el = window.parent.document.getElementById("chat-bottom-anchor");
            if (el) { el.scrollIntoView({behavior: "smooth", block: "end"}); }
        </script>""",
        height=0,
    )
