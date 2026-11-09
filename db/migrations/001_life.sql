-- v0.1: life management (habits, nudge log). Apply: psql stiti -f db/migrations/001_life.sql
CREATE TABLE IF NOT EXISTS habits (
  id            bigserial PRIMARY KEY,
  name          text NOT NULL,
  cue           text,                         -- implementation intention: "after morning chai"
  target_per_week smallint NOT NULL DEFAULT 7,
  strength      real NOT NULL DEFAULT 0,      -- Loop-style EMA 0..1; misses dent it, never zero it
  prompt_level  smallint NOT NULL DEFAULT 2,  -- 2 daily · 1 every other day · 0 no prompts (fades as it sticks)
  status        text NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','archived')),
  created_at    timestamptz NOT NULL DEFAULT now(),
  last_scored   date
);
CREATE TABLE IF NOT EXISTS habit_events (
  habit_id  bigint REFERENCES habits(id),
  day       date NOT NULL,
  done      boolean NOT NULL,
  PRIMARY KEY (habit_id, day)
);
CREATE TABLE IF NOT EXISTS nudges (
  id         bigserial PRIMARY KEY,
  kind       text NOT NULL,                  -- morning_brief, overdue, habit, checkin
  sent_at    timestamptz NOT NULL DEFAULT now(),
  response   text CHECK (response IN ('accepted','dismissed','ignored')),
  payload    jsonb
);
CREATE INDEX IF NOT EXISTS nudges_sent ON nudges (sent_at);
