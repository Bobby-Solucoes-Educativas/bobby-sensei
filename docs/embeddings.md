# Embeddings e banco vetorial (TAI7-6)

O `src/core/embed.py` lê os chunks formatados, gera embeddings via
OpenAI `text-embedding-3-small` e carrega tudo na tabela `chunks` do
Postgres + ParadeDB — deixando o corpus pronto para a busca híbrida do
retrieval.

## Como rodar

Pré-requisitos:

- banco de pé: `docker compose up -d db`;
- `data/processed/chunks.jsonl` gerado: `python src/core/format.py`;
- `OPENAI_API_KEY` e `DATABASE_URL` no `.env`;
- pacote instalado no venv (uma vez): `pip install -e .`.

```bash
python src/core/embed.py
```

O script cria a tabela/índices se não existirem (`db.ensure_schema()`), gera os
embeddings em lotes e recarrega a tabela. Rodada de referência: 2.289 chunks de
378 páginas, ~5 chamadas à API, custo da ordem de centavos.

## Tabela `chunks`

Uma linha por chunk, espelhando o `chunks.jsonl` + o embedding:

| Coluna | Tipo | Origem/observação |
|---|---|---|
| `chunk_id` | text (PK) | `{page_id}-{chunk_index}`, vem da formatação. |
| `page_id`, `title`, `url`, `parent_id`, `breadcrumb`, `chunk_index` | text/int | Metadados da página de origem (formatação). |
| `text` | text | Texto do chunk, já com breadcrumb prefixado — é o que foi embeddado. |
| `ancestors`, `attachments` | jsonb | Estrutura preservada da formatação. |
| `embedding` | vector(1536) | `text-embedding-3-small`, dimensão nativa, sem truncamento. |
| `embedded_at` | timestamptz | Quando o chunk foi carregado. |

Índices:

- `chunks_embedding_idx` — **HNSW** (`vector_cosine_ops`): busca vetorial por
  similaridade de cosseno;
- `chunks_bm25_idx` — **BM25** via `pg_search` sobre `title` + `text`
  (`key_field = chunk_id`): busca por palavra-chave;
- `chunks_page_id_idx` — apoio para operações por página.

Os índices são mantidos automaticamente pelo Postgres a cada carga.

## Consultas de referência (para o retrieval, TAI7-8)

```sql
-- Busca vetorial: top-k por similaridade de cosseno com o vetor da pergunta
-- (:query_embedding é o embedding da pergunta, gerado com o mesmo modelo)
SELECT chunk_id, title, url, text
FROM chunks
ORDER BY embedding <=> :query_embedding
LIMIT 10;

-- Busca BM25: top-k por palavra-chave, com score de relevância
SELECT chunk_id, title, url, text, paradedb.score(chunk_id) AS score
FROM chunks
WHERE text @@@ 'reclassificação de alunos'
ORDER BY score DESC
LIMIT 10;
```

O operador `<=>` é distância de cosseno (menor = mais parecido); `@@@` é o
match BM25 do `pg_search`. As duas listas são combinadas no TAI7-8
(ex.: Reciprocal Rank Fusion) para o top-k final.

## Decisões registradas

- **HNSW em vez de IVFFlat** — melhor recall, e não depende de dados presentes
  na criação (o IVFFlat "treina" os agrupamentos com o que existir na tabela).
- **Carga por TRUNCATE + INSERT em transação única** — o pipeline diário
  regenera o corpus inteiro; recomeçar a tabela evita chunks órfãos de páginas
  removidas. Se a carga falhar no meio, o rollback preserva a carga anterior.
- **Lotes de 512 textos por chamada** — limite da API é 2048 entradas/request;
  5 chamadas cobrem o corpus atual.
