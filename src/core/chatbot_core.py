# TAI7-9/TAI7-14: orquestra o fluxo de resposta a uma pergunta, delegando o
# RAG híbrido (retrieval + LLM) para core/retrieve.py. Função pura, sem
# streamlit — reaproveitável por outros canais (WhatsApp/FastAPI) no futuro.
from core.chat_state import Message
from core.retrieve import answer_with_chunks

_UNAVAILABLE_ANSWER = (
    "Não consegui acessar a base de conhecimento agora — esta é uma "
    "resposta de exemplo para:\n\n> {question}"
)

# Mesmas frases-marcador usadas no backfill de `bot_respondeu` na migration
# 0004 — quem responde de acordo com o system prompt de retrieve.py usa esse
# vocabulário quando não achou contexto suficiente. Aproximação, não um
# classificador exato (mesma ressalva do dashboard).
_FRASES_NAO_RESPONDIDO = (
    "não encontr",
    "não há informa",
    "não tenho essa informa",
    "não consegui acessar a base de conhecimento",
)



def _bot_respondeu(resposta: str) -> bool:
    texto = resposta.lower()
    return not any(frase in texto for frase in _FRASES_NAO_RESPONDIDO)


def answer_question(
    question: str, history: list[Message] | None = None
) -> tuple[str, list[dict], bool]:
    """Responde a pergunta via RAG híbrido; cai num aviso se o backend falhar.

    `history` são as mensagens anteriores da conversa (chat_state.Message,
    o mesmo modelo usado pela UI e pela persistência), sem a pergunta atual;
    vira o `history_context` do prompt, para perguntas de acompanhamento
    ("quero", "e sobre isso?") enxergarem o turno anterior.

    Devolve a resposta, os chunks recuperados que a embasaram (pra exibir
    como fonte/anexo na UI) e `bot_respondeu` (False se caiu no fallback de
    exceção ou se a resposta bate com a heurística de "não sei") — sinal que
    o chamador repassa pra `store.salvar_mensagem` (TAI7-13/14).
    """

    try:
        resposta, chunks = answer_with_chunks(question, history)
        return resposta, chunks, _bot_respondeu(resposta)
    except Exception:
        return _UNAVAILABLE_ANSWER.format(question=question), [], False
