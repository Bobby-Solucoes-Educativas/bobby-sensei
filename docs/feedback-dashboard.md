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
- `unanswered_questions()` — heurística por frases ("não encontrei", "não
  há informa...", indisponibilidade do backend) nas respostas do
  assistente. É uma aproximação pro time revisar à mão, não um
  classificador exato — ver `_MARCADORES_NAO_RESPONDIDO`.

## Como testar

```bash
cd bobby-sensei
docker compose up --build
```

Em `http://localhost:8501`: pergunte algo, clique 👍 ou 👎 (com
comentário) na resposta, depois abra "Dashboard" na barra lateral e
confira o volume, o % e a pergunta na lista de 👎.
