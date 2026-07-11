# Formatação do conteúdo (TAI7-7)

O `src/core/format.py` transforma os arquivos brutos da extração (TAI7-5) em
chunks de texto limpo, prontos para a etapa de embeddings (TAI7-6).

## Critérios de aceite

- Texto extraído sai limpo, sem tags HTML residuais.
- Cada chunk mantém referência à página/fonte original.
- Estratégia de chunking documentada (tamanho e overlap definidos).

## Como rodar

Com o venv local (requer o output da extração em `data/raw/`):

```bash
python src/core/format.py
```

Ou via Docker:

```bash
docker compose run --rm app python src/core/format.py
```

## Entrada e saída

- **Entrada:** `data/raw/index.json` + os `{id}.json` por página (contrato em
  [extracao.md](extracao.md)). O conteúdo vem do campo `body_storage`, que é
  XHTML no formato *storage* do Confluence (contém macros `ac:*`/`ri:*`).
- **Saída:** `data/processed/chunks.jsonl` — um chunk por linha (JSON Lines,
  UTF-8, `ensure_ascii=False`).

Re-executar **sobrescreve** o arquivo — ele sempre reflete a última formatação.

## Limpeza do HTML

O corpo é parseado com BeautifulSoup (`html.parser`) e reduzido a texto puro:

- **Blocos de código** (`ac:structured-macro ac:name="code"`) são preservados
  entre cercas ``` ```, extraindo só o `ac:plain-text-body` (sem os parâmetros
  de layout da macro).
- **`ac:parameter`** (config de macro, ex.: `wide`/`760`) é removido.
- **Emoticons, menções a usuário (`ri:user`) e imagens (`ac:image`)** são
  descartados — nesta etapa não há tratamento do conteúdo de imagem/anexo.
- Entidades HTML (`&aacute;`, `&nbsp;`, …) são decodificadas para texto legível.
- Espaços e linhas em branco excessivos são colapsados.

O resultado é texto sem tags HTML residuais. `<...>` que sobrevivem são
conteúdo legítimo (exemplos dentro de blocos de código ou menções literais a
tags na prosa), não resíduo de parsing.

## Estratégia de chunking

| Parâmetro | Valor | Motivo |
|---|---|---|
| Tamanho (`chunk_size`) | **1000 caracteres** | Contexto suficiente por chunk sem diluir a relevância na recuperação. |
| Overlap (`chunk_overlap`) | **150 caracteres** | Preserva continuidade entre chunks vizinhos, evitando cortar ideias no meio. |
| Splitter | `RecursiveCharacterTextSplitter` (LangChain) | Quebra hierárquica: parágrafo → linha → frase → palavra. |
| Separadores | `["\n\n", "\n", ". ", " ", ""]` | Tenta cortar na maior unidade semântica possível primeiro. |

Os valores são constantes no topo do `format.py` (`CHUNK_SIZE`,
`CHUNK_OVERLAP`).

## Referência à página de origem e aos anexos

Cada chunk carrega os metadados que ligam o texto de volta à sua página, e a
trilha de navegação (`breadcrumb`) também é prefixada no próprio `text` para
ancorar chunks de título genérico na recuperação.

```jsonc
{
  "chunk_id": "768638988-0",       // {page_id}-{índice do chunk na página}
  "page_id": "768638988",          // id da página no Confluence
  "title": "📦 Docker - Ambiente de Desenvolvimento e Testes",
  "url": "https://bobbysolucoes.atlassian.net/wiki/spaces/BE/pages/768638988/...",
  "parent_id": "1372913666",       // id da página mãe (null na raiz do espaço)
  "ancestors": [                   // trilha da raiz até a mãe (id + título)
    { "id": "827261173", "title": "Bobby Educ Home" },
    { "id": "1372913666", "title": "Comece por aqui" }
  ],
  "breadcrumb": "Bobby Educ Home > Documentação técnica > Comece por aqui > Docker",
  "chunk_index": 0,                // posição do chunk dentro da página (0-based)
  "text": "Bobby Educ Home > ... > Docker\n\n<conteúdo limpo do chunk>",

  // anexos da página de origem — referência apenas; esta etapa não abre nem
  // interpreta os binários. Todos os chunks da mesma página repetem a lista.
  "attachments": [
    {
      "id": "att818774034",
      "title": "central.sql",
      "media_type": "application/octet-stream",  // pode ser null
      "file": "data/raw/attachments/768638988/att818774034_central.sql"  // caminho a partir da raiz do projeto; null se não baixado
    }
  ]
}
```

- Páginas com `body_storage` vazio (páginas-organizadoras) são **puladas sem
  erro** — não geram chunk.
- O `chunk_id` é único e estável enquanto a página não muda de conteúdo.
- A lista `attachments` vem direto dos metadados da extração (contrato em
  [extracao.md](extracao.md)) — é uma referência à fonte, sem processar o
  conteúdo dos arquivos. Páginas sem anexo têm a lista vazia.
