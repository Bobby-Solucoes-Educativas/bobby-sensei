# Orquestração da chain RAG híbrida (TAI7-8)

O `src/core/retrieve.py` implementa o retrieval híbrido (vetorial + BM25 via
ParadeDB) e a geração da resposta com o GPT-5.4 mini, orquestrados como uma
chain LangChain (LCEL). É o módulo que a interface Streamlit (TAI7-9) chama —
sem `import streamlit` aqui (decisão de arquitetura de 2026-07-06).

## Como rodar (teste manual interativo)

Requer `OPENAI_API_KEY` no `.env`. Para o retrieval de verdade (não só o
teste manual isolado), requer também a tabela `chunks` populada num ParadeDB
rodando — ver "Dependência" abaixo.

```bash
python src/core/retrieve.py
```

Abre um loop `Pergunta (Enter para sair):` que acumula o histórico da
conversa a cada rodada, simulando o uso real pela interface.

## Fluxo da chain

```
pergunta + histórico
  -> _hybrid_retrieve   (embedding da pergunta -> busca vetorial + BM25 -> RRF)
  -> _format_context    (chunks recuperados viram texto numerado com fonte)
  -> prompt             (ChatPromptTemplate: system + histórico + contexto + pergunta)
  -> llm                (ChatOpenAI, GPT-5.4 mini)
  -> StrOutputParser    (extrai a resposta como str)
```

Montada com o operador `|` do LCEL:

```python
rag_chain = (
    RunnablePassthrough.assign(contexto=RunnableLambda(_retrieve_and_format))
    | _prompt
    | _llm
    | StrOutputParser()
)
```

O retrieval híbrido em si (`vector_search`, `bm25_search`,
`reciprocal_rank_fusion`) é psycopg cru, não LangChain — a lib não tem um
retriever pronto para ParadeDB/pg_search híbrido com RRF, então essa lógica é
só encapsulada numa função (`_hybrid_retrieve`) e injetada na chain via
`RunnableLambda`.

## Retrieval híbrido

1. **Busca vetorial** (`vector_search`): similaridade de cosseno via pgvector
   (`embedding <=> ...`), top-`TOP_K_EACH` candidatos.
2. **Busca BM25** (`bm25_search`): relevância por palavra-chave via
   `pg_search`/Tantivy do ParadeDB (`text @@@ ...`), top-`TOP_K_EACH`
   candidatos. Complementa a busca vetorial pegando correspondência exata de
   termos (siglas, nomes de sistema) que a similaridade semântica às vezes
   perde.
3. **Fusão** (`reciprocal_rank_fusion`): combina as duas listas somando
   `1/(RRF_K + posição)` por chunk em cada lista onde ele aparece — ignora a
   escala dos scores (cosseno e BM25 não são comparáveis diretamente),
   olhando só a posição. `RRF_K = 60` é o valor clássico do paper (Cormack et
   al., 2009).

Constantes ajustáveis no topo do arquivo: `TOP_K_EACH` (20), `TOP_K_FINAL`
(5), `RRF_K` (60) — valores provisórios do MVP, a calibrar depois de testar
com perguntas reais (critério de aceite do ticket).

## Prompt e histórico

`ChatPromptTemplate` com três blocos, nesta ordem:
1. **system** (`_SYSTEM_PROMPT`, fixo): instrui a responder só com o
   contexto fornecido, em português, e admitir quando a documentação não
   cobre a pergunta.
2. **`MessagesPlaceholder("historico")`**: as trocas anteriores da conversa.
3. **human**: contexto recuperado (formatado por `_format_context`) +
   pergunta atual.

Histórico e contexto são coisas diferentes de propósito: o histórico é "o
que já foi dito nessa conversa" (permite perguntas de acompanhamento tipo "e
o prazo disso?"); o contexto é recalculado do zero a cada pergunta, buscando
de novo no banco.

## Único ponto de entrada público (consumido pela TAI7-9)

```python
def answer(pergunta: str, historico: list[dict] | None = None) -> str
```

- `historico` segue o mesmo formato de `st.session_state.messages` do
  Streamlit: `[{"role": "user"|"assistant", "content": str}, ...]`, **sem**
  incluir a pergunta atual.
- `historico=None` por default — turno 1 de uma conversa nova funciona sem
  passar nada.
- Retorna a resposta como `str` puro — o `app.py` não precisa importar nada
  de `langchain_core`.

## Dependência: schema esperado da tabela `chunks` (TAI7-6)

`_hybrid_retrieve` assume que a TAI7-6 populou uma tabela num ParadeDB
rodando, com os campos produzidos pelo `format.py` (ver `docs/format.md`)
mais a coluna de embedding:

```sql
CREATE TABLE chunks (
    chunk_id     text PRIMARY KEY,   -- "<page_id>-<indice>"
    page_id      text,
    title        text,
    url          text,
    parent_id    text,
    ancestors    jsonb,
    breadcrumb   text,
    chunk_index  int,
    text         text,               -- já inclui o breadcrumb no topo
    attachments  jsonb,
    embedding    vector(1536)        -- text-embedding-3-small, dim nativa
);

CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON chunks USING bm25 (chunk_id, text) WITH (key_field='chunk_id');
```

Enquanto esse schema não existir com dados reais, `_hybrid_retrieve`/`answer()`
levantam erro de conexão/tabela inexistente. As partes que não tocam o banco
já são testáveis isoladamente:
- `reciprocal_rank_fusion` (função pura, com listas de chunks fabricadas)
- `_format_context` (função pura)
- A sub-chain `_prompt | _llm | StrOutputParser()` isolada, invocada
  diretamente com `{"pergunta", "historico", "contexto"}` fabricados à mão —
  valida grounding (a resposta usa só o contexto) e uso real do histórico
  (uma pergunta de acompanhamento só faz sentido com a resposta anterior)
  contra a API da OpenAI de verdade.

## Observações para a próxima etapa (interface — TAI7-9)

- Chamar só `answer(pergunta, historico)` — todo o resto (retrieval, prompt,
  chain) é implementação interna do módulo.
- `historico` pode ser passado direto de `st.session_state.messages` (mesmo
  formato de dict), sem conversão manual.
- Confirmar a sintaxe de `bm25_search` (operador `@@@`, `paradedb.score()`)
  contra a versão do ParadeDB fixada assim que o banco subir — a API do
  `pg_search` muda entre versões.
