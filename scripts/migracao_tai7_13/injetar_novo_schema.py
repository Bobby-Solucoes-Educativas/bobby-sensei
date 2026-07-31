"""Lê os CSVs gerados por extrair_legado.py e injeta no schema NOVO (TAI7-13).

Uso:
    DATABASE_URL_DESTINO=postgresql://... python injetar_novo_schema.py [pasta_csv]

Pré-requisito: o banco de destino já precisa ter as tabelas
conversas/mensagens/feedback criadas (rodar db/migrations/001_feedback.sql
antes disto).

Traduções aplicadas (ver conversa com o Arthur em 2026-07-29/30):
    mensagens.role  'user'/'assistant'   -> papel 'usuario'/'assistente'
    feedback.rating 'up'/'down'          -> positivo boolean
    mensagens.chunks                     -> fontes (mesmo JSON)
    bot_respondeu (não existia)          -> recalculado com a heurística
        abaixo, que precisa ficar em sync com
        core/retrieve.py:_MARCADORES_NAO_RESPONDIDO
    ids texto/uuid do legado              -> ids BIGINT IDENTITY novos,
        remapeados em memória (dicionários id_legado -> id_novo)

reply_to do legado é ignorado de propósito: o schema novo não precisa dele
— core/dashboard_data.py e core/feedback.py já resolvem "qual foi a
pergunta desta resposta" via LATERAL (última mensagem 'usuario' anterior
na mesma conversa, por ordem de id). Por isso a ORDEM de inserção das
mensagens importa: tem que ser a mesma ordem cronológica do legado
(garantida por extrair_legado.py, que já exporta em ORDER BY created_at),
senão os ids novos não crescem na ordem certa e o LATERAL erra a pergunta.
"""

import csv
import json
import os
import sys
from pathlib import Path

import psycopg

# Precisa ficar idêntico a core/retrieve.py:_MARCADORES_NAO_RESPONDIDO —
# se um dia adicionarem/tirarem marcador lá, replicar aqui também.
_MARCADORES_NAO_RESPONDIDO = (
    "não encontr",
    "não há informa",
    "não tenho essa informa",
)


def _bot_respondeu(conteudo: str) -> bool:
    texto = conteudo.lower()
    return not any(marcador in texto for marcador in _MARCADORES_NAO_RESPONDIDO)


def _ler_csv(caminho: Path) -> list[dict]:
    with open(caminho, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def injetar(database_url: str, pasta_csv: Path) -> dict[str, int]:
    conversas_legado = _ler_csv(pasta_csv / "conversas.csv")
    mensagens_legado = _ler_csv(pasta_csv / "mensagens.csv")
    feedback_legado = _ler_csv(pasta_csv / "feedback.csv")

    # criada_em de cada conversa = 1ª mensagem dela (legado não tinha essa coluna).
    primeira_mensagem: dict[str, str] = {}
    for m in mensagens_legado:
        cid = m["conversation_id"]
        if cid not in primeira_mensagem or m["created_at"] < primeira_mensagem[cid]:
            primeira_mensagem[cid] = m["created_at"]

    map_conversas: dict[str, int] = {}
    map_mensagens: dict[str, int] = {}
    contagens = {"conversas": 0, "mensagens": 0, "feedback": 0}

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            # 1) conversas
            for c in conversas_legado:
                criada_em = primeira_mensagem.get(c["id"])  # pode faltar se a conversa não tem mensagem
                cur.execute(
                    """
                    INSERT INTO conversas (criada_em, atendente, session_id)
                    VALUES (COALESCE(%(criada_em)s, now()), NULL, NULL)
                    RETURNING id
                    """,
                    {"criada_em": criada_em},
                )
                map_conversas[c["id"]] = cur.fetchone()[0]
                contagens["conversas"] += 1

            # 2) mensagens — na MESMA ordem do CSV (cronológica), ver docstring.
            papel_por_role = {"user": "usuario", "assistant": "assistente"}
            for m in mensagens_legado:
                papel = papel_por_role[m["role"]]
                bot_respondeu = _bot_respondeu(m["content"]) if papel == "assistente" else None
                fontes = m["chunks"] if m["chunks"] else None

                cur.execute(
                    """
                    INSERT INTO mensagens (conversa_id, papel, conteudo, bot_respondeu, fontes, criada_em)
                    VALUES (%(conversa_id)s, %(papel)s, %(conteudo)s, %(bot_respondeu)s, %(fontes)s, %(criada_em)s)
                    RETURNING id
                    """,
                    {
                        "conversa_id": map_conversas[m["conversation_id"]],
                        "papel": papel,
                        "conteudo": m["content"],
                        "bot_respondeu": bot_respondeu,
                        "fontes": fontes,
                        "criada_em": m["created_at"],
                    },
                )
                map_mensagens[m["id"]] = cur.fetchone()[0]
                contagens["mensagens"] += 1

            # 3) feedback
            for fb in feedback_legado:
                cur.execute(
                    """
                    INSERT INTO feedback (mensagem_id, positivo, comentario, criada_em, atualizada_em)
                    VALUES (%(mensagem_id)s, %(positivo)s, %(comentario)s, %(criada_em)s, %(criada_em)s)
                    """,
                    {
                        "mensagem_id": map_mensagens[fb["message_id"]],
                        "positivo": fb["rating"] == "up",
                        "comentario": fb["comment"] or None,
                        "criada_em": fb["created_at"],
                    },
                )
                contagens["feedback"] += 1

        conn.commit()

    return contagens


if __name__ == "__main__":
    database_url = os.environ.get("DATABASE_URL_DESTINO")
    if not database_url:
        print("Defina DATABASE_URL_DESTINO (conexão com o banco no schema novo).", file=sys.stderr)
        sys.exit(1)

    pasta_csv = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "csv_legado"
    print(f"Injetando de {pasta_csv}/ para {database_url!r} ...")
    contagens = injetar(database_url, pasta_csv)
    print("Concluído:", contagens)
