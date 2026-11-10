-- D25 persona + psychology: memory-callback budget (gate G4: the same episode is never volunteered twice in 7 days,
-- at most one unprompted callback per hour). NULL = never volunteered.
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS last_volunteered_at timestamptz;
CREATE INDEX IF NOT EXISTS episodes_volunteered ON episodes (last_volunteered_at) WHERE last_volunteered_at IS NOT NULL;
