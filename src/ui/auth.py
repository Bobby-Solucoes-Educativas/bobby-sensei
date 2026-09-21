# TAI7-24: porta de entrada única do app — chat (app.py) e dashboard
# (pages/1_Dashboard.py) chamam require_login() antes de desenhar qualquer
# coisa. st.session_state é compartilhado entre as páginas do multipage app,
# então logar numa já libera a outra sem pedir de novo.
import streamlit as st

from core.auth import EmailInvalido, EmailJaCadastrado, autenticar, criar_atendente

_SESSION_KEY = "atendente_logado"


def logged_in_email() -> str | None:
    return st.session_state.get(_SESSION_KEY)


def render_logout_button() -> None:
    email = logged_in_email()
    if not email:
        return
    with st.sidebar:
        st.caption(f"Logado como {email}")
        if st.button("Sair", use_container_width=True):
            del st.session_state[_SESSION_KEY]
            st.rerun()


def require_login() -> str:
    """Bloqueia a página até logar (st.stop() se não houver sessão ativa) e
    devolve o e-mail do atendente logado. Único ponto de entrada: chat e
    classificação de feedback usam essa mesma identidade, sem pedir de novo
    em cada ação (era um campo de texto solto na tela de classificação
    antes disso existir — ver docs/feedback-dashboard.md)."""

    email = logged_in_email()
    if email:
        return email

    st.title("🔒 Bobby Sensei")
    aba_entrar, aba_criar = st.tabs(["Entrar", "Criar conta"])

    with aba_entrar:
        with st.form("form-login"):
            email_input = st.text_input("E-mail corporativo")
            senha_input = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar"):
                autenticado = autenticar(email_input, senha_input)
                if autenticado:
                    st.session_state[_SESSION_KEY] = autenticado
                    st.rerun()
                else:
                    st.error("E-mail ou senha inválidos.")

    with aba_criar:
        with st.form("form-cadastro"):
            email_input = st.text_input("E-mail corporativo", key="cadastro-email")
            senha_input = st.text_input(
                "Senha (mínimo 8 caracteres)", type="password", key="cadastro-senha"
            )
            if st.form_submit_button("Criar conta"):
                try:
                    novo_email = criar_atendente(email_input, senha_input)
                    st.session_state[_SESSION_KEY] = novo_email
                    st.rerun()
                except (EmailInvalido, EmailJaCadastrado, ValueError) as erro:
                    st.error(str(erro))

    st.stop()
