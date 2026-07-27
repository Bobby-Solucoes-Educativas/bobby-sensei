# TAI7-12/TAI7-15: consultas de leitura para o dashboard de feedback/histórico.
# Funções puras, sem streamlit — devolvem list[dict]/dict; quem desenha é
# ui/dashboard.py (via pages/1_Dashboard.py). Schema (TAI7-13): conversas/
# mensagens/feedback com bigint ids — ver db/migrations/001_feedback.sql.
# As colunas novas (positivo/comentario/papel/conteudo) são aliasadas de
# volta pros nomes que ui/dashboard.py já esperava (rating/comment/pergunta/
# resposta), pra não precisar tocar na camada de apresentação.
import calendar
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from psycopg.rows import dict_row

# Os containers rodam em UTC, mas o negócio é brasileiro — sem isso, o
# agrupamento "por dia" (e o reset mensal) usa a meia-noite UTC em vez da de
# Brasília: um feedback dado às 22h já cairia no dia seguinte no dashboard
# (bug real, confirmado — ver histórico). `AT TIME ZONE` no SQL converte
# `criada_em` pro horário local antes de truncar por dia.
_TZ = ZoneInfo("America/Sao_Paulo")
_TZ_NAME = "America/Sao_Paulo"

try:
    from core.db import get_connection
except ImportError:
    from db import get_connection

# Como o schema não tem FK "pergunta -> resposta", a pergunta de cada
# resposta é a última mensagem 'usuario' anterior na mesma conversa (ids
# crescem na ordem de inserção) — mesmo LATERAL usado em core/feedback.py.
_PERGUNTA_ANTERIOR = """
    LEFT JOIN LATERAL (
        SELECT conteudo
        FROM mensagens anterior
        WHERE anterior.conversa_id = resposta.conversa_id
          AND anterior.papel = 'usuario'
          AND anterior.id < resposta.id
        ORDER BY anterior.id DESC
        LIMIT 1
    ) pergunta ON true
"""


def question_volume(days: int = 30) -> list[dict]:
    """Volume de perguntas (mensagens do usuário) por dia, últimos `days` dias."""

    sql = """
        SELECT date_trunc('day', criada_em AT TIME ZONE %(tz)s)::date AS dia, count(*) AS total
        FROM mensagens
        WHERE papel = 'usuario' AND criada_em >= now() - (%(days)s || ' days')::interval
        GROUP BY 1
        ORDER BY 1
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, {"days": days, "tz": _TZ_NAME})
            return cur.fetchall()


def feedback_summary() -> dict:
    """Contagem e percentual de 👍/👎 sobre o total de respostas avaliadas."""

    sql = "SELECT positivo, count(*) AS total FROM feedback GROUP BY positivo"
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql)
            rows = cur.fetchall()

    up = next((r["total"] for r in rows if r["positivo"]), 0)
    down = next((r["total"] for r in rows if not r["positivo"]), 0)
    total = up + down
    return {
        "up": up,
        "down": down,
        "total": total,
        "pct_up": (up / total * 100) if total else 0.0,
        "pct_down": (down / total * 100) if total else 0.0,
    }


def negative_feedback() -> list[dict]:
    """Lista dos 👎, com a pergunta (mensagem anterior na conversa) + resposta + comentário."""

    sql = f"""
        SELECT
            f.comentario AS comment,
            f.criada_em AS feedback_created_at,
            resposta.conteudo AS resposta,
            pergunta.conteudo AS pergunta
        FROM feedback f
        JOIN mensagens resposta ON resposta.id = f.mensagem_id
        {_PERGUNTA_ANTERIOR}
        WHERE f.positivo = false
        ORDER BY f.criada_em DESC
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql)
            return cur.fetchall()


def unanswered_questions() -> list[dict]:
    """Perguntas cuja resposta tem `bot_respondeu = false` (TAI7-13/14) —
    pra time de atendimento revisar onde a documentação está falha."""

    sql = f"""
        SELECT
            resposta.conteudo AS resposta,
            resposta.criada_em AS created_at,
            pergunta.conteudo AS pergunta
        FROM mensagens resposta
        {_PERGUNTA_ANTERIOR}
        WHERE resposta.papel = 'assistente' AND resposta.bot_respondeu = false
        ORDER BY resposta.criada_em DESC
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql)
            return cur.fetchall()


def feedback_kpis() -> dict:
    """KPIs do topo do dashboard (TAI7-15): total de feedbacks, taxa de
    aprovação (%), quantos vieram com comentário e quantos são dos últimos 7
    dias — só sobre os campos que já existem (positivo 👍/👎 + comentário)."""

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT positivo, count(*) AS total FROM feedback GROUP BY positivo")
            por_rating = cur.fetchall()
            cur.execute(
                "SELECT count(*) AS total FROM feedback WHERE comentario IS NOT NULL AND btrim(comentario) <> ''"
            )
            com_comentario = cur.fetchone()["total"]
            cur.execute("SELECT count(*) AS total FROM feedback WHERE criada_em >= now() - interval '7 days'")
            ultimos_7_dias = cur.fetchone()["total"]

    up = next((r["total"] for r in por_rating if r["positivo"]), 0)
    down = next((r["total"] for r in por_rating if not r["positivo"]), 0)
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
    converte `criada_em` pro mesmo fuso antes de truncar por dia — assim um
    feedback dado às 23h de Brasília não vaza pro dia seguinte."""

    hoje = datetime.now(_TZ).date()
    primeiro_dia = hoje.replace(day=1)
    dias_no_mes = calendar.monthrange(hoje.year, hoje.month)[1]
    ultimo_dia = primeiro_dia.replace(day=dias_no_mes)

    inicio = datetime.combine(primeiro_dia, datetime.min.time(), tzinfo=_TZ)
    fim = datetime.combine(ultimo_dia + timedelta(days=1), datetime.min.time(), tzinfo=_TZ)

    sql = """
        SELECT date_trunc('day', criada_em AT TIME ZONE %(tz)s)::date AS dia, positivo, count(*) AS total
        FROM feedback
        WHERE criada_em >= %(inicio)s AND criada_em < %(fim)s
        GROUP BY 1, 2
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, {"inicio": inicio, "fim": fim, "tz": _TZ_NAME})
            rows = cur.fetchall()

    contagem = {(r["dia"], r["positivo"]): r["total"] for r in rows}
    return [
        {
            "dia": primeiro_dia + timedelta(days=i),
            "positivos": contagem.get((primeiro_dia + timedelta(days=i), True), 0),
            "negativos": contagem.get((primeiro_dia + timedelta(days=i), False), 0),
        }
        for i in range(dias_no_mes)
    ]


def recent_feedback(limit: int = 5) -> list[dict]:
    """Últimos feedbacks registrados (rating + comentário, se houver),
    mais recente primeiro — base da lista "Comentários recentes"."""

    sql = """
        SELECT
            CASE WHEN positivo THEN 'up' ELSE 'down' END AS rating,
            comentario AS comment,
            criada_em AS created_at
        FROM feedback
        ORDER BY criada_em DESC
        LIMIT %(limit)s
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, {"limit": limit})
            return cur.fetchall()
