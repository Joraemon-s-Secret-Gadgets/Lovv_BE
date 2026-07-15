-- @file schema/aurora_mysql/004_add_itinerary_share_columns.sql
-- @description Adds public sharing, source-copy tracking, and public itinerary lookup support.
-- @author JJonyeok2
-- @lastModified 2026-07-15

-- Lovv Product API Itinerary Share Schema Update.
-- Adds columns and index for public sharing, read-only view, and itinerary cloning.

ALTER TABLE itineraries
  ADD COLUMN is_public TINYINT(1) NOT NULL DEFAULT 0,
  ADD COLUMN copied_from_itinerary_id CHAR(36) NULL,
  ADD CONSTRAINT fk_itineraries_copied_from FOREIGN KEY (copied_from_itinerary_id) REFERENCES itineraries(id) ON DELETE SET NULL,
  ADD INDEX idx_itineraries_public_saved (is_public, saved_at DESC);

-- EOF: schema/aurora_mysql/004_add_itinerary_share_columns.sql
