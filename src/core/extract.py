# TAI7-5: extração de páginas do Confluence via API
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from atlassian import Confluence
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT_DIR / "data" / "raw"
ATTACHMENTS_DIR = RAW_DIR / "attachments"

SPACE = "BE"
PAGE_SIZE = 50
# body.storage = XHTML bruto; children.attachment traz só o 1º lote de anexos
# (até 25) — quando vier cheio, o restante é buscado por chamada dedicada.
EXPAND = "body.storage,version,ancestors,children.attachment"
# Tipos de anexo que não são baixados (metadados são mantidos mesmo assim):
# vídeo não é processável pela pipeline RAG; octet-stream são binários sem
# tipo (na prática, dumps de banco — sem valor documentacional e com dados
# sensíveis de cliente).
SKIP_DOWNLOAD_MEDIA = ("video/", "application/octet-stream", "binary/")

load_dotenv(ROOT_DIR / ".env")



def _client() -> Confluence:
    """Cria o cliente autenticado do Confluence a partir das variáveis do .env."""

    base_url = os.getenv("CONFLUENCE_BASE_URL")
    email = os.getenv("CONFLUENCE_EMAIL")
    token = os.getenv("CONFLUENCE_API_TOKEN")
    if not (base_url and email and token):
        raise RuntimeError(
            "Credenciais do Confluence ausentes "
            "(CONFLUENCE_BASE_URL/EMAIL/API_TOKEN no .env)."
        )
    # No Confluence Cloud, a "senha" é o API token.
    return Confluence(url=base_url, username=email, password=token, cloud=True)



def _iter_batches(confluence: Confluence, space: str) -> Iterator[list[dict]]:
    """Percorre todas as páginas do espaço em lotes, escondendo a paginação."""

    start = 0
    while True:
        batch = confluence.get_all_pages_from_space(
            space=space,
            start=start,
            limit=PAGE_SIZE,
            status="current",
            expand=EXPAND,
        )
        if not batch:
            break
        yield batch
        if len(batch) < PAGE_SIZE:
            break
        start += PAGE_SIZE



def _normalize_attachment(att: dict, base_url: str) -> dict:
    """Reduz um anexo da API aos metadados úteis, com URL de download absoluta."""

    metadata = att.get("metadata", {})
    extensions = att.get("extensions", {})
    return {
        "id": att.get("id"),
        "title": att.get("title"),
        "media_type": metadata.get("mediaType") or extensions.get("mediaType"),
        "file_size": extensions.get("fileSize"),
        # O download exige autenticação (token da API), mesmo com URL absoluta.
        "download_url": base_url + att["_links"]["download"],
    }



def _download_attachment(confluence: Confluence, att: dict, page_id: str) -> str | None:
    """Baixa o anexo para data/raw/attachments/{page_id}/ e retorna o caminho relativo.

    Pula o download se o arquivo já existe com o tamanho esperado (rodadas
    diárias não re-baixam tudo). Retorna None se o download falhar ou o tipo
    estiver em SKIP_DOWNLOAD_MEDIA.
    """

    media_type = att["media_type"] or ""
    if media_type.startswith(SKIP_DOWNLOAD_MEDIA):
        return None

    safe_name = re.sub(r"[^\w.\-]+", "_", att["title"] or "").strip("_") or "sem_nome"
    dest = ATTACHMENTS_DIR / page_id / f"{att['id']}_{safe_name}"
    rel = str(dest.relative_to(RAW_DIR))

    if dest.exists() and dest.stat().st_size == att["file_size"]:
        return rel

    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        resp = confluence._session.get(att["download_url"], stream=True)
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=256 * 1024):
                f.write(chunk)
        return rel
    except Exception as exc:
        print(f"  aviso: falha ao baixar anexo {att['id']} ({att['title']}): {exc}")
        dest.unlink(missing_ok=True)
        return None


def _collect_attachments(
    confluence: Confluence, page: dict, base_url: str
) -> list[dict]:
    """Retorna todos os anexos da página, com os binários baixados.

    Usa os que vieram embutidos no expand; se o lote veio cheio (pode haver
    mais), busca a lista completa com chamadas dedicadas paginadas. Cada
    anexo é baixado e ganha o campo "file" com o caminho local relativo.
    """

    embedded = page.get("children", {}).get("attachment", {})
    results = embedded.get("results", [])
    if len(results) < embedded.get("limit", PAGE_SIZE):
        attachments = [_normalize_attachment(att, base_url) for att in results]
    else:
        attachments = []
        start = 0
        while True:
            resp = confluence.get_attachments_from_content(
                page_id=page["id"], start=start, limit=PAGE_SIZE
            )
            batch = resp.get("results", [])
            attachments.extend(_normalize_attachment(att, base_url) for att in batch)
            if len(batch) < PAGE_SIZE:
                break
            start += PAGE_SIZE

    for att in attachments:
        att["file"] = _download_attachment(confluence, att, page["id"])
    return attachments



def _save_page(page: dict, attachments: list[dict], base_url: str) -> dict:
    """Grava data/raw/{id}.json e retorna os metadados da página para o index."""

    ancestors = page.get("ancestors", [])
    version = page.get("version", {})
    record = {
        "id": page["id"],
        "title": page["title"],
        "status": page["status"],
        "url": base_url + page["_links"]["webui"],
        "version": {
            "number": version.get("number"),
            "when": version.get("when"),
            "by": version.get("by", {}).get("displayName"),
        },
        "parent_id": ancestors[-1]["id"] if ancestors else None,
        "ancestors": [
            {"id": a["id"], "title": a.get("title")} for a in ancestors
        ],
        "body_storage": page.get("body", {}).get("storage", {}).get("value", ""),
        "attachments": attachments,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
    }

    path = RAW_DIR / f"{record['id']}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    return {
        "id": record["id"],
        "file": path.name,
        "title": record["title"],
        "version": record["version"]["number"],
        "updated_at": record["version"]["when"],
        "parent_id": record["parent_id"],
        "attachment_count": len(attachments),
    }



def _write_index(entries: list[dict], space: str) -> Path:
    """Gera o data/raw/index.json de uma vez, ao final da extração."""

    index = {
        "space": space,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "page_count": len(entries),
        "pages": entries,
    }
    path = RAW_DIR / "index.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    return path



def extract_space(space: str = SPACE) -> None:
    """Orquestra a extração: lotes -> {id}.json por página -> index.json."""

    confluence = _client()
    base_url = os.environ["CONFLUENCE_BASE_URL"].rstrip("/")
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    entries: list[dict] = []
    for batch in _iter_batches(confluence, space):
        for page in batch:
            attachments = _collect_attachments(confluence, page, base_url)
            entries.append(_save_page(page, attachments, base_url))
        print(f"{len(entries)} páginas extraídas...")

    index_path = _write_index(entries, space)
    print(f"Concluído: {len(entries)} páginas em {RAW_DIR} (index: {index_path.name})")



if __name__ == "__main__":
    extract_space()
