-- TAI7-13: índices pedidos no ticket. mensagens_conversation_id_idx caiu
-- junto com a coluna antiga na 0006; recriando com o nome/coluna novos.
CREATE INDEX idx_mensagens_conversa ON mensagens (conversa_id);
CREATE INDEX idx_mensagens_criada_em ON mensagens (criada_em);
CREATE INDEX idx_mensagens_nao_resp ON mensagens (id) WHERE bot_respondeu = false;
-- feedback.mensagem_id já tem índice por ser UNIQUE (feedback_mensagem_id_key)
