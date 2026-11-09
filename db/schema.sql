-- Stiti Engine v0 schema. Source: reports/Stiti personal AI buddy research.md (Engine v0 build spec).
-- Apply with: psql stiti -f db/schema.sql

CREATE EXTENSION IF NOT EXISTS vector;      -- pgvector >= 0.8 (halfvec, iterative scans)
CREATE EXTENSION IF NOT EXISTS btree_gist;  -- equality inside GiST exclusion constraints
CREATE EXTENSION IF NOT EXISTS pg_trgm;     -- fuzzy names / Hinglish spelling variants

-- 1. sessions
CREATE TABLE sessions (
  id          bigserial PRIMARY KEY,
  channel     text NOT NULL CHECK (channel IN ('voice','text','telegram')),
  started_at  timestamptz NOT NULL DEFAULT now(),
  ended_at    timestamptz
);

-- 2. episodes: immutable ground truth, one row per utterance, never deleted
CREATE TABLE episodes (
  id               bigserial PRIMARY KEY,
  session_id       bigint REFERENCES sessions(id),
  speaker          text NOT NULL CHECK (speaker IN ('user','stiti','tool','system')),
  origin           text NOT NULL DEFAULT 'owner'
                   CHECK (origin IN ('owner','agent','untrusted','system')),   -- OpenClaw provenance
  text             text NOT NULL,
  occurred_at      timestamptz NOT NULL DEFAULT now(),   -- world time
  ingested_at      timestamptz NOT NULL DEFAULT now(),   -- system time
  privacy          smallint NOT NULL DEFAULT 1 CHECK (privacy BETWEEN 0 AND 2),  -- P0/P1/P2
  emotion          jsonb,          -- {"voice":"tense","conf":0.62,"text":"stressed","arousal":0.7}
  importance       smallint NOT NULL DEFAULT 3 CHECK (importance BETWEEN 1 AND 10),
  strength         real NOT NULL DEFAULT 1.0,            -- MemoryBank-style; decays, never deletes
  access_count     int  NOT NULL DEFAULT 0,
  last_accessed_at timestamptz,
  embedding        halfvec(768),
  embed_model      text,
  tsv              tsvector GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED,
  extracted_at     timestamptz                           -- consolidation watermark
);
CREATE INDEX episodes_vec  ON episodes USING hnsw (embedding halfvec_cosine_ops);
CREATE INDEX episodes_tsv  ON episodes USING gin (tsv);
CREATE INDEX episodes_trgm ON episodes USING gin (text gin_trgm_ops);
CREATE INDEX episodes_time ON episodes (occurred_at);

-- 3. entities: people, projects, places, feelings...
CREATE TABLE entities (
  id          bigserial PRIMARY KEY,
  kind        text NOT NULL CHECK (kind IN ('self','person','project','place','org','event','feeling','topic','thing')),
  name        text NOT NULL,
  aliases     text[] NOT NULL DEFAULT '{}',
  summary     text,
  embedding   halfvec(768),
  privacy     smallint NOT NULL DEFAULT 1,
  merged_into bigint REFERENCES entities(id),
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX entities_name_trgm ON entities USING gin (name gin_trgm_ops);
CREATE INDEX entities_vec ON entities USING hnsw (embedding halfvec_cosine_ops);

-- 4. facts: bitemporal edges (Graphiti model, Postgres-enforced)
CREATE TABLE facts (
  id                 bigserial PRIMARY KEY,
  subj_id            bigint NOT NULL REFERENCES entities(id),
  predicate          text   NOT NULL,              -- works_at, lives_in, feels_about, knows...
  obj_id             bigint REFERENCES entities(id),
  obj_literal        text,
  fact_text          text   NOT NULL,              -- "Tejmul works at X"
  attrs              jsonb,                        -- {"valence":-0.6}
  functional         boolean NOT NULL DEFAULT false,
  valid              tstzrange NOT NULL DEFAULT tstzrange(now(), NULL),  -- world time
  recorded           tstzrange NOT NULL DEFAULT tstzrange(now(), NULL),  -- system time
  confidence         real NOT NULL DEFAULT 0.7,
  privacy            smallint NOT NULL DEFAULT 1,
  source_episode_ids bigint[] NOT NULL DEFAULT '{}',
  invalidated_by     bigint REFERENCES facts(id),
  embedding          halfvec(768),
  CHECK (obj_id IS NOT NULL OR obj_literal IS NOT NULL),
  -- two values of a functional predicate can never be valid at the same time
  EXCLUDE USING gist (subj_id WITH =, predicate WITH =, valid WITH &&)
    WHERE (functional AND upper_inf(recorded))
);
CREATE INDEX facts_subj  ON facts (subj_id);
CREATE INDEX facts_obj   ON facts (obj_id);
CREATE INDEX facts_valid ON facts USING gist (valid);

-- 5. provenance join (Zep episode-mentions)
CREATE TABLE episode_mentions (
  episode_id bigint REFERENCES episodes(id),
  entity_id  bigint REFERENCES entities(id),
  PRIMARY KEY (episode_id, entity_id)
);

-- 6. user model: one imperative directive per row, superseded in place (renders USER.md)
CREATE TABLE user_directives (
  id                 bigserial PRIMARY KEY,
  directive          text NOT NULL,     -- "Reply in Hinglish when I speak Hinglish"
  category           text NOT NULL CHECK (category IN ('talk_style','routine','preference','boundary','goal')),
  supersession_key   text NOT NULL,     -- e.g. 'reply_language'
  status             text NOT NULL DEFAULT 'active' CHECK (status IN ('proposed','active','superseded')),
  observed_at        timestamptz NOT NULL DEFAULT now(),
  superseded_by      bigint REFERENCES user_directives(id),
  source_episode_ids bigint[] NOT NULL DEFAULT '{}',
  privacy            smallint NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX one_active_directive ON user_directives (supersession_key) WHERE status = 'active';

-- 7. lessons: ACE-style itemized playbook (renders LESSONS.md)
CREATE TABLE lessons (
  id                  bigserial PRIMARY KEY,
  situation           text  NOT NULL,                 -- "Tejmul stressed, late night, work topic"
  trigger             jsonb NOT NULL DEFAULT '{}',    -- {"mood":["stressed"],"topic":["work"],"time":"late_night","person":[12]}
  guidance            text  NOT NULL,                 -- imperative, <= 25 words
  polarity            text  NOT NULL CHECK (polarity IN ('do','dont')),
  source              text  NOT NULL CHECK (source IN ('owner_explicit','inferred')),
  status              text  NOT NULL DEFAULT 'candidate' CHECK (status IN ('candidate','active','retired')),
  seen_count          int   NOT NULL DEFAULT 1,
  confidence          real  NOT NULL DEFAULT 0.5,
  helpful_count       int   NOT NULL DEFAULT 0,
  harmful_count       int   NOT NULL DEFAULT 0,
  situation_embedding halfvec(768),
  source_episode_ids  bigint[] NOT NULL DEFAULT '{}',
  supersedes          bigint REFERENCES lessons(id),
  created_at          timestamptz NOT NULL DEFAULT now(),
  last_applied_at     timestamptz
);
CREATE INDEX lessons_trigger ON lessons USING gin (trigger jsonb_path_ops);

-- 8. tasks (was SQLite in the productivity notes)
CREATE TABLE tasks (
  id            bigserial PRIMARY KEY,
  title         text NOT NULL,
  notes         text,
  status        text NOT NULL DEFAULT 'open' CHECK (status IN ('open','done','parked','cancelled')),
  created_at    timestamptz NOT NULL DEFAULT now(),
  due           timestamptz, scheduled timestamptz, wait_until timestamptz,
  est_minutes   int,
  energy        text CHECK (energy IN ('low','med','high')),
  context       text,                                     -- home, desk, errand, phone
  value         smallint CHECK (value BETWEEN 1 AND 5),   -- TMT V
  expectancy    real,                                     -- TMT E (0-1)
  aversiveness  real,                                     -- 0-1
  parent_id     bigint REFERENCES tasks(id),              -- Socratic Chunker tree
  depends_on    bigint[] NOT NULL DEFAULT '{}',
  done_when     text, if_then text, recur_rule text,
  carried_over  int NOT NULL DEFAULT 0,
  source        text NOT NULL DEFAULT 'voice',
  ek_identifier text,                                     -- Apple Reminders mirror
  privacy       smallint NOT NULL DEFAULT 1
);

-- 9. intents: alarms, reminders, check-ins, nudges (was APScheduler+SQLite)
CREATE TABLE intents (
  id            bigserial PRIMARY KEY,
  kind          text NOT NULL CHECK (kind IN ('alarm','reminder','checkin','nudge','event_trigger')),
  task_id       bigint REFERENCES tasks(id),
  fire_at       timestamptz, rrule text, trigger jsonb,
  payload       jsonb NOT NULL,                  -- what to say/do
  user_set      boolean NOT NULL DEFAULT true,   -- user-set alarms are never suppressed
  state         text NOT NULL DEFAULT 'pending'
                CHECK (state IN ('pending','armed','fired','done','cancelled','expired')),
  cooldown      interval DEFAULT '24 hours',     -- OpenClaw standing-intent defaults for nudges
  fires_left    int DEFAULT 3,
  expires_at    timestamptz,
  last_fired_at timestamptz,
  ek_identifier text
);
CREATE INDEX intents_due ON intents (fire_at) WHERE state IN ('pending','armed');

-- 10. turns: one row per exchange (latency + what was recalled)
CREATE TABLE turns (
  id              bigserial PRIMARY KEY,
  session_id      bigint REFERENCES sessions(id),
  user_episode_id bigint REFERENCES episodes(id),
  reply_episode_id bigint REFERENCES episodes(id),
  route           text NOT NULL CHECK (route IN ('fast_path','llm','degraded')),
  provider        text, model text, privacy smallint,
  briefing        text, briefing_tokens int,
  recalled        jsonb,       -- {"episodes":[..],"facts":[..],"lessons":[..]}
  latency_ms      jsonb,       -- {"stt":..,"laya":..,"recall":..,"ttft":..,"tts_first":..}
  created_at      timestamptz NOT NULL DEFAULT now()
);

-- 11. decisions: every Laya answer + outcome (calibration data)
CREATE TABLE decisions (
  id           bigserial PRIMARY KEY,
  turn_id      bigint REFERENCES turns(id),
  question     text NOT NULL,
  answer       text NOT NULL,
  confidence   real NOT NULL,
  acted        boolean NOT NULL,
  laya_version text NOT NULL,
  outcome      text CHECK (outcome IN ('confirmed','corrected','ignored','unknown')),
  corrected_to text,
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- 12. llm_usage: quota + cooldown per provider/model/day
CREATE TABLE llm_usage (
  provider        text, model text, day date,
  requests        int NOT NULL DEFAULT 0,
  tokens_in       int NOT NULL DEFAULT 0,
  tokens_out      int NOT NULL DEFAULT 0,
  minute_start    timestamptz, minute_tokens int NOT NULL DEFAULT 0, minute_requests int NOT NULL DEFAULT 0,
  cooldown_until  timestamptz,
  last_error      text,
  PRIMARY KEY (provider, model, day)
);

-- 13. briefing_cache: sleep-time precompiled standing context + daily digests
CREATE TABLE briefing_cache (
  key         text PRIMARY KEY,   -- 'standing_profile','open_loops','active_projects','digest:2026-11-10'
  content     text NOT NULL,
  tokens      int  NOT NULL,
  built_at    timestamptz NOT NULL DEFAULT now(),
  valid_until timestamptz,
  run_id      bigint
);

-- 14. consolidation_runs: idempotent, watermarked night jobs
CREATE TABLE consolidation_runs (
  id          bigserial PRIMARY KEY,
  job         text NOT NULL,
  started_at  timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  status      text NOT NULL DEFAULT 'running' CHECK (status IN ('running','ok','partial','failed')),
  watermark   bigint,           -- last episode id processed
  provider    text, tokens_used int,
  stats       jsonb,            -- counts + every ACE delta applied
  error       text
);

-- wake workers right after a turn (payload = id only, < 8 KB)
CREATE FUNCTION notify_episode() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN PERFORM pg_notify('stiti_mem', NEW.id::text); RETURN NEW; END $$;
CREATE TRIGGER episodes_notify AFTER INSERT ON episodes
  FOR EACH ROW EXECUTE FUNCTION notify_episode();

-- ===== retrieval functions =====
CREATE FUNCTION recall(q_tsq tsquery, q_vec halfvec(768),
                       t_from timestamptz DEFAULT NULL, t_to timestamptz DEFAULT NULL,
                       max_privacy smallint DEFAULT 1, k int DEFAULT 12)
RETURNS TABLE (episode_id bigint, score double precision, sim double precision, importance smallint, occurred_at timestamptz, text text)
LANGUAGE sql STABLE AS $$
WITH v AS (                         -- semantic leg: LIMIT inside so HNSW is used, rank after
  SELECT id, row_number() OVER (ORDER BY d) AS r
  FROM (SELECT id, embedding <=> q_vec AS d
        FROM episodes
        WHERE embedding IS NOT NULL AND privacy <= max_privacy
          AND (t_from IS NULL OR occurred_at >= t_from) AND (t_to IS NULL OR occurred_at < t_to)
        ORDER BY embedding <=> q_vec LIMIT 50) s
), t AS (                           -- lexical leg ('simple' config: safe for Hinglish)
  SELECT id, row_number() OVER (ORDER BY rk DESC) AS r
  FROM (SELECT id, ts_rank_cd(tsv, q_tsq) AS rk
        FROM episodes
        WHERE tsv @@ q_tsq AND privacy <= max_privacy
          AND (t_from IS NULL OR occurred_at >= t_from) AND (t_to IS NULL OR occurred_at < t_to)
        ORDER BY rk DESC LIMIT 50) s
), fused AS (                       -- Reciprocal Rank Fusion, k = 60
  SELECT COALESCE(v.id, t.id) AS id,
         COALESCE(1.0/(60 + v.r), 0) + COALESCE(1.0/(60 + t.r), 0) AS rrf
  FROM v FULL OUTER JOIN t ON v.id = t.id
)
SELECT e.id,
       f.rrf
       -- recency: 30-day half-life with a 0.5 floor, so old memories still surface ("infinite memory")
       * (0.5 + 0.5 * exp(-ln(2) * extract(epoch FROM now() - COALESCE(e.last_accessed_at, e.occurred_at)) / (30*86400)))
       * (0.7 + 0.03 * e.importance)                     -- importance 1-10
       * (0.8 + 0.2 * LEAST(e.strength, 1.0))            -- MemoryBank strength
       AS score,
       1 - (e.embedding <=> q_vec) AS sim,
       e.importance,
       e.occurred_at, e.text
FROM fused f JOIN episodes e ON e.id = f.id
ORDER BY score DESC
LIMIT k;
$$;

-- current facts around the entities in play (1-2 hops, valid now, not retracted)
CREATE FUNCTION current_facts(seed_ids bigint[], max_depth int DEFAULT 2, max_privacy smallint DEFAULT 1)
RETURNS TABLE (fact_id bigint, fact_text text, valid tstzrange, depth int)
LANGUAGE sql STABLE AS $$
WITH RECURSIVE nb(entity_id, depth, path) AS (
  SELECT unnest(seed_ids), 0, ARRAY[]::bigint[]
  UNION ALL
  SELECT CASE WHEN f.subj_id = nb.entity_id THEN f.obj_id ELSE f.subj_id END,
         nb.depth + 1, nb.path || f.id
  FROM nb JOIN facts f ON (f.subj_id = nb.entity_id OR f.obj_id = nb.entity_id)
  WHERE nb.depth < max_depth AND f.valid @> now() AND upper_inf(f.recorded)
    AND f.privacy <= max_privacy AND f.obj_id IS NOT NULL AND NOT f.id = ANY(nb.path)
)
SELECT DISTINCT ON (f.id) f.id, f.fact_text, f.valid, nb.depth
FROM nb JOIN facts f ON (f.subj_id = nb.entity_id OR f.obj_id = nb.entity_id)
WHERE f.valid @> now() AND upper_inf(f.recorded) AND f.privacy <= max_privacy
ORDER BY f.id, nb.depth
LIMIT 40;
$$;
