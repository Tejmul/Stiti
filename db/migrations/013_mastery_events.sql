-- Features 3 + 4 (docs/FEATURE_PLAN.md): review cards per concept + the mastery history behind the map.
-- Apply: psql stiti -f db/migrations/013_mastery_events.sql

-- 3. Review: one FSRS card per concept the coach taught, linked to its source (mastery key) + concept id.
--    front = the concept's check question, back = what a right answer contains; check = the whole check
--    (kind, options, expectations, hints, reveal) so a review asks it the same way, hint → reveal.
ALTER TABLE study_cards ADD COLUMN IF NOT EXISTS source_key text;     -- tutor/mastery.py key_for(source)
ALTER TABLE study_cards ADD COLUMN IF NOT EXISTS source text;         -- his file path (#unit) or the topic
ALTER TABLE study_cards ADD COLUMN IF NOT EXISTS concept_id text;
ALTER TABLE study_cards ADD COLUMN IF NOT EXISTS concept text;        -- the concept's name, for the board + page
ALTER TABLE study_cards ADD COLUMN IF NOT EXISTS check_spec jsonb;
CREATE UNIQUE INDEX IF NOT EXISTS study_cards_concept ON study_cards (source_key, concept_id) WHERE source_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS study_cards_source_due ON study_cards (source_key, due) WHERE source_key IS NOT NULL;

-- 4. Mastery as an append-only history (iTutor technique 5: beliefs are never overwritten; the JSON in
--    ~/.stiti/tutor/mastery stays the readable current value). One row per mastery update.
CREATE TABLE IF NOT EXISTS mastery_events (
  id          bigserial PRIMARY KEY,
  source_key  text NOT NULL,                          -- same key as ~/.stiti/tutor/mastery/<key>.json
  concept_id  text NOT NULL,                          -- id in ~/.stiti/tutor/concepts/<key>.json
  verdict     text NOT NULL,                          -- correct | partial | wrong | idk | inferred
  hints       smallint NOT NULL DEFAULT 0,
  p_before    real,
  p_after     real NOT NULL,
  origin      text NOT NULL CHECK (origin IN ('probe', 'check', 'review', 'blurt')),
  at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS mastery_events_source ON mastery_events (source_key, at);
CREATE INDEX IF NOT EXISTS mastery_events_concept ON mastery_events (source_key, concept_id, at);
