-- Every question Stiti asks him, and whether he answered it (brain/asked.py). Owner, 2026-11-20: "it asks same
-- questions again and again — I have answered something and it forgets it". One row per question key: an answered
-- question is never asked again, a skipped one not for SKIP_DAYS. Keys: 'askme:<key>', 'onboarding:<key>',
-- 'weather:city', 'llm:<hash of the normalised question>' (questions the LLM put in her replies).
CREATE TABLE IF NOT EXISTS asked_questions (
  id             bigserial PRIMARY KEY,
  qkey           text NOT NULL UNIQUE,
  source         text NOT NULL,                         -- askme | onboarding | weather | llm | …
  question       text NOT NULL,
  embedding      halfvec(768),                          -- for "same meaning, other words" (llm questions)
  asked_count    integer NOT NULL DEFAULT 1,
  first_asked_at timestamptz NOT NULL DEFAULT now(),
  last_asked_at  timestamptz NOT NULL DEFAULT now(),
  answered_at    timestamptz,
  answer         text,                                  -- his words (left empty for private ones)
  answer_episode_id bigint,
  skipped_at     timestamptz,
  privacy        smallint NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS asked_questions_answered ON asked_questions (answered_at) WHERE answered_at IS NOT NULL;
