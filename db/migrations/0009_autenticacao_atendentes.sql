-- Login geral do app (chat + dashboard): a mesma conta autentica tanto o
-- envio de feedback no chat quanto a classificação de feedback no
-- dashboard (TAI7-24). Senha com hash (bcrypt, nunca texto puro) — ver
-- core/auth.py. Sem FK de conversas.atendente/feedback.classificado_por
-- pra cá de propósito: essas colunas já são texto solto (snapshot do
-- e-mail no momento da ação), não uma referência viva — uma conta
-- removida não deve arrastar exclusão em cascata do histórico.
CREATE TABLE atendentes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    senha_hash TEXT NOT NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
