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
  -> _condense_question (reescreve o acompanhamento como pergunta autônoma,
                         só para servir de query da busca)
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
(10), `RRF_K` (60) — valores provisórios do MVP, a calibrar depois de testar
com perguntas reais (critério de aceite do ticket). `TOP_K_FINAL` começou em
5 e foi ajustado para 10 depois da validação ponta a ponta — mais chunks de
contexto disponíveis tanto para o prompt do LLM quanto para a lista de
fontes exibida pela interface (ver "Pontos de entrada públicos" abaixo).

## Prompt e histórico

`ChatPromptTemplate` com três blocos, nesta ordem:

1. **system** (`_SYSTEM_PROMPT`, fixo): instrui a responder só com o
   contexto fornecido, em português, e admitir quando a documentação não
   cobre a pergunta.
2. **`MessagesPlaceholder("history_context")`**: as trocas anteriores da
   conversa, cortadas para caber em `LIMIT_TOKENS_HISTORY_CONTEXT`.
3. **human**: contexto recuperado (formatado por `_format_context`) +
   pergunta atual.

Histórico e contexto são coisas diferentes de propósito: o histórico é "o
que já foi dito nessa conversa" (permite perguntas de acompanhamento tipo "e
o prazo disso?"); o contexto é recalculado do zero a cada pergunta, buscando
de novo no banco.

## Janela de contexto do histórico

`LIMIT_TOKENS_HISTORY_CONTEXT` (1000) é o teto de tokens de conversa anterior
que acompanha cada pergunta — restringe **só** o `history_context`, não o
contexto do RAG nem o system prompt. `build_history_context()` converte as
mensagens e corta com `trim_messages` do LangChain, mantendo as trocas mais
recentes e começando sempre numa pergunta do usuário (para o modelo não
receber uma resposta órfã). 1000 tokens cabem ~2 trocas no padrão de resposta
atual; o contexto do RAG sozinho já gasta ~2.500, então a janela é uma fração
modesta do prompt.

A contagem (`_estimate_tokens`) é aproximada de propósito (~4 caracteres por
token): o `tiktoken` não reconhece o `gpt-5.4-mini`, então uma contagem
"exata" seria o tokenizer de outro modelo fingindo precisão. Para um teto de
orçamento, a aproximação basta.

## Reescrita da pergunta para a busca (query condensation)

Sem isso, um acompanhamento como "quero" ou "e os filtros opcionais?" vira a
query literal do embedding/BM25 e recupera a página errada — o modelo entende
a pergunta pelo histórico, mas recebe contexto irrelevante e recusa responder.

`_condense_question()` usa o histórico para reescrever a pergunta como
autônoma (`"quero"` → `"Como emitir um atestado de matrícula?"`) e alimenta
**só a busca**; o prompt de resposta continua recebendo a pergunta original do
usuário. Três proteções: sem histórico (1º turno) pula a chamada ao LLM;
exceção cai na pergunta original; reescrita vazia ou acima de
`_MAX_CONDENSED_CHARS` (300) também cai na original — o pior caso é o
comportamento anterior a esta etapa.

## Pontos de entrada públicos (consumidos pela TAI7-9)

```python
def answer(pergunta: str, history: list[Message] | None = None) -> str
```

- `history` são as mensagens anteriores da conversa — os mesmos objetos
  `chat_state.Message` que a UI e a persistência (`core/store.py`) já usam,
  sem formato paralelo. **Não** inclui a pergunta atual.
- `history=None` por default — turno 1 de uma conversa nova funciona sem
  passar nada.
- Retorna a resposta como `str` puro — quem chama não precisa importar nada
  de `langchain_core`.

```python
def answer_with_chunks(
    pergunta: str, history: list[Message] | None = None
) -> tuple[str, list[dict]]
```

Mesma assinatura de entrada de `answer()`, mas devolve também a lista de
chunks que a fusão RRF recuperou (os mesmos dicts que `vector_search`/
`bm25_search` retornam, com `rrf_score` adicionado) — usado pela interface
pra exibir as fontes da resposta como anexo (ver `docs/chat-ui.md`, "5ª
passada"). Roda o mesmo retrieval e a mesma sub-chain de geração de
`answer()` (`_prompt | _llm | StrOutputParser()`, extraída para a constante
de módulo `_answer_chain` pra ser reaproveitada entre as duas funções sem
duplicar a definição) — só expõe o resultado intermediário do
`_hybrid_retrieve` que `answer()` mantém interno.

`answer()` continua existindo tal como antes (não foi alterada) para
qualquer consumidor que só precise do texto da resposta.

## Fonte de dados: tabela `chunks` (TAI7-6)

`_hybrid_retrieve` consulta a tabela `chunks` populada pela TAI7-6
(`embed.py`), com os campos produzidos pelo `format.py` (ver `docs/format.md`)
mais a coluna de embedding. O schema e os índices (HNSW vetorial + BM25 do
ParadeDB) entram via `db.ensure_schema()`, que aplica as migrations pendentes
em `db/migrations/`; a migration base está em
`db/migrations/0001_initial_schema.sql`. Detalhes e consultas em
`docs/embeddings.md`.

O pipeline foi validado ponta a ponta contra o banco real (2.289 chunks de
378 páginas): busca vetorial, busca BM25, fusão RRF e geração respondem
usando o contexto recuperado, citando a página de origem. As partes puras
seguem testáveis isoladamente sem banco:

- `reciprocal_rank_fusion` (função pura, com listas de chunks fabricadas)
- `_format_context` (função pura)
- A sub-chain `_prompt | _llm | StrOutputParser()` isolada, invocada
  diretamente com `{"pergunta", "history_context", "contexto"}` fabricados à mão —
  valida grounding (a resposta usa só o contexto) e uso real do histórico
  (uma pergunta de acompanhamento só faz sentido com a resposta anterior).

## Observações para a próxima etapa (interface — TAI7-9)

- Chamar `answer(pergunta, history)` (só o texto) ou
  `answer_with_chunks(pergunta, history)` (texto + fontes, usado hoje pela
  interface pra exibir os chunks como anexo) — todo o resto (retrieval,
  condensação, prompt, chain) é implementação interna do módulo.
- `history` é a própria lista de `chat_state.Message` da conversa, sem a
  pergunta atual (`conversation.messages[:-1]`) — sem conversão manual e sem
  formato paralelo: é o mesmo modelo que a UI e o `core/store.py` já usam.
- A sintaxe de `bm25_search` (operador `@@@`, `paradedb.score()`) foi
  validada com `pg_search` 0.24.3 — a API do ParadeDB muda entre versões, então
  reconferir se o time atualizar a imagem do banco.
