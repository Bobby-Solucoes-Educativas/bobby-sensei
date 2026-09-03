# TAI7-14/TAI7-15: consultas de leitura para o dashboard de feedback/histórico.
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
# `criada_em` pro horário local antes de truncar por dia.
_TZ = ZoneInfo("America/Sao_Paulo")
_TZ_NAME = "America/Sao_Paulo"

try:
    from core.db import get_connection
except ImportError:
    from db import get_connection


def metricas_resumo() -> dict:
    """{'total_perguntas': int, 'positivos': int, 'negativos': int}."""

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT count(*) AS total FROM mensagens WHERE papel = 'usuario'")
            total_perguntas = cur.fetchone()["total"]
            cur.execute("SELECT positivo, count(*) AS total FROM feedback GROUP BY positivo")
            por_positivo = cur.fetchall()

    positivos = next((r["total"] for r in por_positivo if r["positivo"]), 0)
    negativos = next((r["total"] for r in por_positivo if not r["positivo"]), 0)
    return {"total_perguntas": total_perguntas, "positivos": positivos, "negativos": negativos}


def listar_negativos() -> list[dict]:
    """👎 com o histórico inteiro da conversa até a resposta avaliada
    (não só a pergunta imediata) + comentário, mais recentes primeiro.

    `historico` é a lista de mensagens da mesma `conversa_id` com
    `criada_em <= criada_em da resposta avaliada`, em ordem cronológica —
    a última entrada é sempre a resposta que recebeu o 👎. Não duplica dado
    (é uma consulta sobre `mensagens`, não uma cópia gravada no feedback)."""

    sql = """
        SELECT
            f.comentario,
            f.criada_em,
            hist.historico
        FROM feedback f
        JOIN mensagens resposta ON resposta.id = f.mensagem_id
        JOIN LATERAL (
            SELECT json_agg(
                json_build_object('papel', m.papel, 'conteudo', m.conteudo, 'fontes', m.fontes)
                ORDER BY m.criada_em
            ) AS historico
            FROM mensagens m
            WHERE m.conversa_id = resposta.conversa_id
              AND m.criada_em <= resposta.criada_em
        ) hist ON true
        WHERE f.positivo = false
        ORDER BY f.criada_em DESC
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql)
            return cur.fetchall()


def listar_nao_respondidas() -> list[dict]:
    """Mensagens de assistente com bot_respondeu = false: histórico inteiro
    da conversa até aquela resposta (não só a pergunta imediata) — mesmo
    padrão de `listar_negativos`, ver docstring lá pra detalhe da LATERAL."""

    sql = """
        SELECT
            resposta.criada_em,
            hist.historico
        FROM mensagens resposta
        JOIN LATERAL (
            SELECT json_agg(
                json_build_object('papel', m.papel, 'conteudo', m.conteudo, 'fontes', m.fontes)
                ORDER BY m.criada_em
            ) AS historico
            FROM mensagens m
            WHERE m.conversa_id = resposta.conversa_id
              AND m.criada_em <= resposta.criada_em
        ) hist ON true
        WHERE resposta.papel = 'assistente' AND resposta.bot_respondeu = false
        ORDER BY resposta.criada_em DESC
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql)
            return cur.fetchall()


def volume_por_dia(dias: int = 30) -> list[dict]:
    """Contagem de perguntas (mensagens do usuário) por dia, últimos `dias` dias."""

    sql = """
        SELECT date_trunc('day', criada_em AT TIME ZONE %(tz)s)::date AS dia, count(*) AS total
        FROM mensagens
        WHERE papel = 'usuario' AND criada_em >= now() - (%(dias)s || ' days')::interval
        GROUP BY 1
        ORDER BY 1
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, {"dias": dias, "tz": _TZ_NAME})
            return cur.fetchall()


def feedback_kpis() -> dict:
    """KPIs do topo do dashboard (TAI7-15): total de feedbacks, taxa de
    aprovação (%), quantos vieram com comentário e quantos são dos últimos 7
    dias — só sobre os campos que já existem (positivo 👍/👎 + comentário)."""

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT positivo, count(*) AS total FROM feedback GROUP BY positivo")
            por_positivo = cur.fetchall()
            cur.execute(
                "SELECT count(*) AS total FROM feedback WHERE comentario IS NOT NULL AND btrim(comentario) <> ''"
            )
            com_comentario = cur.fetchone()["total"]
            cur.execute("SELECT count(*) AS total FROM feedback WHERE criada_em >= now() - interval '7 days'")
            ultimos_7_dias = cur.fetchone()["total"]

    up = next((r["total"] for r in por_positivo if r["positivo"]), 0)
    down = next((r["total"] for r in por_positivo if not r["positivo"]), 0)
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
    """Últimos feedbacks registrados (positivo + comentário, se houver),
    mais recente primeiro — base da lista "Comentários recentes"."""

    sql = """
        SELECT positivo, comentario, criada_em
        FROM feedback
        ORDER BY criada_em DESC
        LIMIT %(limit)s
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, {"limit": limit})
            return cur.fetchall()
