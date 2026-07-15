# @file src/admin/high_risk_repository.py
# @description Coordinates approval and execution of high-risk administrative changes.
# @author JJonyeok2
# @lastModified 2026-07-15

import copy
import os
import uuid

from admin.audit_logs_repository import RdsDataAuditLogRepository, build_audit_entry
from admin.publish_jobs_repository import PUBLISH_JOB_TYPES
from auth.authz_cache_repository import DynamoDbAuthzCacheRepository
from shared.database import create_database_client
from shared.rds_data import json_dumps, json_loads


OPERATION_TYPES = {
    "role_grant",
    "role_revoke",
    "region_grant",
    "region_revoke",
    "bulk_publish",
}
ASSIGNABLE_ROLES = {
    "R-ADMIN",
    "R-SUPER-ADMIN",
    "R-DATA-PROVIDER",
    "R-LOCAL-OPERATOR",
}
REQUEST_STATUSES = {"pending", "executed", "rejected"}
BULK_PUBLISH_MINIMUM = 10
BULK_PUBLISH_MAXIMUM = 100


class HighRiskChangeError(Exception):
    def __init__(self, status_code, code, message):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class RdsDataHighRiskChangeRepository:
    def __init__(
        self,
        rds_client=None,
        audit_repository=None,
        authz_cache=None,
        requests_table=None,
        roles_table=None,
        regions_table=None,
        users_table=None,
        destinations_table=None,
        publish_jobs_table=None,
    ):
        self.rds = rds_client or create_database_client()
        self.audit = audit_repository or RdsDataAuditLogRepository(rds_client=self.rds)
        self.authz_cache = authz_cache
        self.requests_table = requests_table or os.environ.get(
            "ADMIN_HIGH_RISK_REQUESTS_TABLE_NAME", "admin_high_risk_change_requests"
        )
        self.roles_table = roles_table or os.environ.get(
            "USER_ROLE_ASSIGNMENTS_TABLE_NAME", "user_role_assignments"
        )
        self.regions_table = regions_table or os.environ.get(
            "USER_REGION_ASSIGNMENTS_TABLE_NAME", "user_region_assignments"
        )
        self.users_table = users_table or os.environ.get("USERS_TABLE_NAME", "users")
        self.destinations_table = destinations_table or os.environ.get(
            "MONTHLY_CURATED_DESTINATIONS_TABLE_NAME", "monthly_curated_destinations"
        )
        self.publish_jobs_table = publish_jobs_table or os.environ.get(
            "ADMIN_PUBLISH_JOBS_TABLE_NAME", "admin_publish_jobs"
        )

    @classmethod
    def from_env(cls):
        cache = DynamoDbAuthzCacheRepository.from_env()
        return cls(authz_cache=cache if cache.enabled else None)

    def create(self, principal, payload, now):
        normalized = validate_high_risk_payload(payload)
        request = {
            "id": str(uuid.uuid4()),
            "operationType": normalized["operationType"],
            "targetUserId": normalized.get("targetUserId"),
            "payload": normalized,
            "status": "pending",
            "reason": normalized["reason"],
            "requestedBy": principal["userId"],
            "decidedBy": None,
            "decisionReason": None,
            "requestedAt": now,
            "decidedAt": None,
            "executedAt": None,
            "executionSummary": {},
            "updatedAt": now,
        }
        with self.rds.transaction() as transaction:
            _ensure_user_exists(transaction, self.users_table, request.get("targetUserId"))
            self._insert_request(transaction, request)
            self._record_audit(
                transaction,
                principal,
                "high_risk_request.create",
                request,
                now,
                after={"status": "pending", "operationType": request["operationType"]},
            )
        return request

    def list(self, status=None, operation_type=None, limit=50):
        clauses = []
        params = {}
        if status:
            if status not in REQUEST_STATUSES:
                raise HighRiskChangeError(400, "INVALID_HIGH_RISK_FILTER", "status is invalid")
            clauses.append("status = :status")
            params["status"] = status
        if operation_type:
            if operation_type not in OPERATION_TYPES:
                raise HighRiskChangeError(400, "INVALID_HIGH_RISK_FILTER", "operationType is invalid")
            clauses.append("operation_type = :operation_type")
            params["operation_type"] = operation_type
        rows = self.rds.fetch_all(
            f"""
            SELECT * FROM {self.requests_table}
            {(' WHERE ' + ' AND '.join(clauses)) if clauses else ''}
            ORDER BY requested_at DESC
            LIMIT :limit
            """,
            {**params, "limit": int(limit)},
        )
        return [_request_from_row(row) for row in rows]

    def approve(self, request_id, principal, now, decision_reason=None):
        target_user_id = None
        request = None
        try:
            # Lock the request, apply the privileged change, and persist both
            # audit records atomically so no executed change can lack evidence.
            with self.rds.transaction() as transaction:
                request = self._locked_request(transaction, request_id)
                self._validate_decision(request, principal)
                summary = self._execute(transaction, request, principal, now)
                self._finish(
                    transaction,
                    request_id,
                    "executed",
                    principal["userId"],
                    decision_reason,
                    now,
                    summary,
                )
                request.update(
                    status="executed",
                    decidedBy=principal["userId"],
                    decisionReason=decision_reason,
                    decidedAt=now,
                    executedAt=now,
                    executionSummary=summary,
                    updatedAt=now,
                )
                self._record_audit(
                    transaction,
                    principal,
                    f"{request['operationType']}.execute",
                    request,
                    now,
                    after=summary,
                )
                self._record_audit(
                    transaction,
                    principal,
                    "high_risk_request.approve",
                    request,
                    now,
                    after={"status": "executed", "operationType": request["operationType"]},
                )
                target_user_id = request.get("targetUserId")
        except Exception as error:
            _attach_failure_context(error, request, request_id)
            raise
        # Invalidate only after commit; readers must never observe authorization
        # derived from a transaction that may still roll back.
        if target_user_id and request["operationType"].startswith(("role_", "region_")):
            self._invalidate_authz(target_user_id)
        return request

    def reject(self, request_id, principal, now, decision_reason):
        if not isinstance(decision_reason, str) or not decision_reason.strip():
            raise HighRiskChangeError(400, "INVALID_HIGH_RISK_DECISION", "decisionReason is required")
        decision_reason = decision_reason.strip()
        with self.rds.transaction() as transaction:
            request = self._locked_request(transaction, request_id)
            self._validate_decision(request, principal)
            self._finish(
                transaction,
                request_id,
                "rejected",
                principal["userId"],
                decision_reason,
                now,
                {},
            )
            request.update(
                status="rejected",
                decidedBy=principal["userId"],
                decisionReason=decision_reason,
                decidedAt=now,
                updatedAt=now,
            )
            self._record_audit(
                transaction,
                principal,
                "high_risk_request.reject",
                request,
                now,
                after={"status": "rejected", "operationType": request["operationType"]},
                result="denied",
                reason_code="OPERATOR_REJECTED",
            )
        return request

    def _insert_request(self, transaction, request):
        transaction.execute(
            f"""
            INSERT INTO {self.requests_table}
              (id, operation_type, target_user_id, payload_json, status, reason,
               requested_by, decided_by, decision_reason, requested_at, decided_at,
               executed_at, execution_summary_json, updated_at)
            VALUES
              (:id, :operation_type, :target_user_id, :payload_json, :status, :reason,
               :requested_by, :decided_by, :decision_reason, :requested_at, :decided_at,
               :executed_at, :execution_summary_json, :updated_at)
            """,
            _request_params(request),
            include_result_metadata=False,
        )

    def _locked_request(self, transaction, request_id):
        row = transaction.fetch_one(
            f"SELECT * FROM {self.requests_table} WHERE id = :id FOR UPDATE",
            {"id": request_id},
        )
        if not row:
            raise HighRiskChangeError(404, "HIGH_RISK_REQUEST_NOT_FOUND", "High-risk request was not found")
        return _request_from_row(row)

    def _validate_decision(self, request, principal):
        if request.get("status") != "pending":
            raise HighRiskChangeError(409, "HIGH_RISK_REQUEST_ALREADY_DECIDED", "High-risk request was already decided")
        if request.get("requestedBy") == principal.get("userId"):
            raise HighRiskChangeError(409, "SELF_APPROVAL_FORBIDDEN", "Requester cannot decide their own high-risk request")

    def _finish(self, transaction, request_id, status, actor_id, reason, now, summary):
        response = transaction.execute(
            f"""
            UPDATE {self.requests_table}
            SET status = :status, decided_by = :decided_by, decision_reason = :decision_reason,
                decided_at = :decided_at, executed_at = :executed_at,
                execution_summary_json = :execution_summary_json, updated_at = :updated_at
            WHERE id = :id AND status = 'pending'
            """,
            {
                "id": request_id,
                "status": status,
                "decided_by": actor_id,
                "decision_reason": reason,
                "decided_at": now,
                "executed_at": now if status == "executed" else None,
                "execution_summary_json": json_dumps(summary),
                "updated_at": now,
            },
            include_result_metadata=False,
        )
        if _updated_count(response) != 1:
            raise HighRiskChangeError(409, "HIGH_RISK_REQUEST_STATE_CONFLICT", "High-risk request state changed")

    def _execute(self, transaction, request, principal, now):
        operation = request["operationType"]
        payload = request["payload"]
        if operation == "role_grant":
            return self._grant_role(transaction, payload, principal, now)
        if operation == "role_revoke":
            return self._revoke_role(transaction, payload, now)
        if operation == "region_grant":
            return self._grant_region(transaction, payload, principal, now)
        if operation == "region_revoke":
            return self._revoke_region(transaction, payload, now)
        return self._bulk_publish(transaction, payload, principal, now)

    def _grant_role(self, transaction, payload, principal, now):
        existing = transaction.fetch_one(
            f"""
            SELECT id FROM {self.roles_table}
            WHERE user_id = :user_id AND role_code = :role_code
              AND organization_id <=> :organization_id AND status = 'active'
            FOR UPDATE
            """,
            {
                "user_id": payload["targetUserId"],
                "role_code": payload["roleCode"],
                "organization_id": payload.get("organizationId"),
            },
        )
        if existing:
            raise HighRiskChangeError(409, "DUPLICATE_ACTIVE_ASSIGNMENT", "Active role assignment already exists")
        response = transaction.execute(
            f"""
            INSERT INTO {self.roles_table}
              (id, user_id, role_code, organization_id, status, valid_from, valid_until,
               granted_by, grant_reason, created_at, updated_at)
            VALUES
              (:id, :user_id, :role_code, :organization_id, 'active', :valid_from, :valid_until,
               :granted_by, :grant_reason, :created_at, :updated_at)
            """,
            {
                "id": str(uuid.uuid4()),
                "user_id": payload["targetUserId"],
                "role_code": payload["roleCode"],
                "organization_id": payload.get("organizationId"),
                "valid_from": now,
                "valid_until": payload.get("validUntil"),
                "granted_by": principal["userId"],
                "grant_reason": payload["reason"],
                "created_at": now,
                "updated_at": now,
            },
            include_result_metadata=False,
        )
        return {"assignmentType": "role", "roleCode": payload["roleCode"], "updated": _updated_count(response)}

    def _revoke_role(self, transaction, payload, now):
        if payload["roleCode"] == "R-SUPER-ADMIN":
            # The row lock serializes concurrent revocations that could each
            # otherwise believe another active super admin remains.
            count = transaction.fetch_one(
                f"""
                SELECT COUNT(*) AS active_count FROM {self.roles_table}
                WHERE role_code = 'R-SUPER-ADMIN' AND organization_id IS NULL
                  AND status = 'active' AND valid_from <= UTC_TIMESTAMP(3)
                  AND (valid_until IS NULL OR valid_until > UTC_TIMESTAMP(3))
                FOR UPDATE
                """
            )
            if int((count or {}).get("active_count") or 0) <= 1:
                raise HighRiskChangeError(409, "LAST_SUPER_ADMIN_REQUIRED", "The last active super admin cannot be revoked")
        response = transaction.execute(
            f"""
            UPDATE {self.roles_table}
            SET status = 'revoked', updated_at = :updated_at
            WHERE user_id = :user_id AND role_code = :role_code
              AND organization_id <=> :organization_id AND status = 'active'
            """,
            {
                "updated_at": now,
                "user_id": payload["targetUserId"],
                "role_code": payload["roleCode"],
                "organization_id": payload.get("organizationId"),
            },
            include_result_metadata=False,
        )
        if _updated_count(response) != 1:
            raise HighRiskChangeError(409, "ACTIVE_ASSIGNMENT_NOT_FOUND", "Active role assignment was not found")
        return {"assignmentType": "role", "roleCode": payload["roleCode"], "updated": 1}

    def _grant_region(self, transaction, payload, principal, now):
        existing = transaction.fetch_one(
            f"""
            SELECT id FROM {self.regions_table}
            WHERE user_id = :user_id AND region_id = :region_id
              AND organization_id <=> :organization_id AND status = 'active'
            FOR UPDATE
            """,
            {
                "user_id": payload["targetUserId"],
                "region_id": payload["regionId"],
                "organization_id": payload.get("organizationId"),
            },
        )
        if existing:
            raise HighRiskChangeError(409, "DUPLICATE_ACTIVE_ASSIGNMENT", "Active region assignment already exists")
        response = transaction.execute(
            f"""
            INSERT INTO {self.regions_table}
              (id, user_id, region_id, organization_id, status, valid_from, valid_until,
               granted_by, grant_reason, created_at, updated_at)
            VALUES
              (:id, :user_id, :region_id, :organization_id, 'active', :valid_from, :valid_until,
               :granted_by, :grant_reason, :created_at, :updated_at)
            """,
            {
                "id": str(uuid.uuid4()),
                "user_id": payload["targetUserId"],
                "region_id": payload["regionId"],
                "organization_id": payload.get("organizationId"),
                "valid_from": now,
                "valid_until": payload.get("validUntil"),
                "granted_by": principal["userId"],
                "grant_reason": payload["reason"],
                "created_at": now,
                "updated_at": now,
            },
            include_result_metadata=False,
        )
        return {"assignmentType": "region", "regionId": payload["regionId"], "updated": _updated_count(response)}

    def _revoke_region(self, transaction, payload, now):
        response = transaction.execute(
            f"""
            UPDATE {self.regions_table}
            SET status = 'revoked', updated_at = :updated_at
            WHERE user_id = :user_id AND region_id = :region_id
              AND organization_id <=> :organization_id AND status = 'active'
            """,
            {
                "updated_at": now,
                "user_id": payload["targetUserId"],
                "region_id": payload["regionId"],
                "organization_id": payload.get("organizationId"),
            },
            include_result_metadata=False,
        )
        if _updated_count(response) != 1:
            raise HighRiskChangeError(409, "ACTIVE_ASSIGNMENT_NOT_FOUND", "Active region assignment was not found")
        return {"assignmentType": "region", "regionId": payload["regionId"], "updated": 1}

    def _bulk_publish(self, transaction, payload, principal, now):
        destination_ids = payload["destinationIds"]
        placeholders = ", ".join(f":destination_{index}" for index in range(len(destination_ids)))
        params = {f"destination_{index}": value for index, value in enumerate(destination_ids)}
        rows = transaction.fetch_all(
            f"SELECT id, status FROM {self.destinations_table} WHERE id IN ({placeholders}) FOR UPDATE",
            params,
        )
        by_id = {row["id"]: row for row in rows}
        missing = [destination_id for destination_id in destination_ids if destination_id not in by_id]
        if missing:
            raise HighRiskChangeError(404, "MONTHLY_DESTINATION_NOT_FOUND", "One or more destinations were not found")
        invalid = [item["id"] for item in rows if item.get("status") not in {"candidate", "scheduled", "hidden"}]
        if invalid:
            raise HighRiskChangeError(409, "MONTHLY_TRANSITION_FORBIDDEN", "One or more destinations cannot be published")
        for destination_id in destination_ids:
            transaction.execute(
                f"""
                UPDATE {self.destinations_table}
                SET status = 'published', publish_reason = :reason, published_by = :published_by,
                    published_at = :published_at, updated_at = :updated_at
                WHERE id = :id
                """,
                {
                    "id": destination_id,
                    "reason": payload["reason"],
                    "published_by": principal["userId"],
                    "published_at": now,
                    "updated_at": now,
                },
                include_result_metadata=False,
            )
            for job_type in PUBLISH_JOB_TYPES:
                transaction.execute(
                    f"""
                    INSERT INTO {self.publish_jobs_table}
                      (id, proposal_id, monthly_curated_destination_id, job_type, status,
                       attempt_count, last_error_code, last_error_message, requested_by,
                       started_at, finished_at, created_at, updated_at)
                    VALUES
                      (:id, NULL, :destination_id, :job_type, 'queued', 0, NULL, NULL,
                       :requested_by, NULL, NULL, :created_at, :updated_at)
                    """,
                    {
                        "id": str(uuid.uuid4()),
                        "destination_id": destination_id,
                        "job_type": job_type,
                        "requested_by": principal["userId"],
                        "created_at": now,
                        "updated_at": now,
                    },
                    include_result_metadata=False,
                )
        return {"publishedCount": len(destination_ids), "reflectionJobCount": len(destination_ids) * len(PUBLISH_JOB_TYPES)}

    def _record_audit(
        self, transaction, principal, action, request, now, after,
        result="succeeded", reason_code=None,
    ):
        entry = build_audit_entry(
            principal,
            action,
            "high_risk_request",
            request["id"],
            now,
            result=result,
            reason_code=reason_code,
            after=after,
            metadata={"operationType": request["operationType"], "targetUserId": request.get("targetUserId")},
        )
        self.audit.record(entry, transaction=transaction, strict=True)

    def _invalidate_authz(self, user_id):
        if self.authz_cache is not None:
            self.authz_cache.invalidate(user_id)


class InMemoryHighRiskChangeRepository:
    def __init__(self, audit_repository=None, destinations=None):
        self.audit = audit_repository
        self.requests = {}
        self.role_assignments = set()
        self.region_assignments = set()
        self.destinations = destinations if destinations is not None else {}
        self.publish_jobs = []

    def create(self, principal, payload, now):
        normalized = validate_high_risk_payload(payload)
        request_id = f"high-risk-{len(self.requests) + 1}"
        request = {
            "id": request_id,
            "operationType": normalized["operationType"],
            "targetUserId": normalized.get("targetUserId"),
            "payload": normalized,
            "status": "pending",
            "reason": normalized["reason"],
            "requestedBy": principal["userId"],
            "decidedBy": None,
            "decisionReason": None,
            "requestedAt": now,
            "decidedAt": None,
            "executedAt": None,
            "executionSummary": {},
            "updatedAt": now,
        }
        self.requests[request_id] = request
        self._record_audit(
            principal,
            "high_risk_request.create",
            request,
            now,
            after={"status": "pending", "operationType": request["operationType"]},
        )
        return dict(request)

    def list(self, status=None, operation_type=None, limit=50):
        items = [
            dict(request)
            for request in self.requests.values()
            if (not status or request["status"] == status)
            and (not operation_type or request["operationType"] == operation_type)
        ]
        return items[:limit]

    def approve(self, request_id, principal, now, decision_reason=None):
        request = None
        snapshot = self._snapshot()
        try:
            request = self._pending(request_id, principal)
            payload = request["payload"]
            operation = request["operationType"]
            if operation == "role_grant":
                key = (payload["targetUserId"], payload["roleCode"], payload.get("organizationId"))
                if key in self.role_assignments:
                    raise HighRiskChangeError(409, "DUPLICATE_ACTIVE_ASSIGNMENT", "Active role assignment already exists")
                self.role_assignments.add(key)
                summary = {"assignmentType": "role", "roleCode": payload["roleCode"], "updated": 1}
            elif operation == "role_revoke":
                key = (payload["targetUserId"], payload["roleCode"], payload.get("organizationId"))
                if payload["roleCode"] == "R-SUPER-ADMIN":
                    active_super_admins = sum(1 for item in self.role_assignments if item[1:] == ("R-SUPER-ADMIN", None))
                    if active_super_admins <= 1:
                        raise HighRiskChangeError(409, "LAST_SUPER_ADMIN_REQUIRED", "The last active super admin cannot be revoked")
                if key not in self.role_assignments:
                    raise HighRiskChangeError(409, "ACTIVE_ASSIGNMENT_NOT_FOUND", "Active role assignment was not found")
                self.role_assignments.remove(key)
                summary = {"assignmentType": "role", "roleCode": payload["roleCode"], "updated": 1}
            elif operation == "region_grant":
                key = (payload["targetUserId"], payload["regionId"], payload.get("organizationId"))
                if key in self.region_assignments:
                    raise HighRiskChangeError(409, "DUPLICATE_ACTIVE_ASSIGNMENT", "Active region assignment already exists")
                self.region_assignments.add(key)
                summary = {"assignmentType": "region", "regionId": payload["regionId"], "updated": 1}
            elif operation == "region_revoke":
                key = (payload["targetUserId"], payload["regionId"], payload.get("organizationId"))
                if key not in self.region_assignments:
                    raise HighRiskChangeError(409, "ACTIVE_ASSIGNMENT_NOT_FOUND", "Active region assignment was not found")
                self.region_assignments.remove(key)
                summary = {"assignmentType": "region", "regionId": payload["regionId"], "updated": 1}
            else:
                missing = [item for item in payload["destinationIds"] if item not in self.destinations]
                if missing:
                    raise HighRiskChangeError(404, "MONTHLY_DESTINATION_NOT_FOUND", "One or more destinations were not found")
                invalid = [item for item in payload["destinationIds"] if self.destinations[item].get("status") not in {"candidate", "scheduled", "hidden"}]
                if invalid:
                    raise HighRiskChangeError(409, "MONTHLY_TRANSITION_FORBIDDEN", "One or more destinations cannot be published")
                for destination_id in payload["destinationIds"]:
                    self.destinations[destination_id]["status"] = "published"
                    self.destinations[destination_id]["publishedBy"] = principal["userId"]
                    self.publish_jobs.extend((destination_id, job_type) for job_type in PUBLISH_JOB_TYPES)
                summary = {"publishedCount": len(payload["destinationIds"]), "reflectionJobCount": len(self.publish_jobs)}
            request.update(
                status="executed",
                decidedBy=principal["userId"],
                decisionReason=decision_reason,
                decidedAt=now,
                executedAt=now,
                executionSummary=summary,
                updatedAt=now,
            )
            self._record_audit(principal, f"{operation}.execute", request, now, after=summary)
            self._record_audit(
                principal,
                "high_risk_request.approve",
                request,
                now,
                after={"status": "executed", "operationType": request["operationType"]},
            )
            return dict(request)
        except Exception as error:
            self._restore(snapshot)
            _attach_failure_context(error, request, request_id)
            raise

    def reject(self, request_id, principal, now, decision_reason):
        if not isinstance(decision_reason, str) or not decision_reason.strip():
            raise HighRiskChangeError(400, "INVALID_HIGH_RISK_DECISION", "decisionReason is required")
        request = None
        snapshot = self._snapshot()
        try:
            request = self._pending(request_id, principal)
            request.update(
                status="rejected",
                decidedBy=principal["userId"],
                decisionReason=decision_reason.strip(),
                decidedAt=now,
                updatedAt=now,
            )
            self._record_audit(
                principal,
                "high_risk_request.reject",
                request,
                now,
                after={"status": "rejected", "operationType": request["operationType"]},
                result="denied",
                reason_code="OPERATOR_REJECTED",
            )
            return dict(request)
        except Exception as error:
            self._restore(snapshot)
            _attach_failure_context(error, request, request_id)
            raise

    def _pending(self, request_id, principal):
        request = self.requests.get(request_id)
        if not request:
            raise HighRiskChangeError(404, "HIGH_RISK_REQUEST_NOT_FOUND", "High-risk request was not found")
        if request["status"] != "pending":
            raise HighRiskChangeError(409, "HIGH_RISK_REQUEST_ALREADY_DECIDED", "High-risk request was already decided")
        if request["requestedBy"] == principal.get("userId"):
            raise HighRiskChangeError(409, "SELF_APPROVAL_FORBIDDEN", "Requester cannot decide their own high-risk request")
        return request

    def _record_audit(
        self, principal, action, request, now, after,
        result="succeeded", reason_code=None,
    ):
        if self.audit is None:
            return
        entry = build_audit_entry(
            principal,
            action,
            "high_risk_request",
            request["id"],
            now,
            result=result,
            reason_code=reason_code,
            after=after,
            metadata={"operationType": request["operationType"], "targetUserId": request.get("targetUserId")},
        )
        self.audit.record(entry, strict=True)

    def _snapshot(self):
        return {
            "requests": copy.deepcopy(self.requests),
            "role_assignments": set(self.role_assignments),
            "region_assignments": set(self.region_assignments),
            "destinations": copy.deepcopy(self.destinations),
            "publish_jobs": list(self.publish_jobs),
            "audit_entries": copy.deepcopy(getattr(self.audit, "entries", None)),
        }

    def _restore(self, snapshot):
        self.requests.clear()
        self.requests.update(snapshot["requests"])
        self.role_assignments.clear()
        self.role_assignments.update(snapshot["role_assignments"])
        self.region_assignments.clear()
        self.region_assignments.update(snapshot["region_assignments"])
        self.destinations.clear()
        self.destinations.update(snapshot["destinations"])
        self.publish_jobs[:] = snapshot["publish_jobs"]
        if snapshot["audit_entries"] is not None and hasattr(self.audit, "entries"):
            self.audit.entries[:] = snapshot["audit_entries"]


def validate_high_risk_payload(payload):
    if not isinstance(payload, dict):
        raise HighRiskChangeError(400, "INVALID_HIGH_RISK_PAYLOAD", "JSON object body is required")
    operation = payload.get("operationType")
    if operation not in OPERATION_TYPES:
        raise HighRiskChangeError(400, "INVALID_HIGH_RISK_PAYLOAD", "operationType is invalid")
    reason = _required_text(payload.get("reason"), "reason")
    normalized = {"operationType": operation, "reason": reason}
    allowed = {"operationType", "reason"}
    if operation.startswith("role_"):
        normalized["targetUserId"] = _required_text(payload.get("targetUserId"), "targetUserId")
        role_code = payload.get("roleCode")
        if role_code not in ASSIGNABLE_ROLES:
            raise HighRiskChangeError(400, "INVALID_HIGH_RISK_PAYLOAD", "roleCode is invalid")
        normalized["roleCode"] = role_code
        normalized["organizationId"] = _optional_text(payload.get("organizationId"))
        normalized["validUntil"] = _optional_text(payload.get("validUntil")) if operation == "role_grant" else None
        if role_code == "R-SUPER-ADMIN" and normalized["organizationId"] is not None:
            raise HighRiskChangeError(400, "INVALID_HIGH_RISK_PAYLOAD", "R-SUPER-ADMIN must be a global role")
        allowed.update({"targetUserId", "roleCode", "organizationId", "validUntil"})
    elif operation.startswith("region_"):
        normalized["targetUserId"] = _required_text(payload.get("targetUserId"), "targetUserId")
        normalized["regionId"] = _required_text(payload.get("regionId"), "regionId")
        normalized["organizationId"] = _optional_text(payload.get("organizationId"))
        normalized["validUntil"] = _optional_text(payload.get("validUntil")) if operation == "region_grant" else None
        allowed.update({"targetUserId", "regionId", "organizationId", "validUntil"})
    else:
        raw_ids = payload.get("destinationIds")
        if not isinstance(raw_ids, list) or any(not isinstance(item, str) or not item.strip() for item in raw_ids):
            raise HighRiskChangeError(400, "INVALID_HIGH_RISK_PAYLOAD", "destinationIds must be a string array")
        destination_ids = list(dict.fromkeys(item.strip() for item in raw_ids))
        if not BULK_PUBLISH_MINIMUM <= len(destination_ids) <= BULK_PUBLISH_MAXIMUM:
            raise HighRiskChangeError(
                400,
                "INVALID_HIGH_RISK_PAYLOAD",
                f"bulk_publish requires {BULK_PUBLISH_MINIMUM} to {BULK_PUBLISH_MAXIMUM} unique destinationIds",
            )
        normalized["destinationIds"] = destination_ids
        allowed.add("destinationIds")
    if set(payload) - allowed:
        raise HighRiskChangeError(400, "INVALID_HIGH_RISK_PAYLOAD", "Payload contains unsupported fields")
    return normalized


def _ensure_user_exists(transaction, users_table, user_id):
    if user_id and not transaction.fetch_one(f"SELECT id FROM {users_table} WHERE id = :id", {"id": user_id}):
        raise HighRiskChangeError(404, "USER_NOT_FOUND", "User was not found")


def _request_params(request):
    return {
        "id": request["id"],
        "operation_type": request["operationType"],
        "target_user_id": request.get("targetUserId"),
        "payload_json": json_dumps(request["payload"]),
        "status": request["status"],
        "reason": request["reason"],
        "requested_by": request["requestedBy"],
        "decided_by": request.get("decidedBy"),
        "decision_reason": request.get("decisionReason"),
        "requested_at": request["requestedAt"],
        "decided_at": request.get("decidedAt"),
        "executed_at": request.get("executedAt"),
        "execution_summary_json": json_dumps(request.get("executionSummary") or {}),
        "updated_at": request["updatedAt"],
    }


def _request_from_row(row):
    return {
        "id": row.get("id"),
        "operationType": row.get("operation_type"),
        "targetUserId": row.get("target_user_id"),
        "payload": json_loads(row.get("payload_json"), default={}),
        "status": row.get("status"),
        "reason": row.get("reason"),
        "requestedBy": row.get("requested_by"),
        "decidedBy": row.get("decided_by"),
        "decisionReason": row.get("decision_reason"),
        "requestedAt": row.get("requested_at"),
        "decidedAt": row.get("decided_at"),
        "executedAt": row.get("executed_at"),
        "executionSummary": json_loads(row.get("execution_summary_json"), default={}),
        "updatedAt": row.get("updated_at"),
    }


def _updated_count(response):
    return int((response or {}).get("numberOfRecordsUpdated") or 0)


def _attach_failure_context(error, request, request_id):
    """Add non-sensitive request context for the out-of-transaction audit row."""
    try:
        error.request_id = request_id
        if request:
            error.operation_type = request.get("operationType")
            error.target_user_id = request.get("targetUserId")
    except Exception:
        # Never replace the original business or infrastructure exception.
        pass


def _required_text(value, field):
    text = _optional_text(value)
    if not text:
        raise HighRiskChangeError(400, "INVALID_HIGH_RISK_PAYLOAD", f"{field} is required")
    return text


def _optional_text(value):
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise HighRiskChangeError(400, "INVALID_HIGH_RISK_PAYLOAD", "Text fields must be strings")
    return value.strip() or None


# EOF: src/admin/high_risk_repository.py
