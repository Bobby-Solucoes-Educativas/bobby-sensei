# TAI7-8: orquestração da chain RAG (LangChain) — retrieval híbrido (vetorial + BM25) + GPT-5.4 mini
"""Pipeline de retrieval híbrido + geração da resposta, orquestrado com LangChain (LCEL).

Fluxo (RAG híbrido, ponta a ponta):
    pergunta + histórico
      -> _hybrid_retrieve   (embedding da pergunta -> busca vetorial + BM25 -> RRF)
      -> _format_context    (chunks recuperados viram texto numerado com fonte)
      -> prompt             (ChatPromptTemplate: system + histórico + contexto + pergunta)
      -> llm                (ChatOpenAI, GPT-5.4 mini)
      -> StrOutputParser    (extrai a resposta como str)

A chain propriamente dita (prompt -> llm -> parser) é montada com LCEL
(operador `|`), como pedido na atualização da TAI7-8 de 2026-07-15. O
retrieval híbrido em si continua sendo psycopg cru (LangChain não tem
retriever pronto pra ParadeDB/pg_search híbrido com RRF) — ele é só
encapsulado numa função e injetado na chain via `RunnableLambda`.

Sem `import streamlit` (decisão de arquitetura de 2026-07-06): esta lógica é
pura e reutilizável; o app.py é quem chama `answer()` e desenha a tela.

Único ponto de entrada público (consumido pela TAI7-9, interface Streamlit):

    answer(pergunta: str, historico: list[dict] | None = None) -> str

`historico` segue o mesmo formato de `st.session_state.messages` do
Streamlit: `[{"role": "user"|"assistant", "content": str}, ...]`, sem incluir
a pergunta atual.

DEPENDÊNCIA (TAI7-6, ainda em aberto): `_hybrid_retrieve` assume uma tabela
`chunks` já populada com os campos produzidos pelo format.py (TAI7-7) mais a
coluna de embedding. Contrato esperado:

    CREATE TABLE chunks (
        chunk_id     text PRIMARY KEY,   -- "<page_id>-<indice>"
        page_id      text,
        title        text,
        url          text,
        parent_id    text,
        ancestors    jsonb,
        breadcrumb   text,               -- "Ancestral > ... > Página"
        chunk_index  int,
        text         text,               -- texto do chunk (já com breadcrumb no topo)
        attachments  jsonb,
        embedding    vector(1536)        -- text-embedding-3-small, dim nativa
    );

    -- índice vetorial (similaridade de cosseno)
    CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);
    -- índice BM25 do ParadeDB (busca por palavra-chave de verdade)
    CREATE INDEX ON chunks USING bm25 (chunk_id, text) WITH (key_field='chunk_id');

Enquanto a TAI7-6 não subir esse schema + dados num ParadeDB rodando,
`_hybrid_retrieve`/`answer()` não têm o que consultar e `retrieve_and_format`
levanta erro de conexão/tabela inexistente. As partes que não tocam o banco
(reciprocal_rank_fusion, _format_context, e a sub-chain prompt|llm|parser
isolada com contexto/histórico sintéticos) já são exercitáveis hoje.
"""

from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_openai import ChatOpenAI
from openai import OpenAI
from psycopg.rows import dict_row

# Import irmão resiliente aos dois modos de execução do projeto: como pacote
# (`from core.db import ...`, caso do streamlit rodando com src/ no path) e como
# script solto (`python src/core/retrieve.py`, com src/core/ no path).
try:
    from core.db import get_connection
except ImportError:
    from db import get_connection

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")

EMBEDDING_MODEL = "text-embedding-3-small"
LLM_MODEL = "gpt-5.4-mini"

# Quantos candidatos cada busca (vetorial e BM25) devolve antes da fusão, e
# quantos chunks de contexto sobram no top-k final que vai pro prompt.
TOP_K_EACH = 20
TOP_K_FINAL = 5
# Constante do Reciprocal Rank Fusion. 60 é o valor clássico do paper
# (Cormack et al., 2009): amortece o peso das primeiras posições sem deixar a
# cauda dominar. Vale ajustar depois de medir com perguntas reais (passo 8).
RRF_K = 60

_SYSTEM_PROMPT = (
    "Você é o Bobby Sensei, assistente que responde dúvidas usando a "
    "documentação interna da empresa. Responda em português, de forma direta, "
    "usando SOMENTE as informações do contexto fornecido. Se o contexto não "
    "for suficiente para responder, diga que não encontrou a informação na "
    "documentação — não invente. Quando útil, cite a página de origem."
)


def _openai_client() -> OpenAI:
    """Cliente OpenAI cru (lê OPENAI_API_KEY do ambiente/.env), usado só para
    embeddings — a chamada ao LLM passa pela chain LCEL (ChatOpenAI), não por
    aqui."""
    return OpenAI()


# --------------------------------------------------------------------------- #
# Passo 0 — embedding da pergunta
# --------------------------------------------------------------------------- #
def embed_query(question: str) -> list[float]:
    """Gera o embedding da pergunta com o MESMO modelo usado nos chunks
    (text-embedding-3-small), pré-requisito pra comparar no mesmo espaço vetorial."""
    response = _openai_client().embeddings.create(
        model=EMBEDDING_MODEL,
        input=question,
    )
    return response.data[0].embedding


def _vector_literal(embedding: list[float]) -> str:
    """Serializa o vetor no formato textual que o pgvector aceita: '[a,b,c]'.
    Evita depender do pacote pgvector-python; o cast ::vector é feito na query."""
    return "[" + ",".join(repr(x) for x in embedding) + "]"


# --------------------------------------------------------------------------- #
# Passo 1 — busca vetorial (similaridade de cosseno via pgvector)
# --------------------------------------------------------------------------- #
def vector_search(conn, query_embedding: list[float], limit: int = TOP_K_EACH) -> list[dict]:
    """Top-k chunks mais próximos da pergunta no espaço vetorial.

    Usa o operador de distância de cosseno do pgvector (`<=>`); a similaridade
    (1 - distância) vai junto só como informação/depuração — quem ranqueia de
    fato na fusão é a POSIÇÃO na lista, não o score bruto (ver RRF)."""
    sql = """
        SELECT chunk_id, page_id, title, url, breadcrumb, text,
               1 - (embedding <=> %(vec)s::vector) AS score
        FROM chunks
        ORDER BY embedding <=> %(vec)s::vector
        LIMIT %(limit)s
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, {"vec": _vector_literal(query_embedding), "limit": limit})
        return cur.fetchall()


# --------------------------------------------------------------------------- #
# Passo 2 — busca BM25 (palavra-chave via ParadeDB / pg_search)
# --------------------------------------------------------------------------- #
def bm25_search(conn, query_text: str, limit: int = TOP_K_EACH) -> list[dict]:
    """Top-k chunks por relevância BM25 (palavra-chave), usando o índice bm25
    do ParadeDB. Complementa a busca vetorial: pega correspondência exata de
    termos (siglas, nomes de sistema) que a similaridade semântica às vezes perde.

    Obs.: operador `@@@` e função `paradedb.score()` seguem a API do pg_search;
    confirmar contra a versão fixada do ParadeDB quando a TAI7-6 subir o banco."""
    sql = """
        SELECT chunk_id, page_id, title, url, breadcrumb, text,
               paradedb.score(chunk_id) AS score
        FROM chunks
        WHERE text @@@ %(q)s
        ORDER BY score DESC
        LIMIT %(limit)s
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, {"q": query_text, "limit": limit})
        return cur.fetchall()


# --------------------------------------------------------------------------- #
# Passo 3 — fusão das duas listas (Reciprocal Rank Fusion)
# --------------------------------------------------------------------------- #
def reciprocal_rank_fusion(
    result_lists: list[list[dict]],
    k: int = RRF_K,
    top_k: int = TOP_K_FINAL,
) -> list[dict]:
    """Combina várias listas ranqueadas num ranking único pelo RRF.

    Cada chunk soma 1/(k + posição) por lista em que aparece (posição 1-based).
    O RRF ignora a escala dos scores (cosseno e BM25 não são comparáveis
    diretamente) e olha só a ordem — por isso funde bem buscas heterogêneas.
    Um chunk que aparece bem colocado nas DUAS listas sobe mais que um campeão
    isolado de uma só."""
    scores: dict[str, float] = {}
    payload: dict[str, dict] = {}

    for results in result_lists:
        for position, row in enumerate(results, start=1):
            cid = row["chunk_id"]
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + position)
            payload.setdefault(cid, row)

    ranked_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)

    fused: list[dict] = []
    for cid in ranked_ids[:top_k]:
        row = dict(payload[cid])
        row["rrf_score"] = scores[cid]
        fused.append(row)
    return fused


# --------------------------------------------------------------------------- #
# Passo 4 — retriever híbrido, encapsulado como Runnable da chain
# --------------------------------------------------------------------------- #
def _hybrid_retrieve(inputs: dict) -> list[dict]:
    """inputs: {"pergunta": str, ...}. Roda embed_query + vector_search +
    bm25_search + RRF (psycopg cru) e devolve os chunks top-k. É a peça que a
    chain LCEL injeta via RunnableLambda — LangChain não tem retriever pronto
    pra ParadeDB/pg_search híbrido, então essa lógica continua sendo nossa."""
    pergunta = inputs["pergunta"]
    query_embedding = embed_query(pergunta)
    with get_connection() as conn:
        vector_hits = vector_search(conn, query_embedding)
        bm25_hits = bm25_search(conn, pergunta)
    return reciprocal_rank_fusion([vector_hits, bm25_hits], top_k=TOP_K_FINAL)


def _format_context(chunks: list[dict]) -> str:
    """Formata os chunks recuperados em texto numerado com fonte, pra
    injetar no prompt. Cada chunk entra com sua trilha (breadcrumb) e URL,
    pra o modelo poder ancorar a resposta e citar a fonte."""
    if not chunks:
        return "(nenhum trecho relevante encontrado na documentação)"

    blocos = []
    for i, c in enumerate(chunks, start=1):
        fonte = c.get("breadcrumb") or c.get("title") or "documento"
        url = c.get("url", "")
        blocos.append(f"[{i}] {fonte}\n{c['text']}\nFonte: {url}")
    return "\n\n---\n\n".join(blocos)


def _retrieve_and_format(inputs: dict) -> str:
    """Combina retrieval + formatação num único passo da chain (RunnableLambda)."""
    chunks = _hybrid_retrieve(inputs)
    return _format_context(chunks)


# --------------------------------------------------------------------------- #
# Passo 5 — prompt template (contexto recuperado + histórico + pergunta)
# --------------------------------------------------------------------------- #
def _to_lc_messages(historico: list[dict]) -> list[BaseMessage]:
    """Converte o histórico no formato do Streamlit
    ([{"role": "user"|"assistant", "content": str}]) para mensagens LangChain,
    consumidas pelo MessagesPlaceholder do prompt."""
    convertidas: list[BaseMessage] = []
    for m in historico:
        if m["role"] == "user":
            convertidas.append(HumanMessage(content=m["content"]))
        elif m["role"] == "assistant":
            convertidas.append(AIMessage(content=m["content"]))
        # outros roles (ex.: "system") são ignorados de propósito — o system
        # prompt do Bobby Sensei é fixo, definido só no template abaixo.
    return convertidas


_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", _SYSTEM_PROMPT),
        MessagesPlaceholder("historico"),
        ("human", "Contexto extraído da documentação:\n\n{contexto}\n\nPergunta: {pergunta}"),
    ]
)


# --------------------------------------------------------------------------- #
# Passos 6 e 7 — chain LCEL (retrieval -> prompt -> GPT-5.4 mini -> resposta)
# e função pública única que a TAI7-9 consome
# --------------------------------------------------------------------------- #
_llm = ChatOpenAI(model=LLM_MODEL)

rag_chain = (
    RunnablePassthrough.assign(contexto=RunnableLambda(_retrieve_and_format))
    | _prompt
    | _llm
    | StrOutputParser()
)


def answer(pergunta: str, historico: list[dict] | None = None) -> str:
    """Ponto de entrada único do RAG híbrido, consumido pela TAI7-9.

    `historico` é uma lista de dicts {"role": "user"|"assistant", "content": str}
    (mesmo formato de st.session_state.messages no Streamlit), sem incluir a
    pergunta atual. Retorna a resposta em texto puro.

    (Requer a TAI7-6 pronta: tabela `chunks` populada num ParadeDB rodando.)
    """
    return rag_chain.invoke(
        {
            "pergunta": pergunta,
            "historico": _to_lc_messages(historico or []),
        }
    )


if __name__ == "__main__":
    historico: list[dict] = []
    while True:
        pergunta = input("Pergunta (Enter para sair): ").strip()
        if not pergunta:
            break
        resposta = answer(pergunta, historico)
        print(f"\n{resposta}\n")
        historico.append({"role": "user", "content": pergunta})
        historico.append({"role": "assistant", "content": resposta})
