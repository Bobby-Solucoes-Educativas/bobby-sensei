-- TAI7-13: o requisito central do ticket — sinal explícito de "o bot achou
-- contexto e respondeu" (true) vs "caiu no fallback" (false), NULL só pra
-- mensagens de usuário. Backfill das mensagens de assistente já existentes
-- via a mesma heurística de frases usada em dashboard_data.py pra achar
-- "perguntas não respondidas" — aproximação sobre dado histórico, não exata.
ALTER TABLE mensagens ADD COLUMN bot_respondeu BOOLEAN;
ALTER TABLE mensagens ADD CONSTRAINT mensagens_bot_respondeu_check
    CHECK (papel = 'assistente' OR bot_respondeu IS NULL);

UPDATE mensagens
SET bot_respondeu = NOT (conteudo ILIKE ANY (ARRAY[
    '%não encontr%',
    '%não há informa%',
    '%não tenho essa informa%',
    '%não consegui acessar a base de conhecimento%'
]))
WHERE papel = 'assistente';
