-- Dados sintéticos cobrindo os casos de borda que importam pra migração:
-- título nulo, mensagem sem feedback, 👎 sem comentário, resposta que bate
-- com a heurística de "não sei" (pra testar o recálculo de bot_respondeu),
-- e mais de uma conversa/mensagem pra testar a ordenação cronológica.

INSERT INTO conversas (id, title) VALUES
    ('c1', 'Duvida sobre atestados'),
    ('c2', NULL),
    ('c3', 'Outra pergunta');

INSERT INTO mensagens (id, conversation_id, role, content, chunks, reply_to, created_at) VALUES
    ('m1', 'c1', 'user',      'Aonde localizo o atestado de frequência?', NULL, NULL, '2026-07-20 10:00:00-03'),
    ('m2', 'c1', 'assistant', 'A declaração que informa que o aluno está estudando aparece como Atestado de Frequência.',
        '[{"breadcrumb": "Bobby Educ > Submenu atestados", "url": "https://example.atlassian.net/wiki/x"}]'::jsonb,
        'm1', '2026-07-20 10:00:45-03'),
    ('m3', 'c1', 'user',      'E onde fica o menu?', NULL, NULL, '2026-07-20 10:02:00-03'),
    ('m4', 'c1', 'assistant', 'No menu Documentos > Atestados > Atestado de Frequência.',
        '[{"breadcrumb": "Bobby Educ > Submenu atestados", "url": "https://example.atlassian.net/wiki/x"}]'::jsonb,
        'm3', '2026-07-20 10:02:30-03'),
    ('m5', 'c2', 'user',      'Como funciona o módulo de avaliação numérica?', NULL, NULL, '2026-07-21 09:00:00-03'),
    ('m6', 'c2', 'assistant', 'não encontrei essa informação na documentação, não consigo ajudar.',
        '[]'::jsonb, 'm5', '2026-07-21 09:00:20-03'),
    ('m7', 'c3', 'user',      'Pergunta qualquer sobre outro assunto', NULL, NULL, '2026-07-22 14:00:00-03'),
    ('m8', 'c3', 'assistant', 'Resposta normal e completa sobre o assunto.',
        '[{"breadcrumb": "Bobby Educ > Pagina X", "url": "https://example.atlassian.net/wiki/y"}]'::jsonb,
        'm7', '2026-07-22 14:00:40-03');

INSERT INTO feedback (message_id, rating, comment, created_at) VALUES
    ('m2', 'down', 'Aqui o sistema tem que atender o pedido de atestado de Matricula, o atestado de frequência é outro documento.', '2026-07-20 10:01:30-03'),
    ('m4', 'up',   NULL, '2026-07-20 10:03:00-03'),
    ('m8', 'down', NULL, '2026-07-22 14:05:00-03');
-- m6 fica sem feedback de propósito — testa mensagem assistente sem 👍/👎.
