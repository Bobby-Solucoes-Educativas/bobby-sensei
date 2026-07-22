# TAI7-9: paleta de cores da marca Bobby (verde-limão + branco do mascote),
# compartilhada entre os módulos de UI pra manter a identidade visual
# consistente. Contraste verificado (WCAG): GREEN vs branco = 5.26:1 (AA).
LIME = "#C6FF33"  # verde vibrante do traje — destaque, bolhas, acentos
GREEN = "#3E7A0F"  # mesma família, mais escuro — botões/links (legível com texto branco)
GREEN_SOFT = "#EFFAE0"  # verde bem claro — fundos e hovers sutis
WHITE = "#FFFFFF"
BLACK = "#14171A"

# Fundo principal do app. Espelha `backgroundColor` em `.streamlit/config.toml`
# — o config.toml é quem realmente pinta o fundo (tema nativo do Streamlit,
# só lido na subida do processo), essa constante existe pra quem for injetar
# CSS próprio (como app.py) usar o mesmo valor em vez de repetir o hex.
BACKGROUND = "#D4D4D9"  # cinza claro do mascote — fundo do app, barra lateral e bolhas


def rgba(hex_color: str, alpha: float) -> str:
    """Converte um hex da paleta (#RRGGBB) pra rgba(...) com a transparência
    pedida, pra CSS de hover/borda sem duplicar os valores RGB na mão."""
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha})"
