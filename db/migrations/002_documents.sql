-- v0.1: document ingestion (notes, PDFs, docs). Apply: psql stiti -f db/migrations/002_documents.sql
CREATE TABLE IF NOT EXISTS documents (
  id          bigserial PRIMARY KEY,
  path        text NOT NULL UNIQUE,
  title       text NOT NULL,
  kind        text NOT NULL,                 -- md, pdf, docx, pptx, xlsx, html, txt
  sha256      text NOT NULL,                 -- re-ingest only when content changes
  privacy     smallint NOT NULL DEFAULT 1 CHECK (privacy BETWEEN 0 AND 2),
  ingested_at timestamptz NOT NULL DEFAULT now(),
  modified_at timestamptz
);
CREATE TABLE IF NOT EXISTS chunks (
  id          bigserial PRIMARY KEY,
  document_id bigint NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  ord         int NOT NULL,
  section     text,                          -- heading path, e.g. "Plan > Phase 2"
  header      text NOT NULL,                 -- contextual header: title · section · date
  text        text NOT NULL,
  context     text,                          -- optional cloud-written context (night job, P0/P1 only)
  privacy     smallint NOT NULL DEFAULT 1,
  embedding   halfvec(768),
  embed_model text,
  tsv         tsvector GENERATED ALWAYS AS (to_tsvector('simple', header || ' ' || text)) STORED
);
CREATE INDEX IF NOT EXISTS chunks_vec ON chunks USING hnsw (embedding halfvec_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_tsv ON chunks USING gin (tsv);

-- hybrid recall over document chunks (same RRF design as episodes)
CREATE OR REPLACE FUNCTION recall_chunks(q_tsq tsquery, q_vec halfvec(768), max_privacy smallint DEFAULT 1, k int DEFAULT 5)
RETURNS TABLE (chunk_id bigint, score double precision, sim double precision, title text, section text, text text)
LANGUAGE sql STABLE AS $$
WITH v AS (
  SELECT id, row_number() OVER (ORDER BY d) AS r
  FROM (SELECT id, embedding <=> q_vec AS d FROM chunks
        WHERE embedding IS NOT NULL AND privacy <= max_privacy ORDER BY embedding <=> q_vec LIMIT 40) s
), t AS (
  SELECT id, row_number() OVER (ORDER BY rk DESC) AS r
  FROM (SELECT id, ts_rank_cd(tsv, q_tsq) AS rk FROM chunks
        WHERE tsv @@ q_tsq AND privacy <= max_privacy ORDER BY rk DESC LIMIT 40) s
), fused AS (
  SELECT COALESCE(v.id, t.id) AS id, COALESCE(1.0/(60 + v.r), 0) + COALESCE(1.0/(60 + t.r), 0) AS rrf
  FROM v FULL OUTER JOIN t ON v.id = t.id
)
SELECT c.id, f.rrf, 1 - (c.embedding <=> q_vec), d.title, c.section, c.text
FROM fused f JOIN chunks c ON c.id = f.id JOIN documents d ON d.id = c.document_id
ORDER BY f.rrf DESC LIMIT k;
$$;
