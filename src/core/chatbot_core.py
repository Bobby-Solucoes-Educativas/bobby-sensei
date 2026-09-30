# TAI7-9/TAI7-14: orquestra o fluxo de resposta a uma pergunta, delegando o
# RAG híbrido (retrieval + LLM) para core/retrieve.py. Função pura, sem
# streamlit — reaproveitável por outros canais (WhatsApp/FastAPI) no futuro.
from core.chat_state import Message
from core.retrieve import answer_with_chunks

_UNAVAILABLE_ANSWER = (
    "Não consegui acessar a base de conhecimento agora — esta é uma "
    "resposta de exemplo para:\n\n> {question}"
)

# Quantas rodadas de pergunta_esclarecimento seguidas o bot pode emitir antes
# de ser forçado a desistir (fluxo investigativo, decisão do Arthur,
# 2026-07-29). A contagem mora AQUI, não só no LLM (ver retrieve._SYSTEM_PROMPT
# e _MENSAGEM_LIMITE_RODADAS) — o modelo pode ignorar a instrução do prompt,
# então isso é a rede de segurança que garante o corte.
LIMITE_RODADAS_ESCLARECIMENTO = 2

# Desistência de reserva, usada só quando o LLM ignora `ultima_rodada` e tenta
# perguntar de novo mesmo depois do limite (ver answer_question) — o texto
# natural do modelo (_MENSAGEM_LIMITE_RODADAS) é preferível quando ele
# respeita a instrução; isto aqui é o fallback determinístico.
#
# A oferta de chamado aqui é só texto — decisões do Arthur sobre a criação de
# verdade (validadas em 2026-09-22/23) ficam registradas, mas fora do escopo
# desta sprint:
# - destino: Jira (não só Postgres, como estava anotado antes); a integração
#   em si fica pra uma sprint futura, com desenho mais detalhado.
# - canal-alvo: pensado mais pro WhatsApp do que pro chat web atual — quando
#   essa lógica for implementada de verdade, precisa nascer em core/ (sem
#   streamlit), reaproveitável por qualquer canal, mesmo padrão já usado no
#   resto do projeto.
# - classificação: fica manual, mesmo fluxo de hoje (atendente classifica
#   documentação x pipeline no dashboard após o 👎, ver
#   core.store.classificar_feedback) — o chamado NÃO nasce pré-classificado
#   automaticamente.
# - gatilho (criação automática vs. bot pergunta antes de criar): ainda em
#   aberto, não decidido.
_DESISTENCIA_LIMITE_RODADAS = (
    "Não consegui achar essa informação na documentação, mesmo depois de "
    "tentar entender melhor o que aconteceu. Quer que eu abra um chamado "
    "para o time verificar?"
)


def _rodadas_esclarecimento_consecutivas(history: list[Message] | None) -> int:
    """Conta os turnos finais consecutivos do assistente em `history` com
    tipo_resposta="pergunta_esclarecimento" — sequência não interrompida por
    uma resposta de verdade (tipo="resposta") ou por uma desistência anterior
    (tipo="sem_contexto_final").

    Varre de trás pra frente pulando as mensagens de usuário (só os turnos do
    assistente contam pra sequência) e para no primeiro turno do assistente
    que não for pergunta_esclarecimento. Histórico anterior a esta feature
    tem tipo_resposta=None nas mensagens de assistente — None não bate com
    "pergunta_esclarecimento", então interrompe a contagem (comportamento
    certo: não tem como saber se aquele turno antigo era um esclarecimento).
    """

    rodadas = 0
    for mensagem in reversed(history or []):
        if mensagem.role != "assistant":
            continue
        if mensagem.tipo_resposta != "pergunta_esclarecimento":
            break
        rodadas += 1
    return rodadas


def answer_question(
    question: str, history: list[Message] | None = None
) -> tuple[str, list[dict], str]:
    """Responde a pergunta via RAG híbrido; cai num aviso se o backend falhar.

    `history` são as mensagens anteriores da conversa (chat_state.Message,
    o mesmo modelo usado pela UI e pela persistência), sem a pergunta atual;
    vira o `history_context` do prompt, para perguntas de acompanhamento
    ("quero", "e sobre isso?") enxergarem o turno anterior — e também é de
    onde vem a contagem de rodadas de esclarecimento (ver
    _rodadas_esclarecimento_consecutivas).

    Devolve a resposta, os chunks recuperados que a embasaram (pra exibir
    como fonte/anexo na UI) e `tipo_resposta` ("resposta",
    "pergunta_esclarecimento" ou "sem_contexto_final") — sinal que o
    chamador repassa pra `store.salvar_mensagem` (TAI7-13/14).
    """

    rodadas = _rodadas_esclarecimento_consecutivas(history)
    ultima_rodada = rodadas >= LIMITE_RODADAS_ESCLARECIMENTO

    try:
        resultado, chunks = answer_with_chunks(question, history, ultima_rodada=ultima_rodada)
    except Exception:
        return _UNAVAILABLE_ANSWER.format(question=question), [], "sem_contexto_final"

    tipo, texto = resultado.tipo, resultado.texto
    if ultima_rodada and tipo == "pergunta_esclarecimento":
        # Rede de segurança (não depender só do LLM respeitar o limite): já
        # avisamos via _MENSAGEM_LIMITE_RODADAS, mas se ele insistir em
        # perguntar de novo, fechamos o turno aqui mesmo assim.
        tipo, texto = "sem_contexto_final", _DESISTENCIA_LIMITE_RODADAS

    return texto, chunks, tipo
