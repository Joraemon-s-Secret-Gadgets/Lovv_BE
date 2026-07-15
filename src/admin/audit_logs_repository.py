# @file src/admin/audit_logs_repository.py
# @description Persists and queries append-only administrative audit records.
# @author JJonyeok2
# @lastModified 2026-07-15
#
# Append-only record of every admin mutation. Each entry snapshots who acted
# (actor + roles/org/region scopes), what action on which resource, and the
# result, so the console and operators can reconstruct an audit trail. Writes are
# best-effort for ordinary admin actions. High-risk success records are strict
# and share the business transaction; denied/failed high-risk attempts are
# written independently after rollback by admin.app.

import logging
import os
import uuid

from shared.database import create_database_client
from shared.rds_data import json_dumps, json_loads


LOGGER = logging.getLogger(__name__)


AUDIT_RESULTS = {"allowed", "denied", "succeeded", "failed"}


def build_audit_entry(
    principal,
    action,
    resource_type,
    resource_id,
    now,
    result="succeeded",
    reason_code=None,
    before=None,
    after=None,
    metadata=None,
):
    # Normalize a principal + action into a storable audit row (camelCase domain
    # dict). Roles/org/region are snapshotted so the trail stays accurate even if
    # the actor's access changes later.
    principal = principal or {}
    return {
        "id": str(uuid.uuid4()),
        "occurredAt": now,
        "actorUserId": principal.get("userId"),
        "sessionId": principal.get("sessionId") or None,
        "rolesSnapshot": list(principal.get("roles") or []),
        "organizationIdsSnapshot": list(principal.get("organizationIds") or []),
        "regionIdsSnapshot": list(principal.get("regionIds") or []),
        "action": action,
        "resourceType": resource_type,
        "resourceId": str(resource_id) if resource_id is not None else None,
        "result": result if result in AUDIT_RESULTS else "succeeded",
        "reasonCode": reason_code,
        "beforeSummary": before or {},
        "afterSummary": after or {},
        "metadata": metadata or {},
        "createdAt": now,
    }


class RdsDataAuditLogRepository:
    def __init__(
        self,
        rds_client=None,
        table=None,
        users_table=None,
        proposals_table=None,
        monthly_destinations_table=None,
        publish_jobs_table=None,
        notices_table=None,
        policies_table=None,
        high_risk_requests_table=None,
    ):
        self.rds = rds_client or create_database_client()
        self.table = table or os.environ.get("ADMIN_AUDIT_LOGS_TABLE_NAME", "admin_audit_logs")
        self.users_table = users_table or os.environ.get("USERS_TABLE_NAME", "users")
        self.proposals_table = proposals_table or os.environ.get(
            "ADMIN_DATA_PROPOSALS_TABLE_NAME",
            "admin_data_proposals",
        )
        self.monthly_destinations_table = monthly_destinations_table or os.environ.get(
            "MONTHLY_CURATED_DESTINATIONS_TABLE_NAME",
            "monthly_curated_destinations",
        )
        self.publish_jobs_table = publish_jobs_table or os.environ.get(
            "ADMIN_PUBLISH_JOBS_TABLE_NAME",
            "admin_publish_jobs",
        )
        self.notices_table = notices_table or os.environ.get("ADMIN_NOTICES_TABLE_NAME", "admin_notices")
        self.policies_table = policies_table or os.environ.get(
            "ADMIN_RECOMMENDATION_POLICIES_TABLE_NAME",
            "admin_recommendation_policies",
        )
        self.high_risk_requests_table = high_risk_requests_table or os.environ.get(
            "ADMIN_HIGH_RISK_REQUESTS_TABLE_NAME",
            "admin_high_risk_change_requests",
        )

    @classmethod
    def from_env(cls):
        return cls()

    def record(self, entry, transaction=None, strict=False):
        # Ordinary actions remain best-effort. High-risk changes pass their open
        # transaction with strict=True so the business mutation and audit row
        # commit or roll back together.
        try:
            (transaction or self.rds).execute(
                f"""
                INSERT INTO {self.table}
                  (id, occurred_at, actor_user_id, session_id, roles_snapshot,
                   organization_ids_snapshot, region_ids_snapshot, action, resource_type,
                   resource_id, result, reason_code, request_id, before_summary_json,
                   after_summary_json, metadata_json, created_at)
                VALUES
                  (:id, :occurred_at, :actor_user_id, :session_id, :roles_snapshot,
                   :organization_ids_snapshot, :region_ids_snapshot, :action, :resource_type,
                   :resource_id, :result, :reason_code, :request_id, :before_summary_json,
                   :after_summary_json, :metadata_json, :created_at)
                """,
                _row_params(entry),
                include_result_metadata=False,
            )
        except Exception:
            LOGGER.exception("Failed to persist admin audit log (action=%s)", entry.get("action"))
            if strict:
                raise
        return entry

    def list(self, action=None, resource_type=None, result=None, actor_user_id=None, limit=50):
        clauses = []
        params = {}
        if action:
            clauses.append("action = :action")
            params["action"] = action
        if resource_type:
            clauses.append("resource_type = :resource_type")
            params["resource_type"] = resource_type
        if result:
            clauses.append("result = :result")
            params["result"] = result
        if actor_user_id:
            clauses.append("actor_user_id = :actor_user_id")
            params["actor_user_id"] = actor_user_id
        rows = self.rds.fetch_all(
            f"""
            SELECT * FROM {self.table}
            {(' WHERE ' + ' AND '.join(clauses)) if clauses else ''}
            ORDER BY occurred_at DESC
            LIMIT :limit
            """,
            {**params, "limit": int(limit)},
        )
        entries = [_entry_from_row(row) for row in rows]
        self._hydrate_display_fields(entries)
        return entries

    def _hydrate_display_fields(self, entries):
        actor_map = self._fetch_actor_display_map({entry.get("actorUserId") for entry in entries})
        resource_maps = self._fetch_resource_display_maps(entries)
        for entry in entries:
            actor = actor_map.get(entry.get("actorUserId")) or {}
            entry["actorDisplayName"] = actor.get("displayName")
            entry["actorEmail"] = actor.get("email")

            resource_type = entry.get("resourceType")
            if resource_type == "admin_mfa":
                entry["resourceDisplayName"] = "관리자 추가 인증"
                continue
            entry["resourceDisplayName"] = (
                resource_maps.get(resource_type, {}).get(entry.get("resourceId"))
                if resource_type
                else None
            )

    def _fetch_actor_display_map(self, actor_ids):
        actor_ids = _non_empty_strings(actor_ids)
        if not actor_ids:
            return {}
        try:
            rows = self.rds.fetch_all(
                f"""
                SELECT id, display_name, nickname, email, status
                FROM {self.users_table}
                WHERE id IN ({_placeholders("actor", actor_ids)})
                """,
                _params("actor", actor_ids),
            )
        except Exception as error:
            LOGGER.warning("Failed to hydrate admin audit actor display fields: %s", error)
            return {}
        return {str(row.get("id")): _actor_display_from_row(row) for row in rows}

    def _fetch_resource_display_maps(self, entries):
        by_type = {}
        for entry in entries:
            resource_type = entry.get("resourceType")
            resource_id = entry.get("resourceId")
            if resource_type and resource_id:
                by_type.setdefault(resource_type, set()).add(resource_id)

        display_maps = {}
        display_maps["data_proposal"] = self._fetch_display_map(
            "data_proposal",
            self.proposals_table,
            by_type.get("data_proposal"),
            "id, title, proposal_code",
            lambda row: _join_display(row.get("title"), row.get("proposal_code")),
        )
        display_maps["monthly_destination"] = self._fetch_display_map(
            "monthly_destination",
            self.monthly_destinations_table,
            by_type.get("monthly_destination"),
            "id, city_name, curation_month",
            lambda row: _join_display(row.get("city_name"), row.get("curation_month")),
        )
        display_maps["publish_job"] = self._fetch_display_map(
            "publish_job",
            self.publish_jobs_table,
            by_type.get("publish_job"),
            "id, job_type, status",
            lambda row: _join_display(row.get("job_type"), row.get("status")),
        )
        display_maps["notice"] = self._fetch_display_map(
            "notice",
            self.notices_table,
            by_type.get("notice"),
            "id, title",
            lambda row: _clean_text(row.get("title")),
        )
        display_maps["recommendation_policy"] = self._fetch_display_map(
            "recommendation_policy",
            self.policies_table,
            by_type.get("recommendation_policy"),
            "id, title, policy_key",
            lambda row: _clean_text(row.get("title")) or _clean_text(row.get("policy_key")),
        )
        display_maps["high_risk_request"] = self._fetch_display_map(
            "high_risk_request",
            self.high_risk_requests_table,
            by_type.get("high_risk_request"),
            "id, operation_type, reason",
            lambda row: _join_display(row.get("operation_type"), _truncate(row.get("reason"), 80)),
        )
        return display_maps

    def _fetch_display_map(self, resource_type, table, resource_ids, columns, display_fn):
        resource_ids = _non_empty_strings(resource_ids)
        if not resource_ids:
            return {}
        try:
            rows = self.rds.fetch_all(
                f"""
                SELECT {columns}
                FROM {table}
                WHERE id IN ({_placeholders("resource", resource_ids)})
                """,
                _params("resource", resource_ids),
            )
        except Exception as error:
            LOGGER.warning("Failed to hydrate admin audit %s display fields: %s", resource_type, error)
            return {}
        return {
            str(row.get("id")): display_fn(row)
            for row in rows
            if row.get("id") is not None and display_fn(row) is not None
        }


class InMemoryAuditLogRepository:
    def __init__(self):
        self.entries = []

    def record(self, entry, transaction=None, strict=False):
        self.entries.append(dict(entry))
        return dict(entry)

    def list(self, action=None, resource_type=None, result=None, actor_user_id=None, limit=50):
        items = [
            entry
            for entry in self.entries
            if (not action or entry.get("action") == action)
            and (not resource_type or entry.get("resourceType") == resource_type)
            and (not result or entry.get("result") == result)
            and (not actor_user_id or entry.get("actorUserId") == actor_user_id)
        ]
        items.sort(key=lambda entry: entry.get("occurredAt") or "", reverse=True)
        return [dict(entry) for entry in items[:limit]]


def _row_params(entry):
    return {
        "id": entry.get("id"),
        "occurred_at": entry.get("occurredAt"),
        "actor_user_id": entry.get("actorUserId"),
        "session_id": entry.get("sessionId"),
        "roles_snapshot": json_dumps(entry.get("rolesSnapshot") or []),
        "organization_ids_snapshot": json_dumps(entry.get("organizationIdsSnapshot") or []),
        "region_ids_snapshot": json_dumps(entry.get("regionIdsSnapshot") or []),
        "action": entry.get("action"),
        "resource_type": entry.get("resourceType"),
        "resource_id": entry.get("resourceId"),
        "result": entry.get("result"),
        "reason_code": entry.get("reasonCode"),
        "request_id": entry.get("requestId"),
        "before_summary_json": json_dumps(entry.get("beforeSummary") or {}),
        "after_summary_json": json_dumps(entry.get("afterSummary") or {}),
        "metadata_json": json_dumps(entry.get("metadata") or {}),
        "created_at": entry.get("createdAt"),
    }


def _entry_from_row(row):
    return {
        "id": row.get("id"),
        "occurredAt": row.get("occurred_at"),
        "actorUserId": row.get("actor_user_id"),
        "actorDisplayName": row.get("actor_display_name"),
        "actorEmail": row.get("actor_email"),
        "sessionId": row.get("session_id"),
        "rolesSnapshot": json_loads(row.get("roles_snapshot"), default=[]),
        "organizationIdsSnapshot": json_loads(row.get("organization_ids_snapshot"), default=[]),
        "regionIdsSnapshot": json_loads(row.get("region_ids_snapshot"), default=[]),
        "action": row.get("action"),
        "resourceType": row.get("resource_type"),
        "resourceId": row.get("resource_id"),
        "resourceDisplayName": row.get("resource_display_name"),
        "result": row.get("result"),
        "reasonCode": row.get("reason_code"),
        "beforeSummary": json_loads(row.get("before_summary_json"), default={}),
        "afterSummary": json_loads(row.get("after_summary_json"), default={}),
        "metadata": json_loads(row.get("metadata_json"), default={}),
        "createdAt": row.get("created_at"),
    }


def _non_empty_strings(values):
    return sorted({str(value) for value in (values or []) if value not in (None, "")})


def _placeholders(prefix, values):
    return ", ".join(f":{prefix}_{index}" for index, _ in enumerate(values))


def _params(prefix, values):
    return {f"{prefix}_{index}": value for index, value in enumerate(values)}


def _actor_display_from_row(row):
    status = row.get("status") or "active"
    if status != "active":
        return {"displayName": "탈퇴/삭제 사용자", "email": None}
    return {
        "displayName": _clean_text(row.get("display_name")) or _clean_text(row.get("nickname")),
        "email": _clean_text(row.get("email")),
    }


def _join_display(primary, secondary):
    primary = _clean_text(primary)
    secondary = _clean_text(secondary)
    if primary and secondary:
        return f"{primary} ({secondary})"
    return primary or secondary


def _truncate(value, max_length):
    value = _clean_text(value)
    if value is None or len(value) <= max_length:
        return value
    return value[: max_length - 3].rstrip() + "..."


def _clean_text(value):
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    return value or None


# EOF: src/admin/audit_logs_repository.py
