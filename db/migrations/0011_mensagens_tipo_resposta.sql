-- Fluxo investigativo do RAG antes de desistir (decisão do Arthur,
-- 2026-07-29): o LLM agora devolve um desfecho estruturado por turno em vez
-- de só texto livre (ver src/core/retrieve.py, RespostaEstruturada) —
-- "resposta" respondeu de verdade, "pergunta_esclarecimento" ainda está
-- investigando, "sem_contexto_final" desistiu. Mesmo padrão de
-- bot_respondeu na migration 0004: NULL só pra mensagens de usuário.
--
-- Sem backfill heurístico aqui (diferente da 0004): não dá pra inferir de
-- forma razoável, a partir do texto de uma resposta antiga, se ela foi uma
-- pergunta de esclarecimento ou uma desistência definitiva — fica NULL pro
-- histórico existente.
ALTER TABLE mensagens ADD COLUMN tipo_resposta TEXT
    CHECK (tipo_resposta IN ('resposta', 'pergunta_esclarecimento', 'sem_contexto_final'));
ALTER TABLE mensagens ADD CONSTRAINT mensagens_tipo_resposta_papel_check
    CHECK (papel = 'assistente' OR tipo_resposta IS NULL);
