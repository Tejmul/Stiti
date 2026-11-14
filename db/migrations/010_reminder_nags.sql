-- D39: reminders that don't give up. One row per delivered reminder until he acknowledges it ("ok", "got it",
-- "ho gaya") or Stiti gives up. Also the log of channel + ack latency per delivery (research: alarms.md §2e).
CREATE TABLE IF NOT EXISTS reminder_nags (
  id            bigserial PRIMARY KEY,
  intent_id     bigint REFERENCES intents(id) ON DELETE CASCADE,
  say           text NOT NULL,
  important     boolean NOT NULL DEFAULT false,
  sent          int NOT NULL DEFAULT 1,                 -- deliveries so far (the first one included)
  first_at      timestamptz NOT NULL DEFAULT now(),
  last_at       timestamptz NOT NULL DEFAULT now(),
  next_at       timestamptz,                            -- NULL: no more repeats (waiting for an ack, then gave_up)
  state         text NOT NULL DEFAULT 'open' CHECK (state IN ('open','acked','gave_up')),
  channels      text[] NOT NULL DEFAULT '{}',           -- voice | notification | telegram | none, per delivery
  acked_at      timestamptz,
  ack_via       text,                                   -- voice | text | web | telegram | click | reminders_app
  ack_latency_s real                                    -- seconds from the LAST delivery to his ack
);
CREATE INDEX IF NOT EXISTS reminder_nags_open ON reminder_nags (next_at) WHERE state = 'open';
