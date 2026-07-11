# TAI7-7: formatação/chunking do conteúdo extraído (BeautifulSoup)
import json
import re
from pathlib import Path
from typing import Iterator

from bs4 import BeautifulSoup
from langchain_text_splitters import RecursiveCharacterTextSplitter

ROOT_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT_DIR / "data" / "raw"
PROCESSED_DIR = ROOT_DIR / "data" / "processed"
INDEX_PATH = RAW_DIR / "index.json"
CHUNKS_PATH = PROCESSED_DIR / "chunks.jsonl"

# Estratégia de chunking (documentada em docs/format.md):
# ~1000 caracteres com 150 de overlap. O splitter recursivo quebra
# preferindo parágrafos > linhas > frases, preservando o contexto local.
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150


def _iter_pages() -> Iterator[dict]:
    """Percorre as páginas listadas no index.json, na ordem em que foram extraídas."""

    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    for entry in index["pages"]:
        path = RAW_DIR / entry["file"]
        yield json.loads(path.read_text(encoding="utf-8"))


def _clean_soup(soup: BeautifulSoup) -> None:
    """Normaliza as macros do Confluence in-place, deixando só texto aproveitável.

    - blocos de código (`ac:name="code"`) viram o código puro entre cercas ```;
    - `ac:parameter` (config de macro, ex.: "wide"/"760") é removido;
    - emoticons, menções a usuário (sem nome legível) e imagens são descartados.
    """

    # Código primeiro: substitui a macro inteira pelo conteúdo do plain-text-body
    # (o get_text da macro colaria os parâmetros no meio do código).
    for macro in soup.find_all("ac:structured-macro", {"ac:name": "code"}):
        body = macro.find("ac:plain-text-body")
        code = body.get_text() if body else ""
        macro.replace_with(f"\n```\n{code}\n```\n")

    # Tags puramente decorativas ou de layout, sem texto aproveitável para o RAG.
    for tag_name in ("ac:parameter", "ac:emoticon", "ri:user", "ac:image"):
        for tag in soup.find_all(tag_name):
            tag.replace_with("")


def _to_text(body_storage: str) -> str:
    """Converte o XHTML storage do Confluence em texto limpo, sem tags residuais."""

    soup = BeautifulSoup(body_storage, "html.parser")
    _clean_soup(soup)
    text = soup.get_text(separator="\n")
    # Colapsa espaços/linhas em branco excessivos deixados pela remoção de tags.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _breadcrumb(page: dict) -> str:
    """Trilha 'Ancestral > ... > Página', usada como contexto no topo do chunk."""

    parts = [a["title"] for a in page.get("ancestors", []) if a.get("title")]
    parts.append(page["title"])
    return " > ".join(parts)


def _attachment_refs(page: dict) -> list[dict]:
    """Referência compacta aos anexos da página (metadado — não processa o binário).

    Todos os chunks da mesma página carregam a mesma lista: liga o chunk aos
    anexos da fonte sem esta etapa precisar abrir/interpretar os arquivos.
    """

    refs = []
    for att in page.get("attachments", []):
        raw_file = att.get("file")
        refs.append(
            {
                "id": att.get("id"),
                "title": att.get("title"),
                "media_type": att.get("media_type"),
                # Caminho completo (a partir da raiz do projeto, com barras "/")
                # do arquivo já baixado pela extração. null quando o anexo não
                # foi baixado (ex.: vídeo/binário pulado na extração).
                "file": _local_path(raw_file),
            }
        )
    return refs


def _local_path(raw_file: str | None) -> str | None:
    """Converte o `file` da extração (relativo a data/raw/, barras Windows) num
    caminho resolvível a partir da raiz do projeto, com barras "/"."""

    if not raw_file:
        return None
    return "data/raw/" + raw_file.replace("\\", "/")


def _chunk_page(page: dict, splitter: RecursiveCharacterTextSplitter) -> list[dict]:
    """Formata e quebra uma página em chunks, cada um com referência à origem."""

    text = _to_text(page.get("body_storage", ""))
    if not text:
        return []

    breadcrumb = _breadcrumb(page)
    attachments = _attachment_refs(page)
    # Hierarquia da página (vem da extração): id da mãe + trilha de ancestrais.
    # Permite reconstruir a árvore do espaço e navegar pais/filhos a partir do chunk.
    parent_id = page.get("parent_id")
    ancestors = page.get("ancestors", [])

    records: list[dict] = []
    for chunk in splitter.split_text(text):
        chunk = chunk.strip()
        if not chunk:
            continue
        records.append(
            {
                "chunk_id": f"{page['id']}-{len(records)}",
                "page_id": page["id"],
                "title": page["title"],
                "url": page["url"],
                "parent_id": parent_id,
                "ancestors": ancestors,
                "breadcrumb": breadcrumb,
                "chunk_index": len(records),
                # Prefixa a trilha no texto para ancorar chunks de título genérico
                # na recuperação (recomendação da doc de extração).
                "text": f"{breadcrumb}\n\n{chunk}",
                # Anexos da página de origem (referência; o binário não é lido aqui).
                "attachments": attachments,
            }
        )
    return records


def format_corpus() -> Path:
    """Orquestra: raw/{id}.json -> chunks limpos -> data/processed/chunks.jsonl."""

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    page_count = 0
    chunk_count = 0
    with open(CHUNKS_PATH, "w", encoding="utf-8") as out:
        for page in _iter_pages():
            records = _chunk_page(page, splitter)
            if records:
                page_count += 1
            for record in records:
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                chunk_count += 1

    print(
        f"Concluído: {chunk_count} chunks de {page_count} páginas com conteúdo "
        f"em {CHUNKS_PATH.relative_to(ROOT_DIR)}"
    )
    return CHUNKS_PATH


if __name__ == "__main__":
    format_corpus()
