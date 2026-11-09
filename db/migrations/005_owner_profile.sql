-- v0.3: Stiti works for ANY owner (open source): profile + tentative trait estimates from the intake.
CREATE TABLE IF NOT EXISTS owner_profile (
  key        text PRIMARY KEY,          -- name, call_me, pronouns, language, timezone …
  value      text NOT NULL,
  source     text NOT NULL DEFAULT 'intake',
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS traits (
  key        text PRIMARY KEY,          -- big5_extraversion, chronotype, support_style, motive_autonomy …
  value      real,                      -- normalized 0..1 where numeric
  label      text,                      -- human-readable reading, e.g. "evening person"
  confidence real NOT NULL DEFAULT 0.5, -- tentative: grows with evidence, owner can correct
  evidence   text,                      -- which answers/words it came from
  source     text NOT NULL DEFAULT 'intake',  -- intake | conversation | owner_edit
  updated_at timestamptz NOT NULL DEFAULT now()
);
