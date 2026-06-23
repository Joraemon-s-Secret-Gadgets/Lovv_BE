-- Add optional birth_date to users for profile enrichment (마이페이지 프로필 입력).
-- Field is nullable/optional by product decision; no backfill required.
ALTER TABLE users
  ADD COLUMN birth_date DATE NULL AFTER avatar_url;
