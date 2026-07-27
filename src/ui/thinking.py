# TAI7-?: indicador de "pensando" — logo com animação de respiração
# (escala + opacidade) enquanto a chain do RAG processa. Só apresentação
# (CSS/HTML via st.markdown); quem chama a chain continua sendo app.py.
import base64
from contextlib import contextmanager
from pathlib import Path

import streamlit as st

_ICONS_DIR = Path(__file__).resolve().parent.parent / "icon"
_LOGO_FILENAME = "logo-thinking.png"  # versão reduzida (155x128px) de Logo.png — ver docs

_THINKING_STYLE = """
<style>
@keyframes sensei-breath {
  0%, 100% { transform: scale(0.85); opacity: 0.45; }
  50%      { transform: scale(1.10); opacity: 1; }
}
.sensei-thinking-wrap {
  display: flex; align-items: center; gap: 10px;
}
.sensei-thinking-slot {
  width: 32px; height: 32px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.sensei-thinking-icon {
  max-width: 100%; max-height: 100%;
  object-fit: contain;
  display: block;
  transform-origin: center center;
  animation: sensei-breath 1.6s ease-in-out infinite;
  will-change: transform, opacity;
}
.sensei-thinking-text {
  font-size: 0.9rem; opacity: 0.7;
}
@media (prefers-reduced-motion: reduce) {
  .sensei-thinking-icon {
    animation: none; transform: none; opacity: 1;
  }
}
</style>
"""


@st.cache_data
def png_data_uri(path: str) -> str:
    """Lê o PNG (já com canal alpha) e cristaliza em base64 — sem cache,
    isso seria recalculado a cada rerun do Streamlit."""

    data = Path(path).read_bytes()
    b64 = base64.b64encode(data).decode()
    return f"data:image/png;base64,{b64}"


def inject_thinking_styles() -> None:
    """Injeta o <style> da animação.

    Sem guarda de "injetar uma vez só" via session_state: o Streamlit
    reconstrói a árvore de elementos do zero a cada rerun, então um <style>
    emitido só na primeira execução some do DOM assim que qualquer interação
    disparar um rerun (testado e confirmado — a guarda fazia o CSS sumir e a
    logo aparecia sem a animação/tamanho do slot). Mesmo motivo documentado
    em ui/sidebar.py; o `st.markdown` aqui é barato o bastante pra rodar a
    cada rerun sem problema."""

    st.markdown(_THINKING_STYLE, unsafe_allow_html=True)


@contextmanager
def thinking_indicator(placeholder, texto: str = "Sensei está pensando..."):
    """Context manager: desenha a logo "respirando" + texto no `placeholder`
    enquanto o bloco `with` roda; limpa o placeholder ao sair (inclusive em
    caso de exceção, pra não deixar o indicador travado na tela)."""

    data_uri = png_data_uri(str(_ICONS_DIR / _LOGO_FILENAME))
    placeholder.markdown(
        '<div class="sensei-thinking-wrap">'
        '<div class="sensei-thinking-slot">'
        f'<img class="sensei-thinking-icon" src="{data_uri}" alt="" />'
        "</div>"
        f'<span class="sensei-thinking-text">{texto}</span>'
        "</div>",
        unsafe_allow_html=True,
    )
    try:
        yield
    finally:
        placeholder.empty()
