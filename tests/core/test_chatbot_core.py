# Testes da contagem de rodadas de esclarecimento (fluxo investigativo do
# RAG, decisão do Arthur, 2026-07-29) — só a lógica pura, sem banco nem LLM:
# histórico fabricado como core.chat_state.Message, sem tocar RAG/DB.
import core.chatbot_core as chatbot_core
from core.chat_state import Message
from core.chatbot_core import (
    LIMITE_RODADAS_ESCLARECIMENTO,
    _rodadas_esclarecimento_consecutivas,
    answer_question,
)


def _msg(role: str, tipo_resposta: str | None = None) -> Message:
    return Message(role=role, content="texto qualquer", tipo_resposta=tipo_resposta)


def test_sem_historico_conta_zero_rodadas():
    assert _rodadas_esclarecimento_consecutivas(None) == 0
    assert _rodadas_esclarecimento_consecutivas([]) == 0


def test_ultimo_turno_foi_resposta_de_verdade_conta_zero():
    history = [
        _msg("user"),
        _msg("assistant", "resposta"),
    ]
    assert _rodadas_esclarecimento_consecutivas(history) == 0


def test_uma_pergunta_de_esclarecimento_conta_uma_rodada():
    history = [
        _msg("user"),
        _msg("assistant", "resposta"),
        _msg("user"),
        _msg("assistant", "pergunta_esclarecimento"),
    ]
    assert _rodadas_esclarecimento_consecutivas(history) == 1


def test_duas_perguntas_de_esclarecimento_seguidas_conta_duas_rodadas_e_bate_no_limite():
    history = [
        _msg("user"),
        _msg("assistant", "pergunta_esclarecimento"),
        _msg("user"),
        _msg("assistant", "pergunta_esclarecimento"),
    ]
    rodadas = _rodadas_esclarecimento_consecutivas(history)
    assert rodadas == 2
    assert rodadas >= LIMITE_RODADAS_ESCLARECIMENTO


def test_resposta_de_verdade_no_meio_reseta_a_contagem():
    # 1 esclarecimento, depois uma resposta de verdade, depois outro
    # esclarecimento — a sequência FINAL tem só 1 rodada, não 2: a resposta
    # de verdade no meio interrompe a sequência.
    history = [
        _msg("user"),
        _msg("assistant", "pergunta_esclarecimento"),
        _msg("user"),
        _msg("assistant", "resposta"),
        _msg("user"),
        _msg("assistant", "pergunta_esclarecimento"),
    ]
    assert _rodadas_esclarecimento_consecutivas(history) == 1


def test_historico_antigo_sem_tipo_resposta_nao_conta_como_esclarecimento():
    # Mensagens de antes desta feature têm tipo_resposta=None (migration
    # 0011, sem backfill heurístico) — None não é "pergunta_esclarecimento",
    # então interrompe a contagem em vez de contar como uma rodada.
    history = [
        _msg("user"),
        _msg("assistant", None),
    ]
    assert _rodadas_esclarecimento_consecutivas(history) == 0


class _RespostaFalsa:
    """Substitui core.retrieve.RespostaEstruturada nos testes abaixo — só
    precisa dos atributos que answer_question lê (tipo/texto), sem puxar
    langchain/pydantic pra dentro do teste."""

    def __init__(self, tipo: str, texto: str):
        self.tipo = tipo
        self.texto = texto


def test_no_limite_forca_sem_contexto_final_mesmo_se_llm_insistir_em_perguntar(monkeypatch):
    # Rede de segurança do item 2: já eram 2 rodadas de esclarecimento
    # seguidas (>= LIMITE_RODADAS_ESCLARECIMENTO) — mesmo se o LLM ignorar a
    # instrução do prompt (_MENSAGEM_LIMITE_RODADAS) e tentar perguntar de
    # novo, answer_question tem que fechar o turno como sem_contexto_final.
    # answer_with_chunks é mockado pra simular exatamente esse desrespeito ao
    # limite, sem chamar o LLM de verdade.
    def _answer_with_chunks_insiste(pergunta, history=None, ultima_rodada=False):
        assert ultima_rodada is True  # chatbot_core detectou o limite certo
        return _RespostaFalsa("pergunta_esclarecimento", "Mais uma pergunta..."), []

    monkeypatch.setattr(chatbot_core, "answer_with_chunks", _answer_with_chunks_insiste)

    history = [
        _msg("user"),
        _msg("assistant", "pergunta_esclarecimento"),
        _msg("user"),
        _msg("assistant", "pergunta_esclarecimento"),
    ]
    resposta, chunks, tipo = answer_question("pergunta qualquer", history)

    assert tipo == "sem_contexto_final"
    assert resposta != "Mais uma pergunta..."  # texto do LLM foi descartado


def test_abaixo_do_limite_no_llm_repassa_pergunta_esclarecimento(monkeypatch):
    # Sem chegar no limite (só 1 rodada anterior), o resultado do LLM passa
    # direto — não há override.
    def _answer_with_chunks_pergunta(pergunta, history=None, ultima_rodada=False):
        assert ultima_rodada is False
        return _RespostaFalsa("pergunta_esclarecimento", "Qual tela?"), []

    monkeypatch.setattr(chatbot_core, "answer_with_chunks", _answer_with_chunks_pergunta)

    history = [
        _msg("user"),
        _msg("assistant", "pergunta_esclarecimento"),
    ]
    resposta, chunks, tipo = answer_question("pergunta qualquer", history)

    assert tipo == "pergunta_esclarecimento"
    assert resposta == "Qual tela?"
