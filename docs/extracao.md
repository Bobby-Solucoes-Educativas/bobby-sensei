# Extração do Confluence (TAI7-5)

O `src/core/extract.py` extrai todas as páginas de um espaço do Confluence e
gera os arquivos brutos que alimentam a etapa de formatação (TAI7-7).

## Como rodar

Com o venv local (requer as credenciais `CONFLUENCE_*` no `.env`):

```bash
python src/core/extract.py
```

Ou via Docker (o volume `./data:/app/data` do compose persiste o resultado no host):

```bash
docker compose run --rm app python src/core/extract.py
```

O espaço e o tamanho dos lotes são constantes no topo do script
(`SPACE = "BE"`, `PAGE_SIZE = 50`).

## Saída

```
data/
└── raw/
    ├── index.json        # mapa do espaço (gerado ao final)
    ├── 768638988.json    # uma página por arquivo, nomeado pelo id
    ├── ...
    └── attachments/
        └── 768638988/    # anexos baixados, agrupados pelo id da página
            └── att818774034_central.sql
```

- Tudo em **UTF-8**, com acentos e emojis literais (`ensure_ascii=False`).
- Re-executar **sobrescreve** os arquivos e regenera o index — a pasta sempre
  reflete a última extração completa.
- Anexos já baixados (mesmo tamanho em bytes) **não são re-baixados** nas
  rodadas seguintes — só o que é novo ou mudou.
- **Vídeos e binários sem tipo (`octet-stream`) não são baixados**
  (`SKIP_DOWNLOAD_MEDIA` no `extract.py`) — vídeo a pipeline RAG não
  processa, e os octet-stream do espaço são dumps de banco (sem valor
  documentacional e com dados sensíveis). Os metadados são mantidos.


## Contrato: `{id}.json` (uma página)

Os comentários `//` abaixo são só ilustrativos — os arquivos reais são JSON puro.

```jsonc
{
  "id": "768638988",                  // id da página no Confluence (= nome do arquivo)
  "title": "📦 Docker - Ambiente de Desenvolvimento e Testes",
  "status": "current",                // sempre "current" (a extração filtra por esse status)
  "url": "https://bobbysolucoes.atlassian.net/wiki/spaces/BE/pages/768638988/...",

  "version": {
    "number": 16,                     // nº da versão — cresce a cada edição da página
    "when": "2024-06-19T18:51:13.968Z",  // timestamp ISO da última edição
    "by": "Arthur Novaes"             // quem editou por último (pode ser null)
  },

  "parent_id": "1372913666",          // id da página mãe (null só na raiz do espaço)
  "ancestors": [                      // trilha da raiz até a mãe — útil como breadcrumb dos chunks
    { "id": "827261173", "title": "Bobby Educ Home" },
    { "id": "853508127", "title": "💻Documentação técnica - Educ" },
    { "id": "1372913666", "title": "Comece por aqui" }
  ],

  // corpo em XHTML no formato storage do Confluence (contém macros ac:/ri:)
  "body_storage": "<h2>➡️Passo a passo</h2><p>...</p>",

  "attachments": [
    {
      "id": "att818774034",
      "title": "central.sql",
      "media_type": "application/octet-stream",  // MIME type; pode ser null
      "file_size": 28612,                        // em bytes
      "download_url": "https://bobbysolucoes.atlassian.net/wiki/rest/api/content/...",
      // ^ exige autenticação (e-mail + API token da Atlassian) — não funciona anônima
      "file": "attachments/768638988/att818774034_central.sql"
      // ^ binário baixado, caminho relativo a data/raw/
      //   (null se o download falhou ou o tipo é ignorado, ex.: vídeo)
    }
  ],

  "extracted_at": "2026-07-09T09:12:00+00:00"  // quando a página foi extraída (UTC)
}
```

## Contrato: `index.json`

Mapa do espaço, gerado uma única vez ao final da extração:

```jsonc
{
  "space": "BE",                              // chave do espaço extraído
  "generated_at": "2026-07-09T09:12:05+00:00",  // timestamp ISO (UTC) da geração
  "page_count": 393,                          // total de páginas extraídas
  "pages": [                                  // uma entrada por página
    {
      "id": "768638988",
      "file": "768638988.json",               // arquivo correspondente em data/raw/
      "title": "📦 Docker - Ambiente de Desenvolvimento e Testes",
      "version": 16,
      "updated_at": "2024-06-19T18:51:13.968Z",
      "parent_id": "1372913666",
      "attachment_count": 4
    }
  ]
}
```

Use o index para navegar o corpus sem abrir os arquivos individuais: descobrir
o que existe, reconstruir a hierarquia via `parent_id` e comparar `version`
com uma extração anterior para saber o que mudou.

## Observações para a formatação (TAI7-7)

- O `body_storage` é a fonte de conteúdo; é XHTML, então parsear com
  BeautifulSoup/lxml. Macros do Confluence aparecem como tags `ac:*`/`ri:*`.
- Páginas com `body_storage` vazio existem (ex.: páginas-organizadoras em
  construção) — trate como corpus vazio, não como erro.
- A trilha `ancestors` permite prefixar chunks com o caminho da página
  (ex.: `Bobby Educ > Regras de negócio > ...`), o que melhora a recuperação
  de chunks cujo título é genérico.
