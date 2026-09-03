-- TAI7-13: corte final — promove as pontes bigint (id_novo/conversa_id/
-- reply_to_novo/mensagem_id) a colunas reais, derruba os ids texto antigos.
-- Passo 1: derruba TODAS as FKs antigas primeiro (senão não dá pra derrubar
-- a PK de conversas/mensagens enquanto outra tabela ainda referencia ela).
ALTER TABLE mensagens DROP CONSTRAINT mensagens_reply_to_fkey;
ALTER TABLE mensagens DROP CONSTRAINT mensagens_conversation_id_fkey;
ALTER TABLE feedback DROP CONSTRAINT feedback_message_id_fkey;

-- Passo 2: corte por tabela, em ordem de dependência — conversas (sem
-- dependência) -> mensagens (referencia conversas.id) -> feedback
-- (referencia mensagens.id).
ALTER TABLE conversas DROP CONSTRAINT conversas_pkey;
ALTER TABLE conversas DROP COLUMN id;
ALTER TABLE conversas RENAME COLUMN id_novo TO id;
ALTER TABLE conversas ADD PRIMARY KEY (id);

ALTER TABLE mensagens DROP CONSTRAINT mensagens_pkey;
ALTER TABLE mensagens DROP COLUMN conversation_id;
ALTER TABLE mensagens DROP COLUMN reply_to;
ALTER TABLE mensagens DROP COLUMN id;
ALTER TABLE mensagens RENAME COLUMN id_novo TO id;
ALTER TABLE mensagens RENAME COLUMN reply_to_novo TO reply_to;
ALTER TABLE mensagens ADD PRIMARY KEY (id);
ALTER TABLE mensagens ADD CONSTRAINT mensagens_conversa_id_fkey
    FOREIGN KEY (conversa_id) REFERENCES conversas(id) ON DELETE CASCADE;
ALTER TABLE mensagens ADD CONSTRAINT mensagens_reply_to_fkey
    FOREIGN KEY (reply_to) REFERENCES mensagens(id) ON DELETE SET NULL;

ALTER TABLE feedback DROP CONSTRAINT feedback_message_id_key;
ALTER TABLE feedback DROP CONSTRAINT feedback_pkey;
ALTER TABLE feedback DROP COLUMN message_id;
ALTER TABLE feedback DROP COLUMN rating;
ALTER TABLE feedback DROP COLUMN id;
ALTER TABLE feedback RENAME COLUMN id_novo TO id;
ALTER TABLE feedback ADD PRIMARY KEY (id);
ALTER TABLE feedback ADD CONSTRAINT feedback_mensagem_id_key UNIQUE (mensagem_id);
ALTER TABLE feedback ADD CONSTRAINT feedback_mensagem_id_fkey
    FOREIGN KEY (mensagem_id) REFERENCES mensagens(id) ON DELETE CASCADE;
