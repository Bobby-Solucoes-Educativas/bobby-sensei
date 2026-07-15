import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

_DATABASE_URL = os.environ["DATABASE_URL"]

_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS chunks (
        chunk_id     text PRIMARY KEY,
        page_id      text NOT NULL,
        title        text NOT NULL,
        url          text NOT NULL,
        parent_id    text,
        breadcrumb   text NOT NULL,
        chunk_index  int  NOT NULL,
        text         text NOT NULL,
        ancestors    jsonb NOT NULL DEFAULT '[]',
        attachments  jsonb NOT NULL DEFAULT '[]',
        embedding    vector(1536) NOT NULL,
        embedded_at  timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS chunks_embedding_idx
        ON chunks USING hnsw (embedding vector_cosine_ops)
    """,
    """
    CREATE INDEX IF NOT EXISTS chunks_bm25_idx
        ON chunks USING bm25 (chunk_id, title, text)
        WITH (key_field = 'chunk_id')
    """,
    """
    CREATE INDEX IF NOT EXISTS chunks_page_id_idx ON chunks (page_id)
    """,
)


def get_connection() -> psycopg.Connection:
    return psycopg.connect(_DATABASE_URL)

def ensure_schema() -> None:
    """Cria a tabela de chunks e os índices, se ainda não existirem."""
    
    with get_connection() as conn:
        for statement in _SCHEMA_STATEMENTS:
            conn.execute(statement)
