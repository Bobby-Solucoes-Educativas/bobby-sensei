# TAI7-15: dashboard de feedback — instrumento de medição da fase de
# validação do MVP. Só busca os dados (core/dashboard_data.py) e chama quem
# desenha (ui/dashboard.py); mesmo padrão de app.py com core/ui.
import streamlit as st

from core.dashboard_data import (
    daily_feedback_counts,
    feedback_kpis,
    listar_nao_classificados,
    listar_nao_respondidas,
    listar_negativos,
    recent_feedback,
)
from ui.auth import render_logout_button, require_login
from ui.dashboard import (
    render_classification_queue,
    render_daily_chart,
    render_distribution_section,
    render_kpi_cards,
    render_negative_feedback,
    render_negative_feedback_filters,
    render_unanswered_questions,
)
from ui.sidebar import ensure_conversations_state, render_sidebar
from ui.theme import BACKGROUND

st.set_page_config(page_title="Dashboard · Bobby Sensei", page_icon="./src/icon/Logo.png", layout="wide")

st.markdown(
    f"""<style>
        [data-testid="stAppViewContainer"] {{ background-color: {BACKGROUND}; }}
    </style>""",
    unsafe_allow_html=True,
)

# Mesmo login do app.py: st.session_state é compartilhado entre as páginas
# do multipage app, então quem já logou no chat entra direto aqui — a
# mesma identidade autentica a classificação de feedback abaixo.
atendente_email = require_login()

# Mesma sidebar do app.py (lista de conversas) — sem isso, o Streamlit
# desenha o menu de navegação padrão (claro), e a sidebar "pisca" diferente
# ao trocar de página. ensure_conversations_state() é o mesmo bootstrap que
# app.py usa, pra funcionar mesmo se o usuário abrir o Dashboard direto.
ensure_conversations_state()
id_antes_do_clique = st.session_state.active_id
st.session_state.active_id = render_sidebar(
    st.session_state.conversations,
    st.session_state.conversation_order,
    st.session_state.active_id,
)
render_logout_button()
# "+ Novo chat"/selecionar uma conversa aqui só troca o active_id — sem
# navegar de volta, o clique parecia não fazer nada (o Dashboard não mostra
# mensagem nenhuma). Manda pra tela do chat pra já ver o efeito do clique.
if st.session_state.active_id != id_antes_do_clique:
    st.switch_page("app.py")

st.title("📊 Dashboard de feedback")
st.caption("Volume de perguntas, avaliação das respostas e onde a documentação está falha.")

kpis = feedback_kpis()
render_kpi_cards(kpis)

st.divider()

render_daily_chart(daily_feedback_counts())

st.divider()

render_distribution_section(kpis, recent_feedback(limit=5))

st.divider()

st.subheader("🗂️ Não classificados")
render_classification_queue(listar_nao_classificados(), atendente_email)

st.divider()

st.subheader("👎 Respostas com feedback negativo")
categoria_filtro, time_filtro = render_negative_feedback_filters()
render_negative_feedback(listar_negativos(categoria_filtro, time_filtro))

st.divider()

st.subheader("🤷 Perguntas que o bot não soube responder")
render_unanswered_questions(listar_nao_respondidas())
