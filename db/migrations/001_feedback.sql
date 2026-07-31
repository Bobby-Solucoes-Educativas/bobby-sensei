-- 001_feedback.sql
-- Cria o schema definitivo da TAI7-13 (bigint identity ids, atendente/
-- session_id, papel/bot_respondeu/fontes, positivo/comentario/
-- atualizada_em) num banco/destino que ainda não tem essas tabelas.
--
-- IMPORTANTE: este arquivo NÃO dá DROP nas tabelas antigas. Uma versão
-- anterior deste script tinha `DROP TABLE ... CASCADE` no início — isso
-- teria apagado, sem chance de volta, todo o histórico de conversas/
-- feedback que o time de CS já gerou usando o prod atual (schema antigo
-- da TAI7-12). Removido de propósito (2026-07-31): ver migração dos dados
-- legados em scripts/migracao_tai7_13/. Rodar este arquivo direto contra
-- um banco que ainda tem as tabelas antigas vai falhar com "already
-- exists" — é o comportamento esperado, não um bug.
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
