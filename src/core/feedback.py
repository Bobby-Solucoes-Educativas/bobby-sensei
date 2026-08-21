# TAI7-14: funções puras de histórico/feedback sobre as tabelas da TAI7-13
# (conversas/mensagens/feedback, ver db/migrations/001_feedback.sql). Sem
# streamlit — só SQL parametrizado; app.py e ui/feedback.py só chamam isto.
import json

from psycopg.rows import dict_row

try:
    from core.db import get_connection
except ImportError:
    from db import get_connection


def criar_conversa(atendente: str | None = None, session_id: str | None = None) -> int:
    """Cria uma linha em `conversas` e retorna o id."""

    sql = """
        INSERT INTO conversas (atendente, session_id)
        VALUES (%(atendente)s, %(session_id)s)
        RETURNING id
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"atendente": atendente, "session_id": session_id})
            return cur.fetchone()[0]


def salvar_mensagem(
    conversa_id: int,
    papel: str,
    conteudo: str,
    bot_respondeu: bool | None = None,
    fontes: dict | None = None,
) -> int:
    """Insere em `mensagens` e retorna o id da mensagem."""

    if papel != "assistente":
        bot_respondeu = None
        fontes = None

    sql = """
        INSERT INTO mensagens (conversa_id, papel, conteudo, bot_respondeu, fontes)
        VALUES (%(conversa_id)s, %(papel)s, %(conteudo)s, %(bot_respondeu)s, %(fontes)s)
        RETURNING id
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                {
                    "conversa_id": conversa_id,
                    "papel": papel,
                    "conteudo": conteudo,
                    "bot_respondeu": bot_respondeu,
                    "fontes": json.dumps(fontes) if fontes is not None else None,
                },
            )
            return cur.fetchone()[0]


def registrar_feedback(mensagem_id: int, positivo: bool, comentario: str | None = None) -> None:
    """Upsert em `feedback`: um feedback por mensagem (trocar o voto atualiza,
    não duplica) — depende do UNIQUE (mensagem_id) da TAI7-13."""

    sql = """
        INSERT INTO feedback (mensagem_id, positivo, comentario)
        VALUES (%(mensagem_id)s, %(positivo)s, %(comentario)s)
        ON CONFLICT (mensagem_id) DO UPDATE
            SET positivo = EXCLUDED.positivo,
                comentario = EXCLUDED.comentario,
                atualizada_em = now()
    """
    with get_connection() as conn:
        conn.execute(sql, {"mensagem_id": mensagem_id, "positivo": positivo, "comentario": comentario})


def metricas_resumo() -> dict:
    """{'total_perguntas': int, 'positivos': int, 'negativos': int}."""

    sql = """
        SELECT
            (SELECT count(*) FROM mensagens WHERE papel = 'usuario') AS total_perguntas,
            (SELECT count(*) FROM feedback WHERE positivo) AS positivos,
            (SELECT count(*) FROM feedback WHERE NOT positivo) AS negativos
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql)
            return cur.fetchone()


# Como o schema da TAI7-13 não tem um FK "pergunta -> resposta", a pergunta de
# cada resposta é a última mensagem 'usuario' anterior na mesma conversa (ids
# crescem na ordem de inserção) — daí o LATERAL nas duas queries abaixo.
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


def listar_negativos() -> list[dict]:
    """👎 com pergunta, resposta e comentário, mais recentes primeiro."""

    sql = f"""
        SELECT
            pergunta.conteudo AS pergunta,
            resposta.conteudo AS resposta,
            f.comentario,
            f.criada_em
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


def listar_nao_respondidas() -> list[dict]:
    """Mensagens de assistente com bot_respondeu = false (pergunta + resposta)."""

    sql = f"""
        SELECT
            resposta.id,
            resposta.conteudo AS resposta,
            pergunta.conteudo AS pergunta,
            resposta.criada_em
        FROM mensagens resposta
        {_PERGUNTA_ANTERIOR}
        WHERE resposta.papel = 'assistente' AND resposta.bot_respondeu = false
        ORDER BY resposta.criada_em DESC
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql)
            return cur.fetchall()


def volume_por_dia() -> list[dict]:
    """Contagem de perguntas por dia, para o gráfico de volume."""

    sql = """
        SELECT date_trunc('day', criada_em AT TIME ZONE 'America/Sao_Paulo')::date AS dia,
               count(*) AS total
        FROM mensagens
        WHERE papel = 'usuario'
        GROUP BY 1
        ORDER BY 1
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql)
            return cur.fetchall()
