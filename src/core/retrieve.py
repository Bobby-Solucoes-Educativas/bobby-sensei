# TAI7-8: orquestração da chain RAG (LangChain) — retrieval híbrido (vetorial + BM25) + GPT-5.4 mini
"""Pipeline de retrieval híbrido + geração da resposta, orquestrado com LangChain (LCEL).

Fluxo (RAG híbrido, ponta a ponta):
    pergunta + histórico
      -> _condense_question (reescreve o acompanhamento como pergunta autônoma,
                             só para servir de query da busca)
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

    answer(pergunta: str, history: list[dict] | None = None) -> str

`history` são as mensagens anteriores da conversa — os mesmos objetos
`chat_state.Message` que a UI e a persistência (core/store.py) já usam, sem
inventar um formato paralelo. Não inclui a pergunta atual. Vira o
`history_context` do prompt, cortado para caber em
LIMIT_TOKENS_HISTORY_CONTEXT, a janela de contexto do histórico.

DADOS: `_hybrid_retrieve` consulta a tabela `chunks` populada pela TAI7-6
(`embed.py`) — schema e índices (HNSW vetorial + BM25 do ParadeDB) são criados
por `db.ensure_schema()`, ver `src/core/db.py` e `docs/embeddings.md`. O
pipeline foi validado ponta a ponta contra o banco real (2.289 chunks): as
duas buscas, a fusão RRF e a geração respondem com o contexto recuperado.
"""

from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, trim_messages
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
    from core.chat_state import Message
    from core.db import get_connection
except ImportError:
    from chat_state import Message
    from db import get_connection

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")

EMBEDDING_MODEL = "text-embedding-3-small"
LLM_MODEL = "gpt-5.4-mini"
# Controla o quão determinística é a resposta do LLM: mais baixa = mais
# consistente/previsível, mais alta = mais variação entre respostas pra
# mesma entrada. Sem este parâmetro, o padrão da API (~1.0) causava
# inconsistência real: a mesma pergunta de acompanhamento ("quero") ora
# respondia certo, ora recusava como "mensagem incompleta" (mesmo histórico,
# mesmo contexto recuperado) — ver testes A/B em retrieve com o prompt de
# acompanhamento. 0.0 elimina essa variância, adequado a um RAG factual que
# não busca criatividade.
LLM_TEMPERATURE = 0.0

# Quantos candidatos cada busca (vetorial e BM25) devolve antes da fusão, e
# quantos chunks de contexto sobram no top-k final que vai pro prompt.
TOP_K_EACH = 20
TOP_K_FINAL = 10
# Constante do Reciprocal Rank Fusion. 60 é o valor clássico do paper
# (Cormack et al., 2009): amortece o peso das primeiras posições sem deixar a
# cauda dominar. Vale ajustar depois de medir com perguntas reais (passo 8).
RRF_K = 60

# Janela de contexto do histórico: teto de tokens de conversa anterior que
# acompanha cada pergunta. Restringe SÓ o `history_context` — o contexto
# recuperado do RAG e o system prompt não passam por este limite.
#
# 1000 é um começo econômico: cabem ~2 trocas (pergunta + resposta) no padrão
# de resposta atual do bot, o suficiente para uma pergunta de acompanhamento
# ("quero", "e sobre isso?") enxergar o turno anterior. Para referência, o
# contexto do RAG sozinho (TOP_K_FINAL chunks) já gasta ~2.500 tokens, então
# esta janela é uma fração modesta do prompt. Subir o valor amplia a memória
# da conversa e o custo por pergunta na mesma proporção.
LIMIT_TOKENS_HISTORY_CONTEXT = 1000

_SYSTEM_PROMPT = (
    "Você é o Bobby Sensei, assistente que responde dúvidas usando a "
    "documentação interna da empresa. Responda em português, de forma direta, "
    "usando SOMENTE as informações do contexto fornecido. Se o contexto não "
    "for suficiente para responder, diga que não encontrou a informação na "
    "documentação — não invente. Quando útil, cite a página de origem. "
    # Sem esta parte o modelo às vezes trata um acompanhamento curto como
    # mensagem incompleta ("você escreveu apenas 'quero'"), mesmo com a
    # conversa no prompt e o contexto certo recuperado.
    "A conversa anterior faz parte do enunciado: quando a pergunta atual for "
    "curta ou apenas referenciar o que já foi dito (\"quero\", \"sim\", "
    "\"e isso?\", \"continua\"), interprete-a à luz da última resposta — "
    "inclusive quando ela estiver aceitando algo que você mesmo ofereceu. Não "
    "responda que a mensagem está incompleta se a conversa deixa claro o que "
    "foi pedido."
)


_llm = ChatOpenAI(model=LLM_MODEL, temperature=LLM_TEMPERATURE)


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

    Usa `paradedb.match('text', query_text)` em vez de `text @@@ query_text`
    direto. O operador `@@@` com uma string crua faz PARSE dela como consulta
    (sintaxe tipo Tantivy/Lucene: ":" separa campo:termo, parênteses agrupam,
    AND/OR/NOT são operadores booleanos) — qualquer pergunta com dois-pontos
    (ex.: "status: pendente") ou uma pergunta reescrita pela condensação
    (ver _condense_question) que caia nesse padrão quebra a query com
    psycopg.errors.InternalError_ em vez de simplesmente não achar nada.
    `paradedb.match()` trata o valor sempre como texto literal — mesmo score/
    ranking pra buscas normais (validado: mesmos chunk_id e score do `@@@`
    cru numa consulta sem sintaxe especial), mas sem essa fragilidade.

    Obs.: `paradedb.score()` segue a API do pg_search (validado com pg_search
    0.24.3). Busca só na coluna `text` — que já traz o breadcrumb (logo, o
    caminho/título da página) prefixado pelo format.py."""
    sql = """
        SELECT chunk_id, page_id, title, url, breadcrumb, text,
               paradedb.score(chunk_id) AS score
        FROM chunks
        WHERE chunk_id @@@ paradedb.match('text', %(q)s)
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
# Passo 3.5 — reescrita da pergunta para a busca (query condensation)
# --------------------------------------------------------------------------- #
# Teto de tamanho da pergunta reescrita. Se vier maior, o modelo provavelmente
# explicou em vez de reescrever — nesse caso a original é usada.
_MAX_CONDENSED_CHARS = 300

_CONDENSE_SYSTEM_PROMPT = (
    "Você reescreve perguntas de acompanhamento para busca em documentação. "
    "Dada a conversa anterior e a pergunta de acompanhamento, reescreva-a como "
    "uma pergunta AUTÔNOMA, que faça sentido sozinha, sem depender da conversa: "
    "resolva pronomes e referências implícitas (\"isso\", \"ele\", \"quero\") "
    "usando os termos concretos que aparecem na conversa. Se a pergunta já for "
    "autônoma, devolva-a inalterada. Responda APENAS com a pergunta reescrita, "
    "sem explicação, sem aspas e sem prefixo."
)

_condense_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", _CONDENSE_SYSTEM_PROMPT),
        MessagesPlaceholder("history_context"),
        ("human", "Pergunta de acompanhamento: {pergunta}"),
    ]
)

_condense_chain = _condense_prompt | _llm | StrOutputParser()


def _condense_question(pergunta: str, history_context: list[BaseMessage]) -> str:
    """Reescreve a pergunta como autônoma, para servir de query da busca.

    Sem isso, um acompanhamento como "quero" ou "e os filtros opcionais?" vira
    a query literal do embedding/BM25 e recupera a página errada — o modelo até
    entende a pergunta pelo histórico, mas recebe contexto irrelevante e recusa
    responder.

    O resultado alimenta SÓ a busca; o prompt de resposta continua recebendo a
    pergunta original do usuário. Sem histórico (1º turno) a pergunta já é
    autônoma e a chamada ao LLM é pulada. Qualquer falha cai na pergunta
    original — o pior caso é o comportamento anterior a esta etapa.
    """
    if not history_context:
        return pergunta

    try:
        reescrita = _condense_chain.invoke(
            {"pergunta": pergunta, "history_context": history_context}
        ).strip()
    except Exception:
        return pergunta

    if not reescrita or len(reescrita) > _MAX_CONDENSED_CHARS:
        return pergunta
    return reescrita


# --------------------------------------------------------------------------- #
# Passo 4 — retriever híbrido, encapsulado como Runnable da chain
# --------------------------------------------------------------------------- #
def _hybrid_retrieve(inputs: dict) -> list[dict]:
    """inputs: {"pergunta": str, "history_context": [...], ...}. Condensa a
    pergunta, roda embed_query + vector_search + bm25_search + RRF (psycopg
    cru) e devolve os chunks top-k. É a peça que a chain LCEL injeta via
    RunnableLambda — LangChain não tem retriever pronto pra ParadeDB/pg_search
    híbrido, então essa lógica continua sendo nossa.

    É o ponto único por onde passam os dois caminhos públicos (`answer` via
    rag_chain e `answer_with_chunks`), por isso a condensação mora aqui.
    """
    pergunta_busca = _condense_question(
        inputs["pergunta"], inputs.get("history_context") or []
    )
    query_embedding = embed_query(pergunta_busca)
    with get_connection() as conn:
        vector_hits = vector_search(conn, query_embedding)
        bm25_hits = bm25_search(conn, pergunta_busca)
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
def _to_lc_messages(history: list[Message]) -> list[BaseMessage]:
    """Converte as mensagens da conversa (chat_state.Message — o modelo comum
    do projeto, já usado pela UI e pela persistência) em mensagens LangChain,
    consumidas pelo MessagesPlaceholder do prompt."""
    convertidas: list[BaseMessage] = []
    for m in history:
        if m.role == "user":
            convertidas.append(HumanMessage(content=m.content))
        elif m.role == "assistant":
            convertidas.append(AIMessage(content=m.content))
        # outros roles são ignorados de propósito — o system prompt do Bobby
        # Sensei é fixo, definido só no template abaixo. Os demais campos do
        # Message (chunks, db_id, bot_respondeu) não interessam ao modelo.
    return convertidas


def _estimate_tokens(mensagens: list[BaseMessage]) -> int:
    """Estimativa de tokens de uma lista de mensagens, usada como régua da
    janela de contexto.

    É aproximação proposital (~4 caracteres por token em português, mais uma
    folga fixa por mensagem para role/delimitadores): o tiktoken não reconhece
    o `gpt-5.4-mini` (levanta KeyError), então qualquer contagem "exata" aqui
    seria o tokenizer de outro modelo fingindo precisão. Para um teto de
    orçamento, a aproximação basta — e evita uma dependência a mais.
    """
    return sum(len(m.content) // 4 + 4 for m in mensagens)


def build_history_context(history: list[Message] | None) -> list[BaseMessage]:
    """Monta o `history_context`: o histórico da conversa já convertido e
    cortado para caber em LIMIT_TOKENS_HISTORY_CONTEXT.

    Mantém as trocas mais recentes (`strategy="last"`) e começa sempre numa
    pergunta do usuário (`start_on="human"`), para o modelo não receber uma
    resposta órfã sem a pergunta que a originou. Se nem uma troca inteira
    couber no limite, o resultado é vazio — nesse caso vale subir a constante.
    """
    mensagens = _to_lc_messages(history or [])
    if not mensagens:
        return []

    return trim_messages(
        mensagens,
        max_tokens=LIMIT_TOKENS_HISTORY_CONTEXT,
        token_counter=_estimate_tokens,
        strategy="last",
        start_on="human",
        include_system=False,
        allow_partial=False,
    )


_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", _SYSTEM_PROMPT),
        MessagesPlaceholder("history_context"),
        ("human", "Contexto extraído da documentação:\n\n{contexto}\n\nPergunta: {pergunta}"),
    ]
)


# --------------------------------------------------------------------------- #
# Passos 6 e 7 — chain LCEL (retrieval -> prompt -> GPT-5.4 mini -> resposta)
# e função pública única que a TAI7-9 consome
# --------------------------------------------------------------------------- #
rag_chain = (
    RunnablePassthrough.assign(contexto=RunnableLambda(_retrieve_and_format))
    | _prompt
    | _llm
    | StrOutputParser()
)


def answer(pergunta: str, history: list[Message] | None = None) -> str:
    """Ponto de entrada único do RAG híbrido, consumido pela TAI7-9.

    `history` são as mensagens anteriores da conversa (chat_state.Message),
    sem incluir a pergunta atual. Ele vira o `history_context` do prompt,
    limitado a
    LIMIT_TOKENS_HISTORY_CONTEXT. Retorna a resposta em texto puro.

    (Requer a TAI7-6 pronta: tabela `chunks` populada num ParadeDB rodando.)
    """
    return rag_chain.invoke(
        {
            "pergunta": pergunta,
            "history_context": build_history_context(history),
        }
    )


_answer_chain = _prompt | _llm | StrOutputParser()


def answer_with_chunks(
    pergunta: str, history: list[Message] | None = None
) -> tuple[str, list[dict]]:
    """Como `answer()`, mas também devolve os chunks recuperados (pra exibir
    como fonte/anexo na UI). Roda o mesmo retrieval e a mesma chain de
    geração, só expondo o resultado intermediário do `_hybrid_retrieve`."""
    # Uma única montagem da janela: serve tanto para condensar a pergunta de
    # busca (dentro do _hybrid_retrieve) quanto para o prompt da resposta.
    history_context = build_history_context(history)
    chunks = _hybrid_retrieve(
        {"pergunta": pergunta, "history_context": history_context}
    )
    resposta = _answer_chain.invoke(
        {
            "pergunta": pergunta,
            "history_context": history_context,
            "contexto": _format_context(chunks),
        }
    )
    return resposta, chunks


if __name__ == "__main__":
    history: list[dict] = []
    while True:
        pergunta = input("Pergunta (Enter para sair): ").strip()
        if not pergunta:
            break
        resposta = answer(pergunta, history)
        print(f"\n{resposta}\n")
        history.append({"role": "user", "content": pergunta})
        history.append({"role": "assistant", "content": resposta})
