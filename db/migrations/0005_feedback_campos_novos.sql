-- TAI7-13: feedback ganha positivo (boolean, no lugar de rating texto),
-- atualizada_em (pro upsert de troca de voto) e os nomes em português.
ALTER TABLE feedback ADD COLUMN id_novo BIGINT GENERATED ALWAYS AS IDENTITY;

ALTER TABLE feedback ADD COLUMN mensagem_id BIGINT;
UPDATE feedback f SET mensagem_id = m.id_novo
FROM mensagens m WHERE m.id = f.message_id;
ALTER TABLE feedback ALTER COLUMN mensagem_id SET NOT NULL;

ALTER TABLE feedback ADD COLUMN positivo BOOLEAN;
UPDATE feedback SET positivo = (rating = 'up');
ALTER TABLE feedback ALTER COLUMN positivo SET NOT NULL;

ALTER TABLE feedback RENAME COLUMN comment TO comentario;
ALTER TABLE feedback RENAME COLUMN created_at TO criada_em;
ALTER TABLE feedback ADD COLUMN atualizada_em TIMESTAMPTZ NOT NULL DEFAULT now();
UPDATE feedback SET atualizada_em = criada_em;
