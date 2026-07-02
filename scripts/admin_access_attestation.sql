-- Quarterly access-attestation inventory. Read-only: export the result as the
-- review input, then execute approved revocations through the controlled
-- role/region administration path when that API is available.

SELECT
  'role' AS assignment_type,
  a.id AS assignment_id,
  a.user_id,
  u.email,
  u.display_name,
  u.last_login_at,
  a.role_code AS assignment_value,
  a.organization_id,
  NULL AS region_id,
  a.valid_from,
  a.valid_until,
  a.granted_by,
  a.grant_reason,
  CASE
    WHEN u.last_login_at IS NULL OR u.last_login_at < UTC_TIMESTAMP(3) - INTERVAL 90 DAY
    THEN 'stale_login'
    ELSE 'active_use'
  END AS review_signal
FROM user_role_assignments a
JOIN users u ON u.id = a.user_id
WHERE a.status = 'active'
  AND a.valid_from <= UTC_TIMESTAMP(3)
  AND (a.valid_until IS NULL OR a.valid_until > UTC_TIMESTAMP(3))

UNION ALL

SELECT
  'region' AS assignment_type,
  a.id AS assignment_id,
  a.user_id,
  u.email,
  u.display_name,
  u.last_login_at,
  a.region_id AS assignment_value,
  a.organization_id,
  a.region_id,
  a.valid_from,
  a.valid_until,
  a.granted_by,
  a.grant_reason,
  CASE
    WHEN u.last_login_at IS NULL OR u.last_login_at < UTC_TIMESTAMP(3) - INTERVAL 90 DAY
    THEN 'stale_login'
    ELSE 'active_use'
  END AS review_signal
FROM user_region_assignments a
JOIN users u ON u.id = a.user_id
WHERE a.status = 'active'
  AND a.valid_from <= UTC_TIMESTAMP(3)
  AND (a.valid_until IS NULL OR a.valid_until > UTC_TIMESTAMP(3))

ORDER BY user_id, assignment_type, assignment_value;
