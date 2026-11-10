-- D28: opt-in local conversation recorder + personal emotion learning.
-- One row per committed voice turn while the recorder is ON. The FLAC lives in ~/.stiti/recordings/<day>/;
-- `path` is NULL once the audio expired (features + labels are kept so the personal head never forgets).
CREATE TABLE IF NOT EXISTS voice_turns (
  id              bigserial PRIMARY KEY,
  recorded_at     timestamptz NOT NULL DEFAULT now(),
  session_id      bigint,
  episode_id      bigint REFERENCES episodes(id) ON DELETE SET NULL,
  path            text,                 -- relative to ~/.stiti/recordings, NULL after retention
  bytes           int NOT NULL DEFAULT 0,
  duration_ms     int,
  transcript      text NOT NULL,
  speech_ms       int,                  -- his speech in the segment
  pause_ms        int,                  -- silence between his last word and the commit
  turn_state      text,                 -- finished | unfinished | wait
  timed_out       boolean,
  overlap         boolean,              -- began while she was speaking
  barged          boolean,
  stt_ms          real,
  no_speech_prob  real,
  avg_logprob     real,
  prosody         jsonb,                -- raw {db, pitch, pitch_sd, rate}
  prosody_label   text,                 -- generic prosody rule label at the time
  voice_label     text,                 -- what the live loop passed to the engine
  voice_conf      real,
  voice_src       text,                 -- generic | personal
  text_label      text,
  text_conf       real,
  fused_label     text,
  e2v_label       text,                 -- generic emotion2vec label mapped to Stiti moods
  e2v_conf        real,
  e2v_scores      jsonb,
  embedding       vector(768)           -- emotion2vec+ utterance embedding (live or nightly)
);
CREATE INDEX IF NOT EXISTS voice_turns_time ON voice_turns (recorded_at);

-- Weak labels, rebuilt nightly from his words (self_report / neighbour / correction / pseudo); checkin + manual kept.
CREATE TABLE IF NOT EXISTS emotion_labels (
  id             bigserial PRIMARY KEY,
  voice_turn_id  bigint NOT NULL REFERENCES voice_turns(id) ON DELETE CASCADE,
  label          text NOT NULL,
  polarity       smallint NOT NULL DEFAULT 1 CHECK (polarity IN (-1, 1)),   -- -1 = "NOT this mood"
  weight         real NOT NULL DEFAULT 1.0,
  source         text NOT NULL,
  evidence       text,
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS emotion_labels_turn ON emotion_labels (voice_turn_id);
