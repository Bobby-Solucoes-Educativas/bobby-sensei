# Formatação/chunking do conteúdo extraído (TAI7-7)

O `src/core/format.py` lê os arquivos brutos gerados pela extração (TAI7-5,
`data/raw/*.json`), limpa o XHTML do Confluence e quebra o texto em chunks
prontos para a etapa de embeddings (TAI7-6).

## Como rodar

Com o venv local (requer `data/raw/index.json` já existir, ou seja, a
extração — TAI7-5 — já ter rodado):

```bash
python src/core/format.py
```

Ou via Docker:

```bash
docker compose run --rm app python src/core/format.py
```

## Estratégia de chunking

- **Tamanho**: ~1000 caracteres, com **150 de overlap** entre chunks
  consecutivos da mesma página (`CHUNK_SIZE`/`CHUNK_OVERLAP` no topo do
  script).
- **Splitter**: `RecursiveCharacterTextSplitter` (langchain-text-splitters),
  com separadores `["\n\n", "\n", ". ", " ", ""]` — tenta cortar em quebra de
  parágrafo primeiro, depois linha, depois frase, só cortando no meio de uma
  palavra em último caso. Preserva mais contexto local que um corte por
  caractere cru.
- **Limpeza do XHTML** (`_clean_soup`): blocos de código (macro
  `ac:structured-macro[ac:name=code]`) viram cercas de código puro (```` ``` ````);
  parâmetros de macro (`ac:parameter`), emoticons (`ac:emoticon`) e menções de
  usuário (`ri:user`) são removidos por não terem texto aproveitável para o RAG.
- **Imagem não vira chunk/embedding próprio** (decisão de 2026-07-08,
  TAI7-6/TAI7-7): a tag `ac:image` é descartada do texto — a imagem só existe
  como metadado de anexo (ver `attachments` no contrato abaixo), nunca como
  conteúdo embedado isoladamente.
- **Breadcrumb prefixado no texto**: cada chunk começa com a trilha
  `Ancestral > ... > Página` antes do conteúdo real. Isso ancora chunks cujo
  título é genérico (ex.: uma seção "Passo a passo" que existe em várias
  páginas) na hora da recuperação.

## Saída

```
data/
└── processed/
    └── chunks.jsonl   # um chunk por linha (JSON Lines)
```

`chunks.jsonl` é regenerado do zero a cada execução (sobrescreve o arquivo
anterior) — a pasta sempre reflete o último corpus bruto processado.

## Contrato: uma linha de `chunks.jsonl`

Os comentários `//` abaixo são só ilustrativos — cada linha do arquivo real é
um JSON puro, sem quebras internas.

```jsonc
{
  "chunk_id": "768638988-0",          // "<page_id>-<indice>", estável entre execuções
  "page_id": "768638988",             // id da página de origem no Confluence
  "title": "📦 Docker - Ambiente de Desenvolvimento e Testes",
  "url": "https://bobbysolucoes.atlassian.net/wiki/spaces/BE/pages/768638988/...",

  "parent_id": "1372913666",          // vem direto da extração (TAI7-5)
  "ancestors": [                      // idem — trilha da raiz até a mãe
    { "id": "827261173", "title": "Bobby Educ Home" },
    { "id": "853508127", "title": "💻Documentação técnica - Educ" }
  ],
  "breadcrumb": "Bobby Educ Home > 💻Documentação técnica - Educ > 📦 Docker - ...",

  "chunk_index": 0,                   // posição do chunk dentro da página (0-based)
  "text": "Bobby Educ Home > ...\n\nConteúdo limpo do chunk, já com o breadcrumb no topo.",

  "attachments": [                    // anexos da PÁGINA de origem (não só deste chunk)
    {
      "id": "att818774034",
      "title": "central.sql",
      "media_type": "application/octet-stream",
      "file": "data/raw/attachments/768638988/att818774034_central.sql"
      // ^ null se o binário não foi baixado na extração (ex.: vídeo/octet-stream)
    }
  ]
}
```

Observações sobre o contrato:
- `attachments` é a mesma lista para **todos** os chunks de uma página — liga
  cada chunk aos anexos da fonte sem precisar saber qual imagem "pertence" a
  qual trecho específico do texto.
- Páginas com `body_storage` vazio (ver `docs/extracao.md`) geram **zero**
  chunks — não é erro, só não entra no `chunks.jsonl`.

## Observações para a próxima etapa (embeddings/retrieval — TAI7-6/TAI7-8)

- O campo usado para gerar o embedding deve ser `text` (já inclui o
  breadcrumb) — não `title` isoladamente.
- `chunk_id` é a chave natural para a tabela `chunks` no ParadeDB (ver
  `docs/retrieve.md` para o schema esperado pela TAI7-8).
- `attachments[].file` é um caminho relativo à raiz do projeto — útil para a
  interface (TAI7-9) exibir a imagem/anexo junto da resposta, sem essa etapa
  precisar interpretar o binário.
