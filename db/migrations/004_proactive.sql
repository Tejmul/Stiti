-- v0.2: proactivity — learned nudge preferences (Beta-Bernoulli bandit per kind) + segments.
CREATE TABLE IF NOT EXISTS nudge_arms (
  kind      text PRIMARY KEY,           -- meeting_soon, break, deadline, evening_wrap, followup, habit, morning_brief
  alpha     real NOT NULL DEFAULT 2,    -- prior: mostly helpful until he says otherwise
  beta      real NOT NULL DEFAULT 1,
  disabled  boolean NOT NULL DEFAULT false,  -- "don't remind me about breaks" -> permanent
  updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE nudges ADD COLUMN IF NOT EXISTS channel text;      -- voice | telegram | notification
ALTER TABLE nudges ADD COLUMN IF NOT EXISTS answered_at timestamptz;
-- topic segments of conversations (built nightly, no LLM): time gaps + embedding drift
CREATE TABLE IF NOT EXISTS segments (
  id          bigserial PRIMARY KEY,
  session_id  bigint REFERENCES sessions(id),
  first_ep    bigint NOT NULL,
  last_ep     bigint NOT NULL,
  started_at  timestamptz NOT NULL,
  ended_at    timestamptz NOT NULL,
  n_episodes  int NOT NULL,
  mood        text,
  summary     text,                     -- filled by the cloud night job when available
  embedding   halfvec(768)
);
CREATE UNIQUE INDEX IF NOT EXISTS segments_span ON segments (first_ep, last_ep);
CREATE TABLE IF NOT EXISTS reflections (
  id          bigserial PRIMARY KEY,
  text        text NOT NULL,            -- Stiti's own insight, e.g. "He gets stressed on Sunday nights before sprint planning"
  evidence    bigint[] NOT NULL DEFAULT '{}',
  confidence  real NOT NULL DEFAULT 0.6,
  created_at  timestamptz NOT NULL DEFAULT now(),
  embedding   halfvec(768)
);
