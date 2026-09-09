# Feedback (👍/👎) e dashboard (TAI7-12)

Instrumento de medição da fase de validação do MVP: histórico de
conversas persistido no mesmo Postgres/ParadeDB da busca vetorial
(TAI7-6), classificação 👍/👎 + comentário por resposta, e uma página de
dashboard no próprio Streamlit lendo esses dados.

## Tabelas (`core/db.py`)

Criadas por `ensure_schema()` (chamada uma vez por processo em `app.py`, via
`st.cache_resource`), que aplica as migrations pendentes em `db/migrations/`:

- `conversas (id, title, created_at)`
- `mensagens (id, conversation_id -> conversas, role, content, chunks, reply_to -> mensagens, created_at)`
  — `reply_to` liga a resposta do assistente à pergunta do usuário que a
  originou (a mesma pergunta que foi passada pra `answer_question`).
- `feedback (id, message_id -> mensagens UNIQUE, rating ('up'|'down'), comment, created_at)`
  — `message_id` é único: um novo clique substitui o feedback anterior em
  vez de duplicar linha.

## Persistência (`core/persistence.py`)

Sem `import streamlit`, mesmo padrão de `core/chat_state.py` e
`core/retrieve.py`:

- `save_conversation(conversation_id, title)` — upsert; título só é
  conhecido depois da 1ª pergunta (ver `chat_state._derive_title`).
- `save_message(message_id, conversation_id, role, content, chunks=None, reply_to=None)`
- `save_feedback(message_id, rating, comment=None)` — `rating` é `"up"` ou `"down"`.

`app.py` chama `save_conversation` + `save_message` (via `_persist`) logo
após cada `add_message`, tanto para a pergunta do usuário quanto pra
resposta do assistente.

## Widget de feedback (`ui/feedback.py`)

`render_feedback_widget(message)` desenha 👍/👎 abaixo de cada resposta do
assistente. O 👎 abre um campo de comentário livre opcional antes de
gravar (é o caso que mais interessa pro time entender onde a
documentação falhou). Estado local (qual botão foi clicado, se já
enviou) fica em `st.session_state.feedback_state`, indexado por
`message.id` — a gravação em si é sempre `core.persistence.save_feedback`.

## Dashboard (`pages/1_Dashboard.py`)

Página Streamlit multipage (`http://localhost:8501/Dashboard`), lendo só
funções puras de `core/dashboard_data.py`:

- `feedback_summary()` — total avaliado e % 👍/👎.
- `question_volume(days=30)` — perguntas por dia.
- `negative_feedback()` — pergunta (via `reply_to`) + resposta + comentário
  de cada 👎, mais recente primeiro.
- `listar_nao_classificados()` / `listar_negativos(categoria, time_atribuido)`
  — mesma base, com/sem filtro pela classificação (ver seção abaixo).
- `unanswered_questions()` — heurística por frases ("não encontrei", "não
  há informa...", indisponibilidade do backend) nas respostas do
  assistente. É uma aproximação pro time revisar à mão, não um
  classificador exato — ver `_MARCADORES_NAO_RESPONDIDO`.

## Classificação do 👎 (documentação x pipeline)

Regra decidida com o Arthur em 2026-07-29: o atendente, olhando o
dashboard, classifica a causa de cada 👎 em uma de duas categorias, com
atribuição automática do time responsável (`core/store.time_sugerido`) —
sobrescrevível antes de enviar:

- **documentacao** — a documentação não responde à dúvida → **Time de
  Desenvolvimento**.
- **pipeline** — a documentação atende, mas a resposta do bot foi ruim
  (retrieval, prompt, geração) → **Time 7**.

`feedback.categoria`/`time_atribuido` ficam `NULL` até alguém classificar
(migration `0008_classificacao_feedback.sql`) — todo o histórico de 👎
anterior a essa feature entra de uma vez na fila de "não classificados".
`core.store.classificar_feedback(feedback_id, categoria, time_atribuido,
classificado_por)` grava a classificação; não há edição depois de
classificado, só o override do time antes de enviar.

`classificado_por` vem do login geral do app (ver seção "Login" abaixo) —
não é mais um campo de e-mail solto.

O que acontece depois da classificação (notificar o Time 7 / Time de
Desenvolvimento) ainda está em aberto — por enquanto é só o rótulo
gravado e visível no dashboard.

## Login (`core/auth.py`, `ui/auth.py`)

Chat (`app.py`) e dashboard exigem login antes de mostrar qualquer coisa —
`ui.auth.require_login()` é a primeira chamada em cada um dos dois
(depois de `ensure_schema()`, já que a tabela `atendentes` só existe a
partir da migration `0009_autenticacao_atendentes.sql`). `st.session_state`
é compartilhado entre as páginas do multipage app, então logar numa libera
a outra na hora — a mesma conta autentica tanto o envio de 👍/👎 no chat
(`conversas.atendente`, finalmente populado — antes existia na tabela mas
nunca era preenchido) quanto a classificação de feedback no dashboard
(`feedback.classificado_por`).

Não há admin cadastrando atendente: é auto-cadastro (aba "Criar conta"),
restrito por domínio de e-mail (`core.auth.EMAIL_DOMINIO_PERMITIDO`,
hoje `@bobby.com.br`) — decisão da v1, sem integração com um provedor de
identidade corporativo de verdade (Google Workspace/Microsoft 365), o que
seria a alternativa mais segura se/quando isso for revisado. Senha com
hash bcrypt (`core.auth.criar_atendente`/`autenticar`), nunca texto puro.
Sessão dura enquanto a aba do navegador ficar aberta — sem "lembrar de
mim" nem reset de senha nesta v1.

`feedback.criado_por` (migration `0010_feedback_criado_por.sql`) grava quem
enviou o 👍/👎: `ui.feedback.render_feedback_widget` lê
`ui.auth.logged_in_email()` na hora do clique e passa pra
`core.store.registrar_feedback`, sem pedir e-mail de novo (o widget já
está atrás do `require_login()` do `app.py`). É um campo separado de
`classificado_por` — a pessoa que classifica a causa do 👎 no dashboard
pode não ser a mesma que enviou o feedback no chat.

## Como testar

```bash
cd bobby-sensei
docker compose up --build
```

Em `http://localhost:8501`: na aba "Criar conta", cadastre um e-mail
`@bobby.com.br` + senha (mínimo 8 caracteres). Logado, pergunte algo,
clique 👍 ou 👎 (com comentário) na resposta, depois abra "Dashboard" na
barra lateral — já autenticado — e confira o volume, o %, a fila de
"Não classificados" e a lista de 👎.
