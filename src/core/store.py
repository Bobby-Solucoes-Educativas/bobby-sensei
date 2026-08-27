# TAI7-13/14: histórico de conversas e feedback (👍/👎 + comentário) de cada
# resposta. Funções puras, sem streamlit — mesmo padrão da TAI7-8/TAI7-9, pra
# dar pra expor por outro canal (ex.: FastAPI/WhatsApp) sem reescrever a
# lógica. app.py e ui/feedback.py são quem chama isso.
import json

try:
    from core.db import get_connection
except ImportError:
    from db import get_connection


def criar_conversa(atendente: str | None = None, session_id: str | None = None) -> int:
    """Cria uma linha em `conversas` e retorna o id gerado pelo banco."""

    sql = """
        INSERT INTO conversas (atendente, session_id)
        VALUES (%(atendente)s, %(session_id)s)
        RETURNING id
    """
    with get_connection() as conn:
        row = conn.execute(sql, {"atendente": atendente, "session_id": session_id}).fetchone()
        return row[0]


def atualizar_titulo_conversa(conversa_id: int, titulo: str) -> None:
    """Define o título da conversa — só é conhecido depois da 1ª pergunta
    (ver chat_state._derive_title), por isso é um passo separado de
    `criar_conversa`. Fora do contrato da TAI7-14, mas necessário: sem isso a
    coluna `titulo` (usada na sidebar) nunca seria preenchida."""

    sql = "UPDATE conversas SET titulo = %(titulo)s WHERE id = %(id)s"
    with get_connection() as conn:
        conn.execute(sql, {"id": conversa_id, "titulo": titulo})


def salvar_mensagem(
    conversa_id: int,
    papel: str,
    conteudo: str,
    bot_respondeu: bool | None = None,
    fontes: list[dict] | None = None,
    reply_to: int | None = None,
) -> int:
    """Insere em `mensagens` e retorna o id gerado pelo banco.

    `reply_to` liga a resposta do assistente à pergunta que a originou —
    FK explícita, mais robusta que inferir pela mensagem anterior na mesma
    conversa (ver docs/tai7-13-14-conflitos.md, ponto 4). `bot_respondeu` e
    `fontes` só fazem sentido pra papel='assistente' — forçados a None/vazio
    nas mensagens de usuário pra nunca violar o CHECK do banco."""

    if papel != "assistente":
        bot_respondeu = None
        fontes = None

    sql = """
        INSERT INTO mensagens (conversa_id, papel, conteudo, bot_respondeu, fontes, reply_to)
        VALUES (%(conversa_id)s, %(papel)s, %(conteudo)s, %(bot_respondeu)s, %(fontes)s, %(reply_to)s)
        RETURNING id
    """
    with get_connection() as conn:
        row = conn.execute(
            sql,
            {
                "conversa_id": conversa_id,
                "papel": papel,
                "conteudo": conteudo,
                "bot_respondeu": bot_respondeu,
                "fontes": json.dumps(fontes or []),
                "reply_to": reply_to,
            },
        ).fetchone()
        return row[0]


def registrar_feedback(mensagem_id: int, positivo: bool, comentario: str | None = None) -> None:
    """Upsert em `feedback`: um feedback por mensagem — trocar o voto
    atualiza a linha (via UNIQUE(mensagem_id)), não cria outra."""

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
