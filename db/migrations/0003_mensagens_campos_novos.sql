-- TAI7-13: mensagens ganha os nomes em português (papel, conteudo, fontes)
-- e as pontes bigint (id_novo, conversa_id via conversas.id_novo,
-- reply_to_novo auto-referente). Os valores de papel são convertidos agora
-- (não dá pra deixar pra depois: o CHECK novo já exige 'usuario'/'assistente').
ALTER TABLE mensagens ADD COLUMN id_novo BIGINT GENERATED ALWAYS AS IDENTITY;

ALTER TABLE mensagens ADD COLUMN conversa_id BIGINT;
UPDATE mensagens m SET conversa_id = c.id_novo
FROM conversas c WHERE c.id = m.conversation_id;
ALTER TABLE mensagens ALTER COLUMN conversa_id SET NOT NULL;

-- auto-referente: só dá pra remapear depois que id_novo (acima) já está
-- populada pra tabela inteira.
ALTER TABLE mensagens ADD COLUMN reply_to_novo BIGINT;
UPDATE mensagens m SET reply_to_novo = r.id_novo
FROM mensagens r WHERE r.id = m.reply_to;

ALTER TABLE mensagens RENAME COLUMN role TO papel;
ALTER TABLE mensagens DROP CONSTRAINT mensagens_role_check;
UPDATE mensagens SET papel = CASE papel
    WHEN 'user' THEN 'usuario'
    WHEN 'assistant' THEN 'assistente'
END;
ALTER TABLE mensagens ADD CONSTRAINT mensagens_papel_check CHECK (papel IN ('usuario', 'assistente'));

ALTER TABLE mensagens RENAME COLUMN content TO conteudo;
ALTER TABLE mensagens RENAME COLUMN chunks TO fontes;
ALTER TABLE mensagens RENAME COLUMN created_at TO criada_em;
