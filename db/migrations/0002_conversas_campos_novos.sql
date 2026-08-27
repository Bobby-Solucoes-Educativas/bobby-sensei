-- TAI7-13: conversas ganha os campos do ticket (atendente, session_id) e os
-- nomes em português. id_novo é uma "ponte" bigint identity — mensagens
-- ainda referencia o id (text) antigo, que só é trocado na migration de
-- corte (0006), depois que mensagens/feedback já mapearam pra esse bigint.
ALTER TABLE conversas ADD COLUMN id_novo BIGINT GENERATED ALWAYS AS IDENTITY;
ALTER TABLE conversas ADD COLUMN atendente TEXT;
ALTER TABLE conversas ADD COLUMN session_id TEXT;
ALTER TABLE conversas RENAME COLUMN title TO titulo;
ALTER TABLE conversas RENAME COLUMN created_at TO criada_em;
