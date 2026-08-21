-- Schema antigo (TAI7-12), reconstruído a partir do que core/persistence.py
-- e core/dashboard_data.py (main) realmente usam — NUNCA foi versionado no
-- repo, então isto é a melhor reconstrução possível sem ver o dado real.
-- Serve só pra simular localmente o formato que o dump de prod deve ter.
CREATE TABLE conversas (
    id     TEXT PRIMARY KEY,
    title  TEXT
);

CREATE TABLE mensagens (
    id               TEXT PRIMARY KEY,
    conversation_id  TEXT NOT NULL REFERENCES conversas(id) ON DELETE CASCADE,
    role             TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content          TEXT NOT NULL,
    chunks           JSONB,
    reply_to         TEXT REFERENCES mensagens(id),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE feedback (
    message_id  TEXT PRIMARY KEY REFERENCES mensagens(id) ON DELETE CASCADE,
    rating      TEXT NOT NULL CHECK (rating IN ('up', 'down')),
    comment     TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
