# TAI7-6: geração de embeddings via OpenAI text-embedding-3-small (1536 dim)
import json
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from psycopg.types.json import Jsonb

from core import db

ROOT_DIR = Path(__file__).resolve().parents[2]
CHUNKS_PATH = ROOT_DIR / "data" / "processed" / "chunks.jsonl"


EMBEDDING_MODEL = "text-embedding-3-small"
# Textos por chamada à API (limite: 2048 entradas / ~300k tokens por request).
BATCH_SIZE = 512

load_dotenv(ROOT_DIR / ".env")


def _read_chunks() -> list[dict]:
    """Lê o chunks.jsonl produzido pela formatação, um chunk por linha."""

    chunks = []
    with open(CHUNKS_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    return chunks


def _embed_all(client: OpenAI, texts: list[str]) -> list[list[float]]:
    """Gera os embeddings em lotes; a ordem da saída espelha a da entrada."""

    embeddings: list[list[float]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        resp = client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
        embeddings.extend(item.embedding for item in resp.data)
        print(f"{len(embeddings)}/{len(texts)} embeddings gerados...")
    return embeddings


def _load(chunks: list[dict], embeddings: list[list[float]]) -> None:
    """Recarrega a tabela chunks numa transação única: ou tudo, ou nada.

    TRUNCATE + INSERT casa com o pipeline diário que regenera o corpus
    inteiro — não sobram chunks órfãos de páginas removidas/encolhidas.
    Se algo falhar no meio, o rollback preserva a carga anterior.
    """

    rows = [
        (
            c["chunk_id"],
            c["page_id"],
            c["title"],
            c["url"],
            c["parent_id"],
            c["breadcrumb"],
            c["chunk_index"],
            c["text"],
            Jsonb(c["ancestors"]),
            Jsonb(c["attachments"]),
            json.dumps(embedding),
        )
        for c, embedding in zip(chunks, embeddings)
    ]

    with db.get_connection() as conn:
        conn.execute("TRUNCATE chunks")
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO chunks (chunk_id, page_id, title, url, parent_id,
                                    breadcrumb, chunk_index, text, ancestors,
                                    attachments, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
                """,
                rows,
            )


def main() -> None:
    # Garante schema (e valida a conexão) antes de gastar chamadas na OpenAI.
    db.ensure_schema()

    chunks = _read_chunks()
    if not chunks:
        raise SystemExit(f"Nenhum chunk em {CHUNKS_PATH} — rode o format.py antes.")
    print(f"{len(chunks)} chunks lidos de {CHUNKS_PATH.name}")

    client = OpenAI()
    embeddings = _embed_all(client, [c["text"] for c in chunks])

    _load(chunks, embeddings)
    print(f"Concluído: {len(chunks)} chunks embeddados e carregados na tabela chunks.")


if __name__ == "__main__":
    main()
