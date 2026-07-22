# TAI7-9: orquestra o fluxo de resposta a uma pergunta, delegando o RAG
# híbrido (retrieval + LLM) para core/retrieve.py. Função pura, sem
# streamlit — reaproveitável por outros canais (WhatsApp/FastAPI) no futuro.
from core.retrieve import answer_with_chunks

_UNAVAILABLE_ANSWER = (
    "Não consegui acessar a base de conhecimento agora — esta é uma "
    "resposta de exemplo para:\n\n> {question}"
)


def answer_question(question: str) -> tuple[str, list[dict]]:
    """Responde a pergunta via RAG híbrido; cai num aviso se o backend falhar.

    Devolve a resposta e os chunks recuperados que a embasaram (pra exibir
    como fonte/anexo na UI); em caso de falha, chunks vem vazio.
    """

    try:
        return answer_with_chunks(question)
    except Exception:
        return _UNAVAILABLE_ANSWER.format(question=question), []
