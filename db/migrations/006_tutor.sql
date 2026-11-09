-- v0.6: whiteboard tutor (D14/D15). Apply: psql stiti -f db/migrations/006_tutor.sql
CREATE TABLE IF NOT EXISTS tutor_lessons (
  id          bigserial PRIMARY KEY,
  title       text NOT NULL,
  topic       text,
  source      jsonb NOT NULL DEFAULT '{}'::jsonb,   -- {kind: topic|book|demo, path, pages…}
  plan        jsonb NOT NULL,                       -- the full lesson (segments, cues, ops, checks)
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tutor_sessions (
  id          bigserial PRIMARY KEY,
  lesson_id   bigint NOT NULL REFERENCES tutor_lessons(id) ON DELETE CASCADE,
  started_at  timestamptz NOT NULL DEFAULT now(),
  ended_at    timestamptz,
  cursor      int NOT NULL DEFAULT 0,               -- index of the next cue (resume point)
  finished    boolean NOT NULL DEFAULT false,
  results     jsonb NOT NULL DEFAULT '[]'::jsonb,   -- per check: verdict, attempts, confidence
  questions   jsonb NOT NULL DEFAULT '[]'::jsonb    -- what the learner asked
);
CREATE INDEX IF NOT EXISTS tutor_sessions_recent ON tutor_sessions (started_at DESC);

-- spaced-repetition cards made at the end of a lesson (FSRS fields; scheduler comes next)
CREATE TABLE IF NOT EXISTS study_cards (
  id           bigserial PRIMARY KEY,
  lesson_id    bigint REFERENCES tutor_lessons(id) ON DELETE CASCADE,
  front        text NOT NULL,
  back         text NOT NULL,
  kind         text NOT NULL DEFAULT 'fact',
  source_pages text,
  due          timestamptz NOT NULL DEFAULT now() + interval '1 day',
  stability    real,
  difficulty   real,
  reps         int NOT NULL DEFAULT 0,
  lapses       int NOT NULL DEFAULT 0,
  state        smallint NOT NULL DEFAULT 0,          -- 0 new · 1 learning · 2 review · 3 relearning
  last_review  timestamptz,
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (lesson_id, front)
);
CREATE INDEX IF NOT EXISTS study_cards_due ON study_cards (due);
