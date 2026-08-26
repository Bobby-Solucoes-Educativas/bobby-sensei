# Bobby Sensei

Assistente RAG sobre o Confluence da Bobby — Time 7 (Automações e IA).

## Stack

| Camada           | Ferramenta                                     |
| ---------------- | ---------------------------------------------- |
| Linguagem        | Python 3.12                                    |
| Extração         | API do Confluence                              |
| Formatação       | BeautifulSoup                                  |
| Orquestração RAG | LangChain                                      |
| Embedding        | OpenAI `text-embedding-3-small` (1536 dim)     |
| LLM              | GPT-5.4 mini (OpenAI)                          |
| Banco vetorial   | Postgres + ParadeDB (`pgvector` + `pg_search`) |
| Interface        | Streamlit                                      |

## Como rodar

### Pré-requisitos

- [Docker](https://docs.docker.com/get-docker/) + [Docker Compose](https://docs.docker.com/compose/install/) instalados.

### 1. Clone o repositório

```bash
git clone git@github.com:BobbyBusiness/bobby-sensei.git
cd bobby-sensei
```

### 2. Configure as variáveis de ambiente

```bash
cp .env.example .env
```

Edite o `.env` e preencha:

- `OPENAI_API_KEY` — sua chave da OpenAI
- `CONFLUENCE_EMAIL` — seu e-mail Atlassian
- `CONFLUENCE_API_TOKEN` — token gerado em https://id.atlassian.com/manage-profile/security/api-tokens
- `POSTGRES_PASSWORD` — troque a senha padrão

### 3. Suba os serviços

```bash
docker compose up --build
```

Aguarde o banco ficar saudável (healthcheck) e o Streamlit iniciar. Na
inicialização, a app aplica as migrations pendentes em `db/migrations/`
(ver [Schema do banco](#schema-do-banco)).

### 4. Acesse a aplicação

Abra http://localhost:8501 no navegador.

## Schema do banco

O schema fica em `db/migrations/`, com um arquivo `.sql` numerado por
alteração. `ensure_schema()` (`src/core/db.py`) roda no startup da app, aplica
as migrations que ainda não foram executadas naquele banco e registra cada uma
na tabela `schema_migrations`.

Cada migration roda na própria transação, e o runner usa um advisory lock —
duas instâncias subindo ao mesmo tempo não aplicam a mesma migration duas
vezes.

`db/init.sql` habilita as extensões `vector` e `pg_search` no bootstrap do
volume (primeiro `up`) e é embutido na imagem de produção pelo `Dockerfile.db`.
Não é onde se altera o schema.

### Alterando o schema

1. Crie um arquivo novo, numerado: `db/migrations/0002_descricao.sql`.
2. Escreva `ALTER TABLE` / `CREATE INDEX` — **sem** `IF NOT EXISTS`. A
   migration precisa falhar alto se o estado do banco divergir do esperado.
3. Suba a app. O runner aplica o que estiver pendente.

**Nunca edite uma migration já aplicada.** O runner guarda o sha256 de cada
arquivo e recusa a subida se o conteúdo mudar — o banco não receberia a
alteração e o arquivo passaria a mentir sobre o schema real. Correção =
migration nova.

Para conferir o que já foi aplicado:

```bash
docker exec -it sensei-db psql -U sensei -d sensei -c 'SELECT * FROM schema_migrations'
```

## Extração do Confluence

Extrai as páginas do espaço `BE` para `data/raw/` (um `{id}.json` por página + `index.json`). Requer as credenciais `CONFLUENCE_*` no `.env`.

```bash
# com o venv local
python src/core/extract.py

# ou via Docker
docker compose run --rm app python src/core/extract.py
```

O formato dos arquivos gerados está documentado em [docs/extracao.md](docs/extracao.md).

## Embeddings (banco vetorial)

Gera embeddings dos chunks formatados (`text-embedding-3-small`, 1536 dim) e
carrega na tabela `chunks` do ParadeDB, com índices HNSW (vetorial) e BM25:

```bash
# uma vez, no venv: instala o pacote core/
pip install -e .

# pipeline: extração -> formatação -> embeddings
python src/core/extract.py
python src/core/format.py
python src/core/embed.py
```

Detalhes do schema e das consultas em [docs/embeddings.md](docs/embeddings.md).

## Retrieval (chat RAG híbrido)

Recupera os chunks mais relevantes no banco (busca vetorial + BM25 combinadas
via Reciprocal Rank Fusion) e gera a resposta com o GPT-5.4 mini, orquestrado
como uma chain LangChain. Requer o banco populado (etapas acima) e
`OPENAI_API_KEY` no `.env`.

```bash
# teste manual interativo (loop de perguntas, com histórico da conversa)
python src/core/retrieve.py
```

A lógica é exposta pela função única `answer(pergunta, historico)`, consumida
pela interface (Streamlit). Detalhes da chain e do contrato em
[docs/retrieve.md](docs/retrieve.md).

## Feedback e dashboard

Histórico de conversas persistido no mesmo banco, com classificação 👍/👎 por
resposta e uma página de dashboard no próprio Streamlit
(`http://localhost:8501/Dashboard`). Detalhes em
[docs/feedback-dashboard.md](docs/feedback-dashboard.md).

## Estrutura do projeto

```
bobby-sensei/
├── docker-compose.yml       # ambiente local (build a partir do Dockerfile)
├── docker-compose.prod.yml  # produção (imagens publicadas no Docker Hub)
├── Dockerfile               # imagem da app
├── Dockerfile.db            # imagem do banco (ParadeDB + init.sql)
├── requirements.txt
├── pyproject.toml           # torna os pacotes de src/ instaláveis (pip install -e .)
├── .env.example
├── .gitignore
├── .dockerignore
├── README.md
├── data/                    # gerada pela extração (fora do git)
│   └── raw/                 # {id}.json por página + index.json
├── db/
│   ├── init.sql             # extensões vector e pg_search (bootstrap do volume)
│   └── migrations/          # schema — um .sql numerado por alteração
│       └── 0001_initial_schema.sql
├── docs/
│   ├── extracao.md           # contrato dos dados brutos da extração
│   ├── format.md             # estratégia de chunking e contrato dos chunks
│   ├── embeddings.md         # schema da tabela chunks e consultas de referência
│   ├── retrieve.md           # chain RAG híbrida e contrato de answer()
│   ├── chat-ui.md            # interface de chat (Streamlit)
│   └── feedback-dashboard.md # feedback 👍/👎 e dashboard de validação
└── src/
    ├── app.py               # Streamlit: só UI, chama core/
    ├── icon/                # assets da interface
    ├── pages/               # páginas extras do Streamlit (Dashboard)
    ├── ui/                  # componentes de interface
    └── core/                # lógica de RAG (sem import streamlit)
        ├── __init__.py
        ├── db.py             # conexão Postgres/ParadeDB + runner de migrations
        ├── extract.py        # TAI7-5: extração Confluence
        ├── format.py         # TAI7-7: chunking/formatação
        ├── embed.py          # TAI7-6: geração de embeddings
        ├── retrieve.py       # TAI7-8: recuperação híbrida
        ├── chat_state.py     # estado das conversas
        ├── chatbot_core.py   # ponte entre a UI e o retrieval
        ├── persistence.py    # TAI7-12: gravação de conversas e feedback
        └── dashboard_data.py # TAI7-12: consultas do dashboard
```

## Comandos úteis

```bash
# Subir em background
docker compose up -d --build

# Povoar o Banco de dados
docker compose run --rm app sh -c "python src/core/extract.py && python src/core/format.py && python src/core/embed.py"

# Ver logs
docker compose logs -f app
docker compose logs -f db

# Verificar extensões no banco
docker exec -it sensei-db psql -U sensei -d sensei -c '\dx'

# Ver migrations aplicadas
docker exec -it sensei-db psql -U sensei -d sensei -c 'SELECT * FROM schema_migrations'

# Parar e remover containers (mantém volume)
docker compose down

# Parar e apagar dados do banco (volume zerado)
docker compose down -v
```

> **Atenção:** `docker compose down -v` apaga todos os dados do banco local.