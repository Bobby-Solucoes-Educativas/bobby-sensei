# TAI7-9/TAI7-14: modelo de conversas do chat. Dataclasses puras, sem
# streamlit — reaproveitável por outros canais (WhatsApp/FastAPI) no futuro.
from dataclasses import dataclass, field
from uuid import uuid4

_TITLE_MAX_LEN = 40


@dataclass
class Message:
    role: str
    content: str
    chunks: list[dict] = field(default_factory=list)
    # `id` é só client-side (chave de widget/session_state do Streamlit,
    # precisa existir antes de qualquer round-trip ao banco). `db_id` é o id
    # bigint que o banco gera no INSERT (store.salvar_mensagem) — None até lá,
    # e é o que vira `reply_to` da resposta seguinte.
    id: str = field(default_factory=lambda: uuid4().hex)
    db_id: int | None = None
    # Só relevante pra role="assistant" — se o RAG achou contexto (True) ou
    # caiu no fallback de "não sei" (False); ver core/chatbot_core.py.
    bot_respondeu: bool | None = None


@dataclass
class Conversation:
    id: str
    title: str | None = None
    messages: list[Message] = field(default_factory=list)
    pinned: bool = False
    db_id: int | None = None


def new_conversation() -> Conversation:
    """Cria uma conversa vazia, sem título (o título vem da primeira pergunta)."""

    return Conversation(id=uuid4().hex)


def add_message(
    conversation: Conversation,
    role: str,
    content: str,
    chunks: list[dict] | None = None,
    bot_respondeu: bool | None = None,
) -> None:
    """Adiciona uma mensagem à conversa e deriva o título a partir da 1ª pergunta."""

    conversation.messages.append(
        Message(role=role, content=content, chunks=chunks or [], bot_respondeu=bot_respondeu)
    )
    if conversation.title is None and role == "user":
        conversation.title = _derive_title(content)


def rename_conversation(conversation: Conversation, title: str) -> None:
    """Define um título manual para a conversa; ignora string vazia."""

    trimmed = title.strip()
    if trimmed:
        conversation.title = trimmed


def toggle_pinned(conversation: Conversation) -> None:
    """Fixa/desafixa a conversa no topo da lista."""

    conversation.pinned = not conversation.pinned


def _derive_title(text: str) -> str:
    """Resume a primeira pergunta num título curto para exibir na barra lateral."""

    collapsed = " ".join(text.split())
    if len(collapsed) <= _TITLE_MAX_LEN:
        return collapsed
    return collapsed[:_TITLE_MAX_LEN].rstrip() + "…"
