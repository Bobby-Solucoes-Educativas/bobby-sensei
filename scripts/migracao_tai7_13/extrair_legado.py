"""Extrai conversas/mensagens/feedback do schema ANTIGO (TAI7-12) pra CSV.

Uso:
    DATABASE_URL_ORIGEM=postgresql://... python extrair_legado.py [pasta_saida]

`pasta_saida` default é ./csv_legado/ (relativo a este arquivo). Gera
conversas.csv, mensagens.csv e feedback.csv, um pra um com as colunas do
schema antigo (sem nenhuma tradução — a tradução é feita no script de
injeção). JSONB (`chunks`) vira uma string JSON dentro da célula do CSV.

Rodar contra o dump real: restaurar o dump num Postgres à parte e apontar
DATABASE_URL_ORIGEM pra ele. Este script só LÊ — não faz UPDATE/DELETE.
"""

import csv
import json
import os
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

TABELAS = {
    "conversas": ["id", "title"],
    "mensagens": ["id", "conversation_id", "role", "content", "chunks", "reply_to", "created_at"],
    "feedback": ["message_id", "rating", "comment", "created_at"],
}


def extrair(database_url: str, pasta_saida: Path) -> dict[str, int]:
    pasta_saida.mkdir(parents=True, exist_ok=True)
    contagens = {}

    with psycopg.connect(database_url) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            for tabela, colunas in TABELAS.items():
                cur.execute(f"SELECT {', '.join(colunas)} FROM {tabela} ORDER BY created_at" if "created_at" in colunas else f"SELECT {', '.join(colunas)} FROM {tabela}")
                linhas = cur.fetchall()

                caminho = pasta_saida / f"{tabela}.csv"
                with open(caminho, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=colunas)
                    writer.writeheader()
                    for linha in linhas:
                        linha = dict(linha)
                        if "chunks" in linha and linha["chunks"] is not None:
                            linha["chunks"] = json.dumps(linha["chunks"])
                        writer.writerow(linha)

                contagens[tabela] = len(linhas)
                print(f"  {tabela}: {len(linhas)} linhas -> {caminho}")

    return contagens


if __name__ == "__main__":
    database_url = os.environ.get("DATABASE_URL_ORIGEM")
    if not database_url:
        print("Defina DATABASE_URL_ORIGEM (conexão com o banco no schema antigo).", file=sys.stderr)
        sys.exit(1)

    pasta_saida = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "csv_legado"
    print(f"Extraindo de {database_url!r} para {pasta_saida}/ ...")
    contagens = extrair(database_url, pasta_saida)
    print("Concluído:", contagens)
