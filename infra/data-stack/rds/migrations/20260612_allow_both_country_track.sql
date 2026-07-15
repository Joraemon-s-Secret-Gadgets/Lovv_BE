-- @file infra/data-stack/rds/migrations/20260612_allow_both_country_track.sql
-- @description Extends the user preference country constraint to accept the API fallback value BOTH.
-- @author JJonyeok2
-- @lastModified 2026-07-15

-- Allow the API fallback countryTrack value used when the frontend does not send a country filter.
ALTER TABLE user_preferences
  DROP CHECK chk_user_preferences_country;

ALTER TABLE user_preferences
  ADD CONSTRAINT chk_user_preferences_country
  CHECK (country_track IN ('KR', 'JP', 'BOTH'));

-- EOF: infra/data-stack/rds/migrations/20260612_allow_both_country_track.sql
