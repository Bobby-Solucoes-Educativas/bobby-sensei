# TAI7-13/14: histórico de conversas e feedback (👍/👎 + comentário) de cada
# resposta. Funções puras, sem streamlit — mesmo padrão da TAI7-8/TAI7-9, pra
# dar pra expor por outro canal (ex.: FastAPI/WhatsApp) sem reescrever a
# lógica. app.py e ui/feedback.py são quem chama isso.
import json

from psycopg.rows import dict_row

try:
    from core.chat_state import Message
    from core.db import get_connection
except ImportError:
    from chat_state import Message
    from db import get_connection

# Vocabulário do banco x vocabulário do modelo em memória. O CHECK de
# `mensagens.papel` só aceita 'usuario'/'assistente' (migration 0003), enquanto
# chat_state.Message.role usa 'user'/'assistant'. Os dois sentidos ficam aqui,
# no limite com o banco, para a tradução não se espalhar pelo código.
_PAPEL_POR_ROLE = {"user": "usuario", "assistant": "assistente"}
_ROLE_POR_PAPEL = {v: k for k, v in _PAPEL_POR_ROLE.items()}


def papel_de_role(role: str) -> str:
    """Traduz o `role` do chat_state.Message para o `papel` do banco."""

    return _PAPEL_POR_ROLE[role]


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


def registrar_feedback(
    mensagem_id: int, positivo: bool, comentario: str | None = None, criado_por: str | None = None
) -> None:
    """Upsert em `feedback`: um feedback por mensagem — trocar o voto
    atualiza a linha (via UNIQUE(mensagem_id)), não cria outra.

    `criado_por` é o e-mail de quem está logado (ui.auth.logged_in_email)
    no momento do clique — identifica quem deu o 👍/👎, separado de
    `classificado_por` (quem depois classifica a causa do 👎 no dashboard;
    pode ser outro atendente)."""

    sql = """
        INSERT INTO feedback (mensagem_id, positivo, comentario, criado_por)
        VALUES (%(mensagem_id)s, %(positivo)s, %(comentario)s, %(criado_por)s)
        ON CONFLICT (mensagem_id) DO UPDATE
            SET positivo = EXCLUDED.positivo,
                comentario = EXCLUDED.comentario,
                criado_por = EXCLUDED.criado_por,
                atualizada_em = now()
    """
    with get_connection() as conn:
        conn.execute(
            sql,
            {
                "mensagem_id": mensagem_id,
                "positivo": positivo,
                "comentario": comentario,
                "criado_por": criado_por,
            },
        )


_TIME_POR_CATEGORIA = {"documentacao": "time_dev", "pipeline": "time_7"}


def time_sugerido(categoria: str) -> str:
    """Time sugerido automaticamente pela categoria do 👎 (regra decidida com
    o Arthur em 2026-07-29): documentação não responde a dúvida -> Time de
    Desenvolvimento; documentação atende mas a resposta do bot foi ruim ->
    Time 7. Quem chama pode sobrescrever o resultado antes de classificar."""

    return _TIME_POR_CATEGORIA[categoria]


def classificar_feedback(feedback_id: int, categoria: str, time_atribuido: str, classificado_por: str) -> None:
    """Registra a causa de um 👎 (documentacao/pipeline) e o time responsável.
    `classificado_por` é a identidade de quem classificou — hoje um e-mail
    digitado na sessão do dashboard (ui/dashboard.py), sem login de verdade;
    a função em si é agnóstica de canal, então uma futura triagem por outro
    canal (ex.: WhatsApp) só precisa chamar isso com o texto de identidade
    que tiver disponível, sem mudar nada aqui."""

    sql = """
        UPDATE feedback
        SET categoria = %(categoria)s,
            time_atribuido = %(time_atribuido)s,
            classificado_por = %(classificado_por)s,
            classificado_em = now()
        WHERE id = %(feedback_id)s
    """
    with get_connection() as conn:
        conn.execute(
            sql,
            {
                "feedback_id": feedback_id,
                "categoria": categoria,
                "time_atribuido": time_atribuido,
                "classificado_por": classificado_por,
            },
        )


def carregar_historico(conversa_id: int, antes_de: int | None = None) -> list[Message]:
    """Histórico da conversa em ordem cronológica, como chat_state.Message.

    É a fonte de verdade do contexto que vai para o LLM (TAI7-8): em vez de
    depender do estado em memória do Streamlit, lê as mensagens já persistidas
    por `salvar_mensagem` — então qualquer canal (FastAPI/WhatsApp) monta o
    mesmo histórico só com o `conversa_id`.

    `antes_de` recorta o histórico ANTES de uma mensagem (o id da pergunta
    pendente, que não deve entrar no próprio contexto). Ordena e filtra por
    `id` em vez de `criada_em` porque o id é BIGINT IDENTITY, monotônico e sem
    empate — duas mensagens podem compartilhar o timestamp.

    Quem chama corta o histórico para caber na janela de contexto
    (retrieve.build_history_context) — aqui a conversa volta inteira.
    """

    sql = """
        SELECT id, papel, conteudo, fontes, bot_respondeu
        FROM mensagens
        WHERE conversa_id = %(conversa_id)s
          AND (%(antes_de)s::bigint IS NULL OR id < %(antes_de)s::bigint)
        ORDER BY id
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, {"conversa_id": conversa_id, "antes_de": antes_de})
            linhas = cur.fetchall()

    return [
        Message(
            role=_ROLE_POR_PAPEL[linha["papel"]],
            content=linha["conteudo"],
            chunks=linha["fontes"] or [],
            db_id=linha["id"],
            bot_respondeu=linha["bot_respondeu"],
        )
        for linha in linhas
    ]
