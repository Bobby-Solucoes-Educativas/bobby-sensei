# TAI7-15: desenha a página de dashboard (cards de KPI, gráfico de barras
# agrupadas, rosca de proporção e lista de comentários recentes). Só
# apresentação — os dados vêm prontos de core/dashboard_data.py (mesmo
# padrão de ui/sidebar.py com core/chat_state.py).
import json
from datetime import datetime, timezone

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from ui.theme import BLACK, GREEN, LIME, RED, WHITE, rgba

_CARD_BG = BLACK
_CARD_TEXT = WHITE


def _card_html(label: str, value: str, *, value_color: str = WHITE) -> str:
    return (
        f'<div style="background:{_CARD_BG};color:{_CARD_TEXT};border-radius:12px;'
        'padding:18px 22px;">'
        f'<div style="opacity:0.65;font-size:0.9rem;">{label}</div>'
        f'<div style="font-size:2rem;font-weight:700;margin-top:6px;color:{value_color};">{value}</div>'
        "</div>"
    )


def render_kpi_cards(kpis: dict) -> None:
    """4 cards: total de feedbacks, taxa de aprovação, com comentário, e
    quantos são dos últimos 7 dias."""

    col1, col2, col3, col4 = st.columns(4, gap="medium")
    with col1:
        st.markdown(_card_html("Total de feedbacks", str(kpis["total"])), unsafe_allow_html=True)
    with col2:
        st.markdown(
            _card_html("Taxa de aprovação", f"{kpis['pct_aprovacao']}%", value_color=LIME),
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(_card_html("Com comentário", str(kpis["com_comentario"])), unsafe_allow_html=True)
    with col4:
        st.markdown(_card_html("Últimos 7 dias", f"+{kpis['ultimos_7_dias']}"), unsafe_allow_html=True)


_DIA_SLOT_WIDTH = 70  # px por dia (2 barras + espaço) — largura fixa, não estica com poucos dias
_CHART_MIN_WIDTH = 640  # largura mínima da ÁREA do gráfico (sem contar o padding dos eixos)
_CHART_HEIGHT = 260  # altura da ÁREA do gráfico (sem contar o padding dos eixos)
# Com autosize="none", width/height acima são só a área de plotagem — os
# rótulos dos eixos precisam desse espaço extra reservado à parte, ou saem
# cortados (foi visto acontecer sem isso: eixos sumiam da tela).
_PAD_LEFT, _PAD_RIGHT, _PAD_TOP, _PAD_BOTTOM = 45, 15, 10, 35


def _dark_card_css(key: str) -> str:
    return f"""
    div[class*="st-key-{key}"] {{
        background: {BLACK};
        border-radius: 14px;
        padding: 24px 26px 16px 26px;
    }}
    """


_EIXO_Y_WIDTH = 1  # largura da área de plotagem do painel do eixo (só precisa do padding-left)


def render_daily_chart(daily: list[dict]) -> None:
    """Gráfico de barras agrupadas (positivo x negativo) por dia, construído
    do zero em Altair (não `st.bar_chart`) — só assim dá pra controlar fundo
    escuro, cor dos eixos e legenda, pra bater com o card das referências.

    Largura fixa por dia: a cada dia novo o gráfico cresce pro lado em vez
    de espremer os dias existentes. São 2 gráficos Vega-Lite lado a lado,
    montados à mão num único iframe (`components.html`, não `st.altair_chart`
    — um gráfico largo dentro de um `st.container` normal arrasta a página
    inteira junto com ele, testado e visto acontecer):
    - um painel FIXO só com o eixo Y (fora da área de rolagem);
    - o painel com as barras, rolável, com o eixo Y escondido (só a grade
      horizontal aparece, alinhada, pra não duplicar os números).
    Os dois usam a MESMA escala Y (mesmo domínio + "nice"), então a grade de
    um bate exatamente com os números do outro conforme rola pro lado."""

    df = pd.DataFrame(daily)
    df["dia"] = pd.to_datetime(df["dia"])
    df["rotulo"] = df["dia"].dt.strftime("%d/%m")
    longo = df.melt(id_vars=["rotulo"], value_vars=["positivos", "negativos"], var_name="tipo", value_name="total")
    longo["tipo"] = longo["tipo"].map({"positivos": "Positivo", "negativos": "Negativo"})

    largura = max(_CHART_MIN_WIDTH, len(df) * _DIA_SLOT_WIDTH)
    maximo = max(1, int(longo["total"].max()))
    escala_y = alt.Scale(domain=[0, maximo], nice=True)

    card_key = "daily-chart-card"
    st.markdown(f"<style>{_dark_card_css(card_key)}</style>", unsafe_allow_html=True)
    with st.container(key=card_key):
        st.markdown(
            f'<div style="color:{WHITE};font-size:1.15rem;font-weight:700;margin-bottom:14px;">'
            "Feedback por dia</div>",
            unsafe_allow_html=True,
        )
        legenda = "".join(
            '<span style="display:inline-flex;align-items:center;gap:6px;margin-right:18px;">'
            f'<span style="width:11px;height:11px;background:{cor};border-radius:2px;'
            'display:inline-block;"></span>'
            f'<span style="color:{WHITE};font-size:0.9rem;">{rotulo}</span></span>'
            for cor, rotulo in ((GREEN, "Positivo"), (RED, "Negativo"))
        )
        st.markdown(f'<div style="margin-bottom:10px;">{legenda}</div>', unsafe_allow_html=True)

        eixo_x = alt.Axis(labelColor=WHITE, domainColor="transparent", tickColor="transparent", labelAngle=0)
        # Painel fixo: números do eixo Y, sem grade (não teria largura pra mostrar).
        eixo_y_fixo = alt.Axis(
            title=None, labelColor=WHITE, domainColor="transparent", tickColor="transparent", grid=False
        )
        # Painel rolável: só a grade horizontal, sem números (evita duplicar
        # o que já aparece no painel fixo ao lado).
        eixo_y_scroll = alt.Axis(
            title=None, labels=False, ticks=False, domain=False, gridColor=rgba(WHITE, 0.15)
        )

        grafico_eixo = (
            alt.Chart(longo)
            .mark_point(opacity=0)
            .encode(y=alt.Y("total:Q", title=None, axis=eixo_y_fixo, scale=escala_y))
            .properties(
                width=_EIXO_Y_WIDTH,
                height=_CHART_HEIGHT,
                background="transparent",
                autosize="none",
                padding={"left": _PAD_LEFT, "right": 0, "top": _PAD_TOP, "bottom": _PAD_BOTTOM},
            )
            .configure_view(strokeWidth=0)
        )
        grafico_barras = (
            alt.Chart(longo)
            .mark_bar(size=13)
            .encode(
                x=alt.X("rotulo:N", sort=None, title=None, axis=eixo_x),
                xOffset=alt.XOffset("tipo:N", sort=["Positivo", "Negativo"]),
                y=alt.Y("total:Q", title=None, axis=eixo_y_scroll, scale=escala_y),
                color=alt.Color(
                    "tipo:N",
                    scale=alt.Scale(domain=["Positivo", "Negativo"], range=[GREEN, RED]),
                    legend=None,
                ),
            )
            # autosize="none": sem isso, o Vega-Lite recalcula a largura pra
            # caber no elemento que o hospeda ("fit", o padrão) e ignora o
            # `width=` abaixo — com "none" ele respeita o pixel exato pedido.
            .properties(
                width=largura,
                height=_CHART_HEIGHT,
                background="transparent",
                autosize="none",
                padding={"left": 4, "right": _PAD_RIGHT, "top": _PAD_TOP, "bottom": _PAD_BOTTOM},
            )
            .configure_view(strokeWidth=0)
        )

        largura_eixo_total = _PAD_LEFT + _EIXO_Y_WIDTH
        largura_barras_total = largura + 4 + _PAD_RIGHT
        altura_total = _CHART_HEIGHT + _PAD_TOP + _PAD_BOTTOM

        # Monta o HTML à mão (em vez de Chart.to_html(), pensado pra 1 gráfico
        # só): dois <div>, cada um com seu vegaEmbed — o do eixo fica fora da
        # div com overflow-x:auto, então não rola junto com as barras.
        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
html, body {{ margin:0; padding:0; background:{BLACK}; overflow:hidden; }}
#wrap {{ display:flex; align-items:flex-start; }}
#axis-vis {{ flex:0 0 auto; width:{largura_eixo_total}px; min-width:{largura_eixo_total}px; }}
#scroll-area {{ flex:1 1 auto; min-width:0; overflow-x:auto; overflow-y:hidden; }}
#bars-vis {{ width:{largura_barras_total}px; }}
</style>
<script src="https://cdn.jsdelivr.net/npm/vega@5"></script>
<script src="https://cdn.jsdelivr.net/npm/vega-lite@5"></script>
<script src="https://cdn.jsdelivr.net/npm/vega-embed@6"></script>
</head><body>
<div id="wrap">
    <div id="axis-vis"></div>
    <div id="scroll-area"><div id="bars-vis"></div></div>
</div>
<script>
    vegaEmbed("#axis-vis", {json.dumps(grafico_eixo.to_dict())}, {{actions: false}});
    vegaEmbed("#bars-vis", {json.dumps(grafico_barras.to_dict())}, {{actions: false}});
</script>
</body></html>"""
        components.html(html, height=altura_total + 15)


_DONUT_DIAMETER = 200
_DONUT_HOLE_PCT = 58  # tamanho do buraco central, em % do diâmetro


def render_donut(kpis: dict) -> None:
    """Rosca 👍 (verde) x 👎 (vermelho) — desenhada à mão com CSS puro
    (`conic-gradient`), sem nenhuma biblioteca de gráfico: um círculo com um
    degradê cônico de 2 cores, com um círculo menor da cor do fundo por
    cima, formando o buraco do meio. Legenda (quadrado colorido + %) abaixo,
    igual à referência."""

    total = kpis["total"]
    if total == 0:
        st.markdown(
            f'<span style="color:{WHITE};opacity:0.7;">Sem feedback suficiente '
            "pra calcular a distribuição.</span>",
            unsafe_allow_html=True,
        )
        return

    pct_pos = kpis["pct_aprovacao"]
    pct_neg = 100 - pct_pos

    st.markdown(
        f'<div style="width:{_DONUT_DIAMETER}px;height:{_DONUT_DIAMETER}px;border-radius:50%;'
        f"background:conic-gradient({GREEN} 0% {pct_pos}%, {RED} {pct_pos}% 100%);"
        'position:relative;margin:6px auto 18px;">'
        '<div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);'
        f"width:{_DONUT_HOLE_PCT}%;height:{_DONUT_HOLE_PCT}%;border-radius:50%;"
        f'background:{BLACK};"></div>'
        "</div>",
        unsafe_allow_html=True,
    )

    legenda = "".join(
        '<div style="display:flex;align-items:center;gap:8px;margin-top:6px;">'
        f'<div style="width:12px;height:12px;background:{cor};border-radius:2px;"></div>'
        f'<span style="color:{WHITE};">{rotulo} {pct}%</span></div>'
        for cor, rotulo, pct in ((GREEN, "Positivo", pct_pos), (RED, "Negativo", pct_neg))
    )
    st.markdown(legenda, unsafe_allow_html=True)


def render_distribution_section(kpis: dict, comments: list[dict]) -> None:
    """Bloco único (card escuro) com "Distribuição" (rosca) e "Comentários
    recentes" lado a lado, igual à referência — mesmo card, não dois
    separados."""

    card_key = "distribution-card"
    st.markdown(f"<style>{_dark_card_css(card_key)}</style>", unsafe_allow_html=True)
    with st.container(key=card_key):
        col_donut, col_comments = st.columns([1, 1.4], gap="large")
        with col_donut:
            st.markdown(
                f'<div style="color:{WHITE};font-size:1.15rem;font-weight:700;margin-bottom:6px;">'
                "Distribuição</div>",
                unsafe_allow_html=True,
            )
            render_donut(kpis)
        with col_comments:
            st.markdown(
                f'<div style="color:{WHITE};font-size:1.15rem;font-weight:700;margin-bottom:14px;">'
                "Comentários recentes</div>",
                unsafe_allow_html=True,
            )
            render_recent_comments(comments)


def _relative_time(created_at: datetime) -> str:
    """Formata "há X minutos/horas/dias" em português, a partir de um
    timestamp — puramente de apresentação (por isso mora em ui/, não em core/)."""

    agora = datetime.now(timezone.utc)
    delta = agora - created_at.astimezone(timezone.utc)
    segundos = delta.total_seconds()
    if segundos < 60:
        return "Agora mesmo"
    minutos = int(segundos // 60)
    if minutos < 60:
        return f"Há {minutos} minuto{'s' if minutos != 1 else ''}"
    horas = int(segundos // 3600)
    if horas < 24:
        return f"Há {horas} hora{'s' if horas != 1 else ''}"
    dias = int(segundos // 86400)
    return f"Há {dias} dia{'s' if dias != 1 else ''}"


def render_recent_comments(comments: list[dict]) -> None:
    """Lista dos feedbacks mais recentes: marcador verde/vermelho, o
    comentário (ou "Sem comentário", em itálico) e o tempo relativo. Texto em
    branco — este card é escuro, o texto padrão do Streamlit (pensado pro
    fundo claro da página) ficaria ilegível aqui."""

    if not comments:
        st.markdown(
            f'<span style="color:{WHITE};opacity:0.7;">Ainda não há feedback registrado.</span>',
            unsafe_allow_html=True,
        )
        return

    for item in comments:
        cor = GREEN if item["positivo"] else RED
        if item["comentario"]:
            texto = item["comentario"]
            estilo_texto = f"color:{WHITE};"
        else:
            texto = "Sem comentário"
            estilo_texto = f"color:{WHITE};font-style:italic;opacity:0.7;"
        st.markdown(
            f'<div style="display:flex;gap:10px;align-items:flex-start;margin-bottom:16px;">'
            f'<div style="width:14px;height:14px;margin-top:3px;flex-shrink:0;'
            f'border:2px solid {cor};border-radius:3px;"></div>'
            f'<div><div style="{estilo_texto}">{texto}</div>'
            f'<div style="color:{WHITE};opacity:0.55;font-size:0.85rem;margin-top:2px;">'
            f'{_relative_time(item["criada_em"])}</div>'
            "</div></div>",
            unsafe_allow_html=True,
        )


def render_negative_feedback(items: list[dict]) -> None:
    """Lista dos 👎, cada um em um expander mostrando o histórico inteiro da
    conversa até a resposta avaliada (não só a pergunta imediata) + o
    comentário do feedback."""

    if not items:
        st.caption("Nenhum 👎 registrado até agora.")
        return

    for item in items:
        historico = item["historico"]
        perguntas = [m["conteudo"] for m in historico if m["papel"] == "usuario"]
        titulo = perguntas[-1] if perguntas else "(pergunta não identificada)"

        with st.expander(f"🗨️ {titulo}"):
            for m in historico:
                rotulo = "🧑 Usuário" if m["papel"] == "usuario" else "🤖 Assistente"
                st.markdown(f"**{rotulo}:**\n\n{m['conteudo']}")
                st.divider()
            if item["comentario"]:
                st.markdown(f"**Comentário:** {item['comentario']}")
            else:
                st.caption("Sem comentário.")
            st.caption(f"Avaliado em {item['criada_em']:%d/%m/%Y %H:%M}")


def render_unanswered_questions(items: list[dict]) -> None:
    """Perguntas cuja resposta ficou com `bot_respondeu = false` — sinal
    gravado no momento da resposta (ver core.chatbot_core._bot_respondeu);
    linhas de antes da TAI7-13 foram preenchidas por heurística no backfill
    (migration 0004), não um classificador exato."""

    if not items:
        st.caption("Nenhuma pergunta sem resposta detectada até agora.")
        return

    for item in items:
        with st.expander(f"❓ {item['pergunta'] or '(pergunta não identificada)'}"):
            st.markdown(item["resposta"])
            st.caption(f"Em {item['criada_em']:%d/%m/%Y %H:%M}")
