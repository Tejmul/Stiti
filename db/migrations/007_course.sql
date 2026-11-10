-- v0.7: one-night crash course + FSRS revision (D19). Apply: psql stiti -f db/migrations/007_course.sql
CREATE TABLE IF NOT EXISTS tutor_courses (
  id          bigserial PRIMARY KEY,
  title       text NOT NULL,
  source      jsonb NOT NULL DEFAULT '{}'::jsonb,   -- {kind: book|subject, path, subject}
  goal        text,
  hours       real NOT NULL DEFAULT 3,
  plan        jsonb NOT NULL,                       -- ordered lessons: title, unit pages, diagnostic, depth, status
  cursor      int NOT NULL DEFAULT 0,               -- next lesson index (resume point)
  status      text NOT NULL DEFAULT 'planned',      -- planned · running · done · stopped
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE tutor_lessons ADD COLUMN IF NOT EXISTS course_id bigint REFERENCES tutor_courses(id) ON DELETE SET NULL;
ALTER TABLE tutor_lessons ADD COLUMN IF NOT EXISTS position int;
ALTER TABLE study_cards ADD COLUMN IF NOT EXISTS fsrs jsonb;          -- py-fsrs Card.to_dict() (source of truth)
ALTER TABLE study_cards ADD COLUMN IF NOT EXISTS course_id bigint REFERENCES tutor_courses(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS study_cards_course ON study_cards (course_id, due);
