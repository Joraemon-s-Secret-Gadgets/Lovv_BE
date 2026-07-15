-- @file schema/aurora_mysql/004_admin_high_risk_approvals.sql
-- @description Applies rerunnable role constraints and creates high-risk approval and MFA storage tables.
-- @author JJonyeok2
-- @lastModified 2026-07-15

-- Production migration for C2 high-risk admin approvals and MFA.
-- Safe to run after an older 002_admin_console_tables.sql and safe to re-run.

-- Constraint names may differ between environments. Discover the CHECK that
-- governs role_code and replace it only when R-SUPER-ADMIN is not yet allowed.
SET @user_role_check_name := (
  SELECT tc.CONSTRAINT_NAME
  FROM information_schema.TABLE_CONSTRAINTS AS tc
  JOIN information_schema.CHECK_CONSTRAINTS AS cc
    ON cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
   AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
  WHERE tc.CONSTRAINT_SCHEMA = DATABASE()
    AND tc.TABLE_NAME = 'user_role_assignments'
    AND tc.CONSTRAINT_TYPE = 'CHECK'
    AND LOWER(cc.CHECK_CLAUSE) LIKE '%role_code%'
  ORDER BY tc.CONSTRAINT_NAME
  LIMIT 1
);

SET @user_role_check_clause := (
  SELECT cc.CHECK_CLAUSE
  FROM information_schema.TABLE_CONSTRAINTS AS tc
  JOIN information_schema.CHECK_CONSTRAINTS AS cc
    ON cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
   AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
  WHERE tc.CONSTRAINT_SCHEMA = DATABASE()
    AND tc.TABLE_NAME = 'user_role_assignments'
    AND tc.CONSTRAINT_NAME = @user_role_check_name
  LIMIT 1
);

SET @user_role_check_sql := CASE
  WHEN @user_role_check_name IS NOT NULL
       AND @user_role_check_clause LIKE '%R-SUPER-ADMIN%'
    THEN 'DO 0'
  WHEN @user_role_check_name IS NOT NULL
    THEN CONCAT(
      'ALTER TABLE user_role_assignments DROP CHECK `',
      REPLACE(@user_role_check_name, '`', '``'),
      '`, ADD CONSTRAINT chk_user_role_code CHECK ',
      '(role_code IN (''R-ADMIN'', ''R-SUPER-ADMIN'', ''R-DATA-PROVIDER'', ''R-LOCAL-OPERATOR''))'
    )
  ELSE
    'ALTER TABLE user_role_assignments ADD CONSTRAINT chk_user_role_code CHECK '
    '(role_code IN (''R-ADMIN'', ''R-SUPER-ADMIN'', ''R-DATA-PROVIDER'', ''R-LOCAL-OPERATOR''))'
END;

PREPARE user_role_check_statement FROM @user_role_check_sql;
EXECUTE user_role_check_statement;
DEALLOCATE PREPARE user_role_check_statement;

CREATE TABLE IF NOT EXISTS admin_high_risk_change_requests (
  id                      CHAR(36)     NOT NULL,
  operation_type          VARCHAR(40)  NOT NULL,
  target_user_id          CHAR(36)     NULL,
  payload_json            JSON         NOT NULL,
  status                  VARCHAR(20)  NOT NULL DEFAULT 'pending',
  reason                  VARCHAR(500) NOT NULL,
  requested_by            CHAR(36)     NOT NULL,
  decided_by              CHAR(36)     NULL,
  decision_reason         VARCHAR(500) NULL,
  requested_at            DATETIME(3)  NOT NULL,
  decided_at              DATETIME(3)  NULL,
  executed_at             DATETIME(3)  NULL,
  execution_summary_json  JSON         NULL,
  updated_at              DATETIME(3)  NOT NULL,
  PRIMARY KEY (id),
  KEY idx_high_risk_status_time (status, requested_at),
  KEY idx_high_risk_operation_time (operation_type, requested_at),
  KEY idx_high_risk_target_time (target_user_id, requested_at),
  KEY idx_high_risk_requester_time (requested_by, requested_at),
  CONSTRAINT fk_high_risk_target_user
    FOREIGN KEY (target_user_id) REFERENCES users(id)
    ON DELETE RESTRICT ON UPDATE CASCADE,
  -- requested_by/decided_by are used in chk_high_risk_distinct_actors.
  -- MySQL 8.0 forbids a modifying referential action (ON UPDATE CASCADE) on a
  -- column referenced by a CHECK constraint, and users.id (UUID PK) never
  -- changes, so ON UPDATE NO ACTION is both required and semantically correct.
  CONSTRAINT fk_high_risk_requester
    FOREIGN KEY (requested_by) REFERENCES users(id)
    ON DELETE RESTRICT ON UPDATE NO ACTION,
  CONSTRAINT fk_high_risk_decider
    FOREIGN KEY (decided_by) REFERENCES users(id)
    ON DELETE RESTRICT ON UPDATE NO ACTION,
  CONSTRAINT chk_high_risk_operation
    CHECK (operation_type IN ('role_grant', 'role_revoke', 'region_grant', 'region_revoke', 'bulk_publish')),
  CONSTRAINT chk_high_risk_status
    CHECK (status IN ('pending', 'executed', 'rejected')),
  CONSTRAINT chk_high_risk_distinct_actors
    CHECK (decided_by IS NULL OR decided_by <> requested_by),
  CONSTRAINT chk_high_risk_decision_time
    CHECK (decided_at IS NULL OR decided_at >= requested_at),
  CONSTRAINT chk_high_risk_execution_time
    CHECK (executed_at IS NULL OR executed_at >= requested_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS admin_mfa_credentials (
  user_id               CHAR(36)      NOT NULL,
  encrypted_secret      TEXT          NOT NULL,
  status                VARCHAR(20)   NOT NULL DEFAULT 'pending',
  last_used_counter     BIGINT        NULL,
  recovery_codes_json   JSON          NOT NULL,
  failed_attempts       INT           NOT NULL DEFAULT 0,
  locked_until          DATETIME(3)   NULL,
  enrolled_at           DATETIME(3)   NOT NULL,
  confirmed_at          DATETIME(3)   NULL,
  updated_at            DATETIME(3)   NOT NULL,
  PRIMARY KEY (user_id),
  CONSTRAINT fk_admin_mfa_credential_user
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT chk_admin_mfa_credential_status
    CHECK (status IN ('pending', 'active', 'revoked')),
  CONSTRAINT chk_admin_mfa_failed_attempts
    CHECK (failed_attempts >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS admin_mfa_sessions (
  session_id            VARCHAR(120)  NOT NULL,
  user_id               CHAR(36)      NOT NULL,
  verified_at           DATETIME(3)   NOT NULL,
  expires_at            DATETIME(3)   NOT NULL,
  method                VARCHAR(30)   NOT NULL,
  created_at            DATETIME(3)   NOT NULL,
  updated_at            DATETIME(3)   NOT NULL,
  PRIMARY KEY (session_id),
  KEY idx_admin_mfa_session_user_expiry (user_id, expires_at),
  CONSTRAINT fk_admin_mfa_session_user
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT chk_admin_mfa_session_method
    CHECK (method IN ('totp', 'recovery_code')),
  CONSTRAINT chk_admin_mfa_session_window
    CHECK (expires_at > verified_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- EOF: schema/aurora_mysql/004_admin_high_risk_approvals.sql
