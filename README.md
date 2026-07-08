# Bobby Sensei

Assistente RAG sobre o Confluence da Bobby — Time 7 (Automações e IA).

## Stack

| Camada | Ferramenta |
|---|---|
| Linguagem | Python 3.12 |
| Extração | API do Confluence |
| Formatação | BeautifulSoup |
| Orquestração RAG | LangChain |
| Embedding | OpenAI `text-embedding-3-small` (1536 dim) |
| LLM | GPT-4o mini (OpenAI) |
| Banco vetorial | Postgres + ParadeDB (`pgvector` + `pg_search`) |
| Interface | Streamlit |

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

Aguarde o banco ficar saudável (healthcheck) e o Streamlit iniciar.

### 4. Acesse a aplicação

Abra http://localhost:8501 no navegador.

## Estrutura do projeto

```
bobby-sensei/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── db/
│   └── init.sql        # habilita vector e pg_search no banco
└── src/
    ├── app.py          # Streamlit: só UI, chama core/
    └── core/           # lógica de RAG (sem import streamlit)
        ├── __init__.py
        ├── db.py        # conexão Postgres/ParadeDB
        ├── extract.py   # TAI7-5: extração Confluence
        ├── format.py    # TAI7-7: chunking/formatação
        ├── embed.py     # TAI7-6: geração de embeddings
        └── retrieve.py  # TAI7-8: recuperação híbrida
```

## Comandos úteis

```bash
# Subir em background
docker compose up -d --build

# Ver logs
docker compose logs -f app
docker compose logs -f db

# Verificar extensões no banco
docker exec -it sensei-db psql -U sensei -d sensei -c '\dx'

# Parar e remover containers (mantém volume)
docker compose down

# Parar e apagar dados do banco (volume zerado)
docker compose down -v
```

> **Atenção:** `docker compose down -v` apaga todos os dados do banco local.
