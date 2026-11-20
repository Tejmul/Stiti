-- D56: background jobs with live progress (concept maps today; notes, recaps, transcription later).
-- One row per job. A worker thread inside Stiti.app claims rows with FOR UPDATE SKIP LOCKED; every change fires
-- NOTIFY stiti_jobs (trigger below) → /api/events (server-sent events) → the Lessons page updates live.
-- A job survives a restart: a running row whose heartbeat stopped is put back in the queue, and `checkpoint` keeps
-- what the handler already finished, so it resumes from its last step. A free-tier 429 parks it until `not_before`.
CREATE TABLE IF NOT EXISTS stiti_job (
  id            bigserial PRIMARY KEY,
  kind          text NOT NULL,                          -- handler name: concept_map | …
  recipe        jsonb NOT NULL DEFAULT '{}',            -- the job's inputs ({"path": …})
  recipe_hash   text NOT NULL,                          -- sha256(kind + canonical recipe): enqueue is idempotent
  source_hash   text,                                   -- hash of the input file (path + size + mtime): stale outputs
  label         text,                                   -- what the page shows ("Compiler Notebook.pdf")
  status        text NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued','running','done','failed','parked','cancelled')),
  step          text,                                   -- "Reading unit 3 of 8"
  percent       int NOT NULL DEFAULT 0 CHECK (percent BETWEEN 0 AND 100),
  eta_s         int,                                    -- seconds left, best guess
  error         text,                                   -- last error, safe to show him
  attempts      int NOT NULL DEFAULT 0,                 -- runs that ended in an error (retry with backoff)
  max_attempts  int NOT NULL DEFAULT 3,
  parks         int NOT NULL DEFAULT 0,                 -- times parked for a free-tier limit (separate backoff)
  not_before    timestamptz,                            -- parked / retrying: not claimed before this
  claimed_by    text,                                   -- worker id (host:pid:n)
  heartbeat_at  timestamptz,                            -- a running job's worker is alive while this moves
  checkpoint    jsonb NOT NULL DEFAULT '{}',            -- what the handler already finished (resume point)
  result        jsonb,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  started_at    timestamptz,
  finished_at   timestamptz
);
-- at most one live job per recipe (queued / running / parked): a second "Prepare" click returns the same job
CREATE UNIQUE INDEX IF NOT EXISTS stiti_job_live_uq ON stiti_job (recipe_hash)
  WHERE status IN ('queued','running','parked');
CREATE INDEX IF NOT EXISTS stiti_job_ready_idx ON stiti_job (status, not_before, created_at);
CREATE INDEX IF NOT EXISTS stiti_job_recent_idx ON stiti_job (updated_at DESC);

CREATE OR REPLACE FUNCTION stiti_job_notify() RETURNS trigger AS $$
BEGIN
  -- only what the page shows: a heartbeat or a checkpoint save alone doesn't wake every open tab
  IF TG_OP = 'UPDATE' AND NEW.status = OLD.status AND NEW.step IS NOT DISTINCT FROM OLD.step
     AND NEW.percent = OLD.percent AND NEW.eta_s IS NOT DISTINCT FROM OLD.eta_s
     AND NEW.error IS NOT DISTINCT FROM OLD.error AND NEW.not_before IS NOT DISTINCT FROM OLD.not_before
     AND NEW.attempts = OLD.attempts AND NEW.label IS NOT DISTINCT FROM OLD.label THEN
    RETURN NEW;
  END IF;
  -- a small summary (NOTIFY payloads must stay under 8000 bytes); the page merges it by id
  PERFORM pg_notify('stiti_jobs', json_build_object(
    'id', NEW.id, 'kind', NEW.kind, 'label', left(NEW.label, 140), 'status', NEW.status,
    'step', left(NEW.step, 140), 'percent', NEW.percent, 'eta_s', NEW.eta_s, 'error', left(NEW.error, 300),
    'attempts', NEW.attempts, 'max_attempts', NEW.max_attempts, 'not_before', NEW.not_before,
    'created_at', NEW.created_at, 'updated_at', NEW.updated_at, 'finished_at', NEW.finished_at)::text);
  RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS stiti_job_notify_trg ON stiti_job;
CREATE TRIGGER stiti_job_notify_trg AFTER INSERT OR UPDATE ON stiti_job
  FOR EACH ROW EXECUTE FUNCTION stiti_job_notify();
