# Migração TAI7-12 → TAI7-13 (conversas/mensagens/feedback)

Scripts pra migrar o histórico real do CS (schema antigo, em prod) pro
schema novo da TAI7-13, sem tocar na pipeline de deploy — conforme
decidido com o Arthur em 2026-07-31 (dump → CSV → script de injeção).

Testado ponta a ponta contra dado sintético (ver `ddl_schema_legado.sql` +
`seed_dados_fake.sql`) em 2026-07-31: contagens batendo, traduções
corretas, heurística de `bot_respondeu` recalculada certo, vínculo
pergunta→resposta funcionando via o mesmo LATERAL que `core/feedback.py`/
`core/dashboard_data.py` já usam. **Ainda não rodou contra dado real.**

## Quando o dump do Arthur chegar

1. **Restaurar o dump num Postgres à parte** (nunca direto em prod nem no
   `sensei-db` de dev):
   ```
   docker run -d --name sensei-dump-real -e POSTGRES_PASSWORD=teste \
       -e POSTGRES_DB=prod_dump -p 5545:5432 postgres:16
   # se for um dump feito com pg_dump -Fc (formato custom):
   docker exec -i sensei-dump-real pg_restore -U postgres -d prod_dump < dump.bin
   # se for um .sql puro:
   docker exec -i sensei-dump-real psql -U postgres -d prod_dump < dump.sql
   ```

2. **Conferir que o schema restaurado bate com o que assumimos** — antes
   de rodar qualquer coisa, olhar `\d conversas`, `\d mensagens`,
   `\d feedback` no banco restaurado e comparar com
   `ddl_schema_legado.sql`. Se houver qualquer diferença (coluna a mais,
   tipo diferente, valores de `role`/`rating` fora do esperado), PARAR e
   ajustar os scripts antes de seguir — não assumir que bate só porque
   "provavelmente é isso".

3. **Extrair pra CSV**:
   ```
   DATABASE_URL_ORIGEM="postgresql://postgres:teste@localhost:5545/prod_dump" \
       python extrair_legado.py csv_prod_real
   ```

4. **Revisar os CSVs gerados** (`csv_prod_real/*.csv`) — conferir se as
   contagens batem com o que o CS reportou usar, abrir uma amostra pra
   ver se o texto/formato do `chunks` está como esperado.

5. **Criar o schema novo no destino** (ainda a decidir com o Arthur: uma
   base nova, ou o mesmo banco de prod depois de renomear as tabelas
   antigas) e rodar `db/migrations/001_feedback.sql` nele.

6. **Injetar**:
   ```
   DATABASE_URL_DESTINO="postgresql://.../destino" \
       python injetar_novo_schema.py csv_prod_real
   ```

7. **Validar** — rodar as 4 queries de validação da TAI7-13 (volume de
   perguntas, %👍/👎, lista de 👎 com pergunta+resposta, perguntas não
   respondidas) contra o destino e comparar com o que o CS relata ter
   visto/gerado. Só depois disso decidir com o Arthur o corte de fato
   pro app novo apontar pra este banco.

## Arquivos

- `ddl_schema_legado.sql` — reconstrução do schema antigo (não existe
  versionado em lugar nenhum; inferido do `core/persistence.py` da main).
- `seed_dados_fake.sql` — dado sintético usado só pra testar os scripts.
- `extrair_legado.py` — schema antigo → CSV. Só lê, nunca escreve.
- `injetar_novo_schema.py` — CSV → schema novo, com as traduções.

## Decisões que ainda dependem do Arthur

- Onde o schema novo vai viver de fato (banco novo vs. mesmo banco de
  prod com as tabelas antigas renomeadas) — isso muda o passo 5 acima.
- Janela/momento de cortar o app pra apontar pro banco migrado.
