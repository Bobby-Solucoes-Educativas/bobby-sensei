# TAI7-24: login geral do app — a mesma conta autentica tanto o envio de
# feedback no chat (app.py) quanto a classificação de feedback no dashboard
# (pages/1_Dashboard.py). Sem import streamlit, mesmo padrão do resto de
# core/; quem desenha o formulário é ui/auth.py.
import bcrypt
from psycopg.errors import UniqueViolation

try:
    from core.db import get_connection
except ImportError:
    from db import get_connection

# Restrição simples de domínio pro auto-cadastro (não há admin cadastrando
# atendentes hoje) — só pra não deixar qualquer e-mail criar conta. Repensar
# se a Bobby migrar pra um provedor de identidade corporativo de verdade
# (Google Workspace/Microsoft 365) em vez de senha própria do bobby-sensei.
EMAIL_DOMINIO_PERMITIDO = "@bobby.com.br"
_SENHA_MIN_LEN = 8


class EmailInvalido(Exception):
    pass


class EmailJaCadastrado(Exception):
    pass


def _normalizar_email(email: str) -> str:
    return email.strip().lower()


def criar_atendente(email: str, senha: str) -> str:
    """Auto-cadastro de um atendente novo: e-mail precisa ser do domínio
    corporativo, senha vai com hash bcrypt (nunca texto puro, e o bcrypt já
    embute o salt no próprio hash). Devolve o e-mail normalizado, pra quem
    chamou já abrir a sessão logada sem outra consulta."""

    email = _normalizar_email(email)
    if not email.endswith(EMAIL_DOMINIO_PERMITIDO):
        raise EmailInvalido(f"Use seu e-mail corporativo ({EMAIL_DOMINIO_PERMITIDO}).")
    if len(senha) < _SENHA_MIN_LEN:
        raise ValueError(f"A senha precisa ter pelo menos {_SENHA_MIN_LEN} caracteres.")

    senha_hash = bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    sql = "INSERT INTO atendentes (email, senha_hash) VALUES (%(email)s, %(senha_hash)s)"
    try:
        with get_connection() as conn:
            conn.execute(sql, {"email": email, "senha_hash": senha_hash})
    except UniqueViolation:
        raise EmailJaCadastrado(f"Já existe uma conta para {email}.")
    return email


def autenticar(email: str, senha: str) -> str | None:
    """Confere a senha contra o hash salvo; devolve o e-mail normalizado se
    bater, ou None (e-mail não encontrado e senha errada dão o mesmo
    resultado pra fora — a UI mostra uma mensagem genérica, sem dar pista de
    quais e-mails têm conta)."""

    email = _normalizar_email(email)
    sql = "SELECT senha_hash FROM atendentes WHERE email = %(email)s"
    with get_connection() as conn:
        row = conn.execute(sql, {"email": email}).fetchone()

    if row is None:
        return None
    return email if bcrypt.checkpw(senha.encode("utf-8"), row[0].encode("utf-8")) else None
