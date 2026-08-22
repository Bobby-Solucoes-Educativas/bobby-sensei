# TAI7-12/TAI7-15: consultas de leitura para o dashboard de feedback/histórico.
# Funções puras, sem streamlit — devolvem list[dict]/dict; quem desenha é
# ui/dashboard.py (via pages/1_Dashboard.py).
import calendar
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from psycopg.rows import dict_row

# Os containers rodam em UTC, mas o negócio é brasileiro — sem isso, o
# agrupamento "por dia" (e o reset mensal) usa a meia-noite UTC em vez da de
# Brasília: um feedback dado às 22h já cairia no dia seguinte no dashboard
# (bug real, confirmado — ver histórico). `AT TIME ZONE` no SQL converte
# `created_at` pro horário local antes de truncar por dia.
_TZ = ZoneInfo("America/Sao_Paulo")
_TZ_NAME = "America/Sao_Paulo"

try:
    from core.db import get_connection
except ImportError:
    from db import get_connection

# Heurística de "não soube responder": nenhum LLM devolve um campo estruturado
# dizendo "não sei", então detectamos pelas frases que o próprio system
# prompt (core/retrieve.py) pede ao modelo, mais o aviso de indisponibilidade
# do backend (core/chatbot_core.py). É uma aproximação pro time de
# atendimento revisar à mão na lista de 👎 — não um classificador exato.
_MARCADORES_NAO_RESPONDIDO = (
    "%não encontr%",
    "%não há informa%",
    "%não tenho essa informa%",
    "%não consegui acessar a base de conhecimento%",
)


def question_volume(days: int = 30) -> list[dict]:
    """Volume de perguntas (mensagens do usuário) por dia, últimos `days` dias."""

    sql = """
        SELECT date_trunc('day', created_at AT TIME ZONE %(tz)s)::date AS dia, count(*) AS total
        FROM mensagens
        WHERE role = 'user' AND created_at >= now() - (%(days)s || ' days')::interval
        GROUP BY 1
        ORDER BY 1
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, {"days": days, "tz": _TZ_NAME})
            return cur.fetchall()


def feedback_summary() -> dict:
    """Contagem e percentual de 👍/👎 sobre o total de respostas avaliadas."""

    sql = "SELECT rating, count(*) AS total FROM feedback GROUP BY rating"
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql)
            rows = cur.fetchall()

    up = next((r["total"] for r in rows if r["rating"] == "up"), 0)
    down = next((r["total"] for r in rows if r["rating"] == "down"), 0)
    total = up + down
    return {
        "up": up,
        "down": down,
        "total": total,
        "pct_up": (up / total * 100) if total else 0.0,
        "pct_down": (down / total * 100) if total else 0.0,
    }


def negative_feedback() -> list[dict]:
    """Lista dos 👎, com a pergunta (via reply_to) + resposta + comentário."""

    sql = """
        SELECT
            f.comment,
            f.created_at AS feedback_created_at,
            resposta.content AS resposta,
            pergunta.content AS pergunta
        FROM feedback f
        JOIN mensagens resposta ON resposta.id = f.message_id
        LEFT JOIN mensagens pergunta ON pergunta.id = resposta.reply_to
        WHERE f.rating = 'down'
        ORDER BY f.created_at DESC
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql)
            return cur.fetchall()


def unanswered_questions() -> list[dict]:
    """Perguntas cuja resposta bate com a heurística de 'não soube responder'
    (ver `_MARCADORES_NAO_RESPONDIDO`) — pra time de atendimento revisar onde
    a documentação está falha."""

    condicoes = " OR ".join(f"resposta.content ILIKE %(m{i})s" for i in range(len(_MARCADORES_NAO_RESPONDIDO)))
    sql = f"""
        SELECT
            resposta.content AS resposta,
            resposta.created_at,
            pergunta.content AS pergunta
        FROM mensagens resposta
        LEFT JOIN mensagens pergunta ON pergunta.id = resposta.reply_to
        WHERE resposta.role = 'assistant' AND ({condicoes})
        ORDER BY resposta.created_at DESC
    """
    params = {f"m{i}": marcador for i, marcador in enumerate(_MARCADORES_NAO_RESPONDIDO)}
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def feedback_kpis() -> dict:
    """KPIs do topo do dashboard (TAI7-15): total de feedbacks, taxa de
    aprovação (%), quantos vieram com comentário e quantos são dos últimos 7
    dias — só sobre os campos que já existem (rating 👍/👎 + comentário)."""

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT rating, count(*) AS total FROM feedback GROUP BY rating")
            por_rating = cur.fetchall()
            cur.execute(
                "SELECT count(*) AS total FROM feedback WHERE comment IS NOT NULL AND btrim(comment) <> ''"
            )
            com_comentario = cur.fetchone()["total"]
            cur.execute("SELECT count(*) AS total FROM feedback WHERE created_at >= now() - interval '7 days'")
            ultimos_7_dias = cur.fetchone()["total"]

    up = next((r["total"] for r in por_rating if r["rating"] == "up"), 0)
    down = next((r["total"] for r in por_rating if r["rating"] == "down"), 0)
    total = up + down
    return {
        "total": total,
        "up": up,
        "down": down,
        "pct_aprovacao": round(up / total * 100) if total else 0,
        "com_comentario": com_comentario,
        "ultimos_7_dias": ultimos_7_dias,
    }


def daily_feedback_counts() -> list[dict]:
    """Feedback 👍/👎 por dia do MÊS CORRENTE — dia 1 até o último dia do mês,
    com zero-fill (inclusive dias que ainda não chegaram). Reseta sozinho a
    cada mês novo, porque `hoje`/`primeiro_dia`/`ultimo_dia` são recalculados
    a cada chamada — não acumula os meses anteriores.

    Tudo calculado no fuso de Brasília (`_TZ`), não UTC: os limites do mês são
    instantes absolutos com tzinfo explícito (não datas "nuas"), e o SQL
    converte `created_at` pro mesmo fuso antes de truncar por dia — assim um
    feedback dado às 23h de Brasília não vaza pro dia seguinte."""

    hoje = datetime.now(_TZ).date()
    primeiro_dia = hoje.replace(day=1)
    dias_no_mes = calendar.monthrange(hoje.year, hoje.month)[1]
    ultimo_dia = primeiro_dia.replace(day=dias_no_mes)

    inicio = datetime.combine(primeiro_dia, datetime.min.time(), tzinfo=_TZ)
    fim = datetime.combine(ultimo_dia + timedelta(days=1), datetime.min.time(), tzinfo=_TZ)

    sql = """
        SELECT date_trunc('day', created_at AT TIME ZONE %(tz)s)::date AS dia, rating, count(*) AS total
        FROM feedback
        WHERE created_at >= %(inicio)s AND created_at < %(fim)s
        GROUP BY 1, 2
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, {"inicio": inicio, "fim": fim, "tz": _TZ_NAME})
            rows = cur.fetchall()

    contagem = {(r["dia"], r["rating"]): r["total"] for r in rows}
    return [
        {
            "dia": primeiro_dia + timedelta(days=i),
            "positivos": contagem.get((primeiro_dia + timedelta(days=i), "up"), 0),
            "negativos": contagem.get((primeiro_dia + timedelta(days=i), "down"), 0),
        }
        for i in range(dias_no_mes)
    ]


def recent_feedback(limit: int = 5) -> list[dict]:
    """Últimos feedbacks registrados (rating + comentário, se houver),
    mais recente primeiro — base da lista "Comentários recentes"."""

    sql = """
        SELECT rating, comment, created_at
        FROM feedback
        ORDER BY created_at DESC
        LIMIT %(limit)s
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, {"limit": limit})
            return cur.fetchall()
