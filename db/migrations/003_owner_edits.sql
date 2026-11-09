-- v0.1: provenance for owner edits made in USER.md / LESSONS.md / onboarding.
ALTER TABLE user_directives ADD COLUMN IF NOT EXISTS origin text NOT NULL DEFAULT 'stiti';   -- stiti | owner_edit | onboarding
ALTER TABLE facts           ADD COLUMN IF NOT EXISTS origin text NOT NULL DEFAULT 'stiti';
ALTER TABLE lessons         ADD COLUMN IF NOT EXISTS origin text NOT NULL DEFAULT 'stiti';
