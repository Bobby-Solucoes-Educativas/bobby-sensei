# Chat UI: bolhas, múltiplas conversas e respostas com fontes (TAI7-9)

Interface Streamlit que consome o RAG híbrido (`core/retrieve.py`, TAI7-8 —
ver `docs/retrieve.md`): múltiplas conversas com barra lateral, mensagens
como bolhas, indicador de carregamento enquanto a busca roda, e as fontes
(chunks recuperados) exibidas em anexo na resposta.

## Como rodar

```bash
cd bobby-sensei
docker compose up --build
```

Abre em `http://localhost:8501`. Sem banco populado (TAI7-6) ou
`OPENAI_API_KEY` válida, a UI continua navegável — `chatbot_core` captura a
falha e cai num aviso de indisponibilidade em vez de travar (ver abaixo).

Só a UI, sem Docker:

```bash
cd bobby-sensei   # tem que ser a raiz do projeto, não src/
streamlit run src/app.py
```

## Módulos

| Módulo | Responsabilidade |
|---|---|
| `core/chat_state.py` | Estado das conversas — dataclasses puras, sem `streamlit` |
| `core/chatbot_core.py` | Orquestra pergunta → RAG → resposta + fontes, sem `streamlit` |
| `core/retrieve.py` | RAG híbrido (retrieval + LLM) — TAI7-8, ver `docs/retrieve.md` |
| `ui/chat_bubbles.py` | Desenha mensagens, indicador de carregamento e auto-scroll |
| `ui/sidebar.py` | Desenha a barra lateral (lista de conversas) |
| `ui/theme.py` | Paleta de cores da marca, compartilhada pelos módulos de UI |
| `app.py` | Liga tudo: `st.session_state`, fluxo de envio, loop de renderização |

`core/*` nunca importa `streamlit` — só `app.py` e `ui/*` desenham na tela,
o que permite reaproveitar o estado/orquestração por outro canal (ex.:
WhatsApp/FastAPI) no futuro.

## Estado da conversa (`core/chat_state.py`)

- `Message(role: str, content: str, chunks: list[dict] = [])`
- `Conversation(id: str, title: str | None, messages: list[Message], pinned: bool = False)`
- `new_conversation()` — conversa vazia, `id` gerado (`uuid4().hex`).
- `add_message(conversation, role, content, chunks=None)` — acrescenta a
  mensagem; se a conversa ainda não tem título, deriva um a partir da
  primeira pergunta do usuário (`_derive_title`, trunca em 40 caracteres).
- `rename_conversation(conversation, title)` / `toggle_pinned(conversation)`.

## Orquestração da resposta (`core/chatbot_core.py`)

```python
def answer_question(question: str) -> tuple[str, list[dict]]
```

Chama `core.retrieve.answer_with_chunks(question)` dentro de um
`try/except Exception`; se falhar (banco fora do ar, chave da OpenAI
ausente etc.), devolve `(mensagem_de_aviso, [])`. É o único ponto onde
`app.py` toca o RAG.

## Envio da pergunta: mensagem imediata + indicador de carregamento (`app.py`)

O envio acontece em duas etapas, pra pergunta aparecer na tela antes da
chamada (bloqueante) ao RAG terminar:

1. `st.chat_input` só chama `add_message(..., "user", question)` e dá
   `st.rerun()`.
2. No rerun seguinte, se a última mensagem ainda for do usuário (ninguém
   respondeu), o app desenha `render_loading_message()` e só então chama
   `answer_question()`. Isso funciona porque o Streamlit envia cada
   elemento pro navegador assim que ele é desenhado, não só no fim do
   script — o indicador já chega antes da chamada bloqueante começar. Ao
   terminar, adiciona a resposta e dá outro `st.rerun()`, que troca o
   indicador pela resposta final.

`scroll_to_bottom()` é chamada a cada rerun (mensagens, indicador e
resposta final) pra tela sempre acompanhar o conteúdo mais recente.

## Mensagens e indicador de carregamento (`ui/chat_bubbles.py`)

- `render_user_message(text)` — bolha à direita (`rgba(LIME, 0.22)` de
  fundo). Texto passa por `html.escape()` antes de virar HTML.
- `render_assistant_message(text, chunks=None)` — texto corrido à esquerda
  via `st.markdown(text)` puro (preserva negrito/listas/quebras vindas do
  RAG sem reimplementar parser de Markdown). Se `chunks` não for vazio,
  desenha um `st.expander(f"📎 {len(chunks)} trecho(s) da documentação
  consultados")` logo abaixo, listando fonte (`breadcrumb`/`title`), `url`
  e o texto de cada chunk.
- `render_loading_message()` — spinner CSS + "Bobby Sensei está buscando na
  documentação...", alinhado à esquerda (lado do assistente).
- `scroll_to_bottom()` — injeta uma âncora invisível no fim do conteúdo e
  um `components.html(...)` com `scrollIntoView()` via
  `window.parent.document` (o componente roda num iframe same-origin).

## Barra lateral (`ui/sidebar.py`)

```python
def render_sidebar(conversations, conversation_order, active_id) -> str | None
```

- "+ Novo chat", lista de conversas ordenada com fixadas primeiro
  (`sorted(..., key=lambda cid: not conversations[cid].pinned)`, sort
  estável).
- Cada linha (`st.container(key=f"chat-row-{id}")`) tem o botão de
  seleção + um `st.popover("⋮")` com renomear/fixar/excluir, visível só no
  hover da linha (CSS por `opacity`, escopado pela classe estável que a
  `key` do container gera).
- O `<style>` é reinjetado **a cada chamada** — o Streamlit reconstrói a
  árvore de elementos do zero em cada rerun, então um `<style>` emitido só
  uma vez some do DOM assim que qualquer interação disparar um rerun.
- `st.text_input` de renomear usa `key=f"rename-{id}-{conversation.title or ''}"`
  (título embutido na key): o Streamlit só respeita `value=` na primeira
  vez que uma key aparece, então sem isso o campo travava sempre vazio.
- O handler de excluir grava `st.session_state.active_id` diretamente antes
  de chamar `st.rerun()` — `st.rerun()` interrompe a execução na hora, e o
  `return` no fim da função nunca rodaria a tempo de `app.py` receber o
  novo `active_id`.

## Paleta de cores (`ui/theme.py` + `.streamlit/config.toml`)

`ui/theme.py` centraliza as cores da marca (verde-limão + branco do
mascote Bobby), importadas por `sidebar.py`, `chat_bubbles.py` e `app.py`:

- `LIME` (`#C6FF33`) — destaque/acentos/bolhas.
- `GREEN` (`#3E7A0F`) — mesma família, mais escuro; contraste WCAG com
  branco = 5.26:1 (AA), por isso é a cor usada onde há texto branco em
  cima (`LIME` sozinho só tem 1.18:1).
- `GREEN_SOFT`, `WHITE`, `BLACK`, `BACKGROUND` (fundo principal).
- `rgba(hex, alpha)` — helper pra CSS de hover/borda sem duplicar RGB.

`.streamlit/config.toml` define o tema **nativo** do Streamlit
(`primaryColor`, `backgroundColor` etc.), aplicado automaticamente nos
widgets padrão. Só é lido na subida do processo — mudar o arquivo exige
reiniciar (`docker compose restart app`), não hot-reloada como um `.py`. O
`docker-compose.yml` precisa montar `./.streamlit:/app/.streamlit` (não
teria efeito no container sem isso).

Dois pontos que exigiram CSS além do `config.toml`:
- O botão da conversa ativa (`type="primary"`, fundo `LIME`) precisa de uma
  regra mirando o `<p>` interno com `!important` — o CSS base do Streamlit
  aplica a cor do texto num elemento mais específico que o `<button>`.
- `app.py` pinta `[data-testid="stAppViewContainer"]` **e**
  `[data-testid="stBottom"]` com `BACKGROUND` — a barra do `chat_input` é
  um container separado no DOM, com fundo branco próprio; só o primeiro
  seletor deixava uma faixa branca visível.

## Favicon

`src/icon/Logo.png` (logo "BB" em `LIME`), via
`st.set_page_config(page_icon="./src/icon/Logo.png")` — caminho relativo à
raiz do repo (diretório de trabalho do processo Streamlit), não a
`app.py`. Diferente do emoji 🤖 fixo na tela de saudação (hero).

## Gotcha de ambiente (Docker Desktop + macOS)

O bind mount `./src:/app/src` às vezes não dispara o file-watcher do
Streamlit dentro do container (evento de escrita do host não propaga via
inotify) — uma mudança de código pode não refletir nem depois de recarregar
a página. Nesse caso, `docker compose restart app` antes de assumir que o
código está errado.

## Pendências para tickets futuros

- Persistir conversas entre sessões (hoje `st.session_state` é só em
  memória).
- Feedback/avaliação de resposta: ticket separado, ainda em refinamento.
- "🗑 Excluir" apaga direto, sem confirmação.
- `theme.py` (paleta Python) e `.streamlit/config.toml` guardam cores
  parcialmente sobrepostas sem sincronização automática — atualizar os dois
  se a paleta mudar de novo.
