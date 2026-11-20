-- D49: things that matter, noticed in what he says, in mail and in documents. One row per thing (source_ref is a
-- hash of kind + day + its main words, so the same exam is never asked about twice, whatever mentioned it).
-- The open question lives here (stage + asked_at), not in the process: it survives a restart.
CREATE TABLE IF NOT EXISTS noticed (
  id            bigserial PRIMARY KEY,
  what          text NOT NULL,                          -- "exams", "interview at Orbit Labs"
  kind          text NOT NULL,                          -- exam | interview | deadline | bill | result | travel |
                                                        -- appointment | birthday | meeting | event
  when_at       timestamptz NOT NULL,                   -- the day (midnight) or the exact time
  has_time      boolean NOT NULL DEFAULT false,
  source        text NOT NULL CHECK (source IN ('said','mail','document','llm')),
  source_ref    text NOT NULL UNIQUE,                   -- dedup key
  source_label  text,                                   -- mail sender / document title
  heard         text,                                   -- the sentence or subject it came from
  meta          jsonb NOT NULL DEFAULT '{}',            -- {mine, starts, plural}
  confidence    real NOT NULL DEFAULT 0.7,
  privacy       smallint NOT NULL DEFAULT 1,
  status        text NOT NULL DEFAULT 'new'
                CHECK (status IN ('new','asked','accepted','declined','noted','expired')),
  stage         text CHECK (stage IN ('important','prep')),   -- the question she is waiting on right now
  created_at    timestamptz NOT NULL DEFAULT now(),
  asked_at      timestamptz,
  asked_via     text,                                   -- turn | voice | notification | telegram | list
  answered_at   timestamptz,
  undo_until    timestamptz,                            -- "undo" takes the booking back until then (cleared when he moves on)
  answer        text,                                   -- his words
  event_id      text,                                   -- Apple Calendar event identifier
  reminder_ids  bigint[] NOT NULL DEFAULT '{}',         -- intents she booked for it
  prep_intent_id bigint,
  task_id       bigint,
  fact_id       bigint
);
CREATE INDEX IF NOT EXISTS noticed_open ON noticed (when_at) WHERE status IN ('new','asked');
