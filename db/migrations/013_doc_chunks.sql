-- Feature 2 (cited answers): his study file cut into page-tagged chunks for doubts answered with a real quote.
-- 013 (012 is taken by feature 1, jobs, on its own branch). Apply: psql stiti -f db/migrations/013_doc_chunks.sql
-- Everything here is his own file's text: it stays in this Mac's Postgres; only the 3–4 passages retrieved for one
-- doubt go to the free LLM (as the lesson's sources already do).

-- one row per indexed file: re-index only when the file changes (mtime + size) or the embedder changes
CREATE TABLE IF NOT EXISTS doc_sources (
  source_key  text PRIMARY KEY,                    -- sha1 of the resolved path (tutor/cite.py source_key)
  path        text NOT NULL,
  mtime       double precision NOT NULL,
  size        bigint NOT NULL,
  pages       int NOT NULL DEFAULT 0,
  chunks      int NOT NULL DEFAULT 0,
  outline     boolean NOT NULL DEFAULT false,      -- a syllabus / topic list: nothing to quote, doubts stay general
  complete    boolean NOT NULL DEFAULT false,      -- every page indexed (a partial index never claims "not covered")
  embed_model text,
  indexed_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS doc_chunks (
  id          bigserial PRIMARY KEY,
  source_key  text NOT NULL REFERENCES doc_sources(source_key) ON DELETE CASCADE,
  path        text NOT NULL,
  page_label  text NOT NULL,                       -- the printed page number ("42", "xii")
  page_index  int NOT NULL,                        -- 0-based page in tutor/book.py's pages
  unit        text,                                -- the chapter / unit the page sits in ("Unit 2 — Parsing")
  char_start  int NOT NULL,                        -- span inside that page's text: the quote can be highlighted
  char_end    int NOT NULL,
  text        text NOT NULL,
  tsv         tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
  embedding   halfvec(768),                        -- embed.py: EmbeddingGemma-300M, 768-d (same type as chunks)
  UNIQUE (source_key, page_index, char_start)
);
CREATE INDEX IF NOT EXISTS doc_chunks_source ON doc_chunks (source_key, page_index);
CREATE INDEX IF NOT EXISTS doc_chunks_tsv ON doc_chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS doc_chunks_vec ON doc_chunks USING hnsw (embedding halfvec_cosine_ops);

-- per-file answer bank: a repeated doubt is answered from here, without an LLM call
CREATE TABLE IF NOT EXISTS doc_answers (
  id          bigserial PRIMARY KEY,
  source_key  text NOT NULL REFERENCES doc_sources(source_key) ON DELETE CASCADE,
  question    text NOT NULL,
  embedding   halfvec(768) NOT NULL,
  answer      jsonb NOT NULL,                      -- {say, quotes (verified), ops, check}
  hits        int NOT NULL DEFAULT 0,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS doc_answers_source ON doc_answers (source_key);
