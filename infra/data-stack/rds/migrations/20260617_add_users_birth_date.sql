-- @file infra/data-stack/rds/migrations/20260617_add_users_birth_date.sql
-- @description Adds an optional birth date field to user profiles without requiring a data backfill.
-- @author JJonyeok2
-- @lastModified 2026-07-15

-- Add optional birth_date to users for profile enrichment (마이페이지 프로필 입력).
-- Field is nullable/optional by product decision; no backfill required.
ALTER TABLE users
  ADD COLUMN birth_date DATE NULL AFTER avatar_url;

-- EOF: infra/data-stack/rds/migrations/20260617_add_users_birth_date.sql
