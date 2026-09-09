-- Identifica quem enviou o 👍/👎 (login geral do app, TAI7-24) — par de
-- `criada_em` na mesma tabela, mesmo padrão de `classificado_por`/
-- `classificado_em`. Fica NULL pro histórico anterior ao login, que nunca
-- teve essa identidade disponível.
ALTER TABLE feedback ADD COLUMN criado_por TEXT;
