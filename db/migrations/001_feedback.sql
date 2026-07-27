-- 001_feedback.sql
-- Substitui o schema ad-hoc de conversas/mensagens/feedback criado por
-- core/db.py (ensure_schema) pela modelagem definitiva da TAI7-13
-- (bigint identity ids, atendente/session_id, papel/bot_respondeu/fontes,
-- positivo/comentario/atualizada_em). Os DROPs cobrem os bancos onde essas
-- tabelas já existiam no schema antigo.
DROP TABLE IF EXISTS feedback CASCADE;
DROP TABLE IF EXISTS mensagens CASCADE;
DROP TABLE IF EXISTS conversas CASCADE;

CREATE TABLE conversas (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    criada_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
    atendente   TEXT,
    session_id  TEXT
);

CREATE TABLE mensagens (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversa_id    BIGINT NOT NULL REFERENCES conversas(id) ON DELETE CASCADE,
    papel          TEXT   NOT NULL CHECK (papel IN ('usuario','assistente')),
    conteudo       TEXT   NOT NULL,
    bot_respondeu  BOOLEAN,
    fontes         JSONB,
    criada_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (papel = 'assistente' OR bot_respondeu IS NULL)
);

CREATE TABLE feedback (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mensagem_id    BIGINT NOT NULL UNIQUE REFERENCES mensagens(id) ON DELETE CASCADE,
    positivo       BOOLEAN NOT NULL,
    comentario     TEXT,
    criada_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizada_em  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Índices
CREATE INDEX idx_mensagens_conversa   ON mensagens (conversa_id);
CREATE INDEX idx_mensagens_criada_em  ON mensagens (criada_em);
CREATE INDEX idx_mensagens_nao_resp   ON mensagens (id) WHERE bot_respondeu = false;
-- feedback.mensagem_id já tem índice por ser UNIQUE
