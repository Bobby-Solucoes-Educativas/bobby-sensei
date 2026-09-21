-- Classificação da causa de um 👎 (documentação x pipeline) e atribuição
-- automática do time responsável (Time de Desenvolvimento x Time 7).
-- Quem classifica é o atendente, manualmente, pelo dashboard — não é
-- automático nem feito pelo usuário no momento do 👎. categoria e
-- time_atribuido ficam em colunas separadas (não é derivado só na
-- aplicação) pra permitir override manual do time sugerido.
ALTER TABLE feedback
    ADD COLUMN categoria TEXT CHECK (categoria IN ('documentacao', 'pipeline')),
    ADD COLUMN time_atribuido TEXT CHECK (time_atribuido IN ('time_7', 'time_dev')),
    ADD COLUMN classificado_por TEXT,
    ADD COLUMN classificado_em TIMESTAMPTZ,
    ADD CONSTRAINT feedback_categoria_so_negativo
        CHECK (categoria IS NULL OR positivo = false);

-- categoria/time_atribuido ficam NULL até alguém classificar — é assim que
-- o dashboard sabe o que está na fila de "👎 sem classificar" (todo o
-- histórico de 👎 já existente entra na fila de uma vez, por não ter valor
-- nessas colunas).
CREATE INDEX idx_feedback_categoria ON feedback (categoria) WHERE categoria IS NOT NULL;
