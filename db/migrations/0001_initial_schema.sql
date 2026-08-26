CREATE TABLE public.chunks (
    chunk_id text NOT NULL,
    page_id text NOT NULL,
    title text NOT NULL,
    url text NOT NULL,
    parent_id text,
    breadcrumb text NOT NULL,
    chunk_index integer NOT NULL,
    text text NOT NULL,
    ancestors jsonb DEFAULT '[]'::jsonb NOT NULL,
    attachments jsonb DEFAULT '[]'::jsonb NOT NULL,
    embedding public.vector(1536) NOT NULL,
    embedded_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE public.conversas (
    id text NOT NULL,
    title text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE public.mensagens (
    id text NOT NULL,
    conversation_id text NOT NULL,
    role text NOT NULL,
    content text NOT NULL,
    chunks jsonb DEFAULT '[]'::jsonb NOT NULL,
    reply_to text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT mensagens_role_check
        CHECK ((role = ANY (ARRAY['user'::text, 'assistant'::text])))
);

CREATE TABLE public.feedback (
    id integer NOT NULL,
    message_id text NOT NULL,
    rating text NOT NULL,
    comment text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT feedback_rating_check
        CHECK ((rating = ANY (ARRAY['up'::text, 'down'::text])))
);

CREATE SEQUENCE public.feedback_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.feedback_id_seq OWNED BY public.feedback.id;

ALTER TABLE ONLY public.feedback
    ALTER COLUMN id SET DEFAULT nextval('public.feedback_id_seq'::regclass);

ALTER TABLE ONLY public.chunks
    ADD CONSTRAINT chunks_pkey PRIMARY KEY (chunk_id);

ALTER TABLE ONLY public.conversas
    ADD CONSTRAINT conversas_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.mensagens
    ADD CONSTRAINT mensagens_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.feedback
    ADD CONSTRAINT feedback_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.feedback
    ADD CONSTRAINT feedback_message_id_key UNIQUE (message_id);

ALTER TABLE ONLY public.mensagens
    ADD CONSTRAINT mensagens_conversation_id_fkey
    FOREIGN KEY (conversation_id) REFERENCES public.conversas(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.mensagens
    ADD CONSTRAINT mensagens_reply_to_fkey
    FOREIGN KEY (reply_to) REFERENCES public.mensagens(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.feedback
    ADD CONSTRAINT feedback_message_id_fkey
    FOREIGN KEY (message_id) REFERENCES public.mensagens(id) ON DELETE CASCADE;

CREATE INDEX chunks_embedding_idx
    ON public.chunks USING hnsw (embedding public.vector_cosine_ops);

CREATE INDEX chunks_bm25_idx
    ON public.chunks USING bm25 (chunk_id, title, text) WITH (key_field=chunk_id);

CREATE INDEX chunks_page_id_idx ON public.chunks USING btree (page_id);

CREATE INDEX mensagens_conversation_id_idx
    ON public.mensagens USING btree (conversation_id);