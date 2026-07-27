# TAI7-12: persiste conversas/mensagens e o feedback (👍/👎 + comentário) de
# cada resposta. Funções puras, sem streamlit — mesmo padrão da
# TAI7-8/TAI7-9, pra dar pra expor por outro canal (ex.: FastAPI/WhatsApp)
# sem reescrever a lógica. app.py e ui/feedback.py são quem chama isso.
import json

try:
    from core.db import get_connection
except ImportError:
    from db import get_connection

RATINGS = ("up", "down")


def save_conversation(conversation_id: str, title: str | None) -> None:
    """Insere a conversa na primeira mensagem; atualiza o título nas seguintes
    (o título só é conhecido depois da 1ª pergunta, ver chat_state._derive_title)."""

    sql = """
        INSERT INTO conversas (id, title)
        VALUES (%(id)s, %(title)s)
        ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title
    """
    with get_connection() as conn:
        conn.execute(sql, {"id": conversation_id, "title": title})


def save_message(
    message_id: str,
    conversation_id: str,
    role: str,
    content: str,
    chunks: list[dict] | None = None,
    reply_to: str | None = None,
) -> None:
    """Insere a mensagem, ligada à conversa. A conversa precisa já existir
    (chamar save_conversation antes). `reply_to` liga a resposta do
    assistente à pergunta do usuário que a originou — usado pelo dashboard
    pra casar pergunta + resposta na lista de 👎."""

    sql = """
        INSERT INTO mensagens (id, conversation_id, role, content, chunks, reply_to)
        VALUES (%(id)s, %(conversation_id)s, %(role)s, %(content)s, %(chunks)s, %(reply_to)s)
        ON CONFLICT (id) DO NOTHING
    """
    with get_connection() as conn:
        conn.execute(
            sql,
            {
                "id": message_id,
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
                "chunks": json.dumps(chunks or []),
                "reply_to": reply_to,
            },
        )


def save_feedback(message_id: str, rating: str, comment: str | None = None) -> None:
    """Registra o feedback (👍/👎 + comentário opcional) de uma resposta.
    Um novo clique no mesmo message_id substitui o feedback anterior (o
    usuário pode trocar de ideia) em vez de duplicar linhas."""

    if rating not in RATINGS:
        raise ValueError(f"rating precisa ser 'up' ou 'down', recebeu {rating!r}")

    sql = """
        INSERT INTO feedback (message_id, rating, comment)
        VALUES (%(message_id)s, %(rating)s, %(comment)s)
        ON CONFLICT (message_id) DO UPDATE
            SET rating = EXCLUDED.rating,
                comment = EXCLUDED.comment,
                created_at = now()
    """
    with get_connection() as conn:
        conn.execute(sql, {"message_id": message_id, "rating": rating, "comment": comment})
