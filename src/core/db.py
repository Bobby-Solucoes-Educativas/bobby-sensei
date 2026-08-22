import hashlib
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()

_DATABASE_URL = os.environ["DATABASE_URL"]
_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "db" / "migrations"
_MIGRATIONS_TABLE = "schema_migrations"
_LOCK_KEY = 8274619283746  # int64 arbitrário, fixo para este projeto


def get_connection() -> psycopg.Connection:
    return psycopg.connect(_DATABASE_URL)


def ensure_schema() -> None:
    """Aplica as migrations pendentes em `db/migrations/`.

    Cada arquivo roda em sua própria transação e é registrado em
    `schema_migrations` com o sha256 do conteúdo, para detectar migration
    editada depois de aplicada.
    """

    if not _MIGRATIONS_DIR.is_dir():
        raise RuntimeError(
            f"diretório de migrations não encontrado: {_MIGRATIONS_DIR}"
        )

    with get_connection() as conn:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_MIGRATIONS_TABLE} (
                filename   text PRIMARY KEY,
                checksum   text NOT NULL,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )

    for migration_path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        sql = migration_path.read_text(encoding="utf-8")
        checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()

        with get_connection() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (_LOCK_KEY,))

            row = conn.execute(
                f"SELECT checksum FROM {_MIGRATIONS_TABLE} WHERE filename = %s",
                (migration_path.name,),
            ).fetchone()

            if row is not None:
                if row[0] != checksum:
                    raise RuntimeError(
                        f"{migration_path.name} foi editada depois de aplicada "
                        "— crie uma migration nova em vez de alterar esta"
                    )
                continue

            print(f"[migrations] aplicando {migration_path.name}")
            conn.execute(sql)
            conn.execute(
                f"INSERT INTO {_MIGRATIONS_TABLE} (filename, checksum) "
                "VALUES (%s, %s)",
                (migration_path.name, checksum),
            )