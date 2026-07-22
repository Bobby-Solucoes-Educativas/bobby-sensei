# TAI7-9: modelo de conversas do chat. Dataclasses puras, sem streamlit —
# reaproveitável por outros canais (WhatsApp/FastAPI) no futuro.
from dataclasses import dataclass, field
from uuid import uuid4

_TITLE_MAX_LEN = 40


@dataclass
class Message:
    role: str
    content: str
    chunks: list[dict] = field(default_factory=list)


@dataclass
class Conversation:
    id: str
    title: str | None = None
    messages: list[Message] = field(default_factory=list)
    pinned: bool = False


def new_conversation() -> Conversation:
    """Cria uma conversa vazia, sem título (o título vem da primeira pergunta)."""

    return Conversation(id=uuid4().hex)


def add_message(
    conversation: Conversation, role: str, content: str, chunks: list[dict] | None = None
) -> None:
    """Adiciona uma mensagem à conversa e deriva o título a partir da 1ª pergunta."""

    conversation.messages.append(Message(role=role, content=content, chunks=chunks or []))
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
