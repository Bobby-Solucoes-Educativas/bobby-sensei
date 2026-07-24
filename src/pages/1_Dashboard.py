# TAI7-15: dashboard de feedback — instrumento de medição da fase de
# validação do MVP. Só busca os dados (core/dashboard_data.py) e chama quem
# desenha (ui/dashboard.py); mesmo padrão de app.py com core/ui.
import streamlit as st

from core.dashboard_data import (
    daily_feedback_counts,
    feedback_kpis,
    negative_feedback,
    recent_feedback,
    unanswered_questions,
)
from ui.dashboard import (
    render_daily_chart,
    render_distribution_section,
    render_kpi_cards,
    render_negative_feedback,
    render_unanswered_questions,
)
from ui.theme import BACKGROUND

st.set_page_config(page_title="Dashboard · Bobby Sensei", page_icon="./src/icon/grafico-colorido.png", layout="wide")

st.markdown(
    f"""<style>
        [data-testid="stAppViewContainer"] {{ background-color: {BACKGROUND}; }}
    </style>""",
    unsafe_allow_html=True,
)

st.title("📊 Dashboard de feedback")
st.caption("Volume de perguntas, avaliação das respostas e onde a documentação está falha.")

kpis = feedback_kpis()
render_kpi_cards(kpis)

st.divider()

render_daily_chart(daily_feedback_counts())

st.divider()

render_distribution_section(kpis, recent_feedback(limit=5))

st.divider()

st.subheader("👎 Respostas com feedback negativo")
render_negative_feedback(negative_feedback())

st.divider()

st.subheader("🤷 Perguntas que o bot não soube responder")
render_unanswered_questions(unanswered_questions())
