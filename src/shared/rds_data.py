import json
import os
from contextlib import contextmanager


class RdsDataConfigurationError(Exception):
    pass


class RdsDataClient:
    def __init__(self, cluster_arn=None, secret_arn=None, database=None, boto3_client=None):
        self.cluster_arn = cluster_arn or os.environ.get("AURORA_CLUSTER_ARN")
        self.secret_arn = secret_arn or os.environ.get("AURORA_SECRET_ARN")
        self.database = database or os.environ.get("AURORA_DATABASE_NAME")
        if not self.cluster_arn or not self.secret_arn or not self.database:
            raise RdsDataConfigurationError("Aurora Data API configuration is missing")

        self.client = boto3_client or _boto3_client()

    def execute(self, sql, parameters=None, include_result_metadata=True):
        request = {
            "resourceArn": self.cluster_arn,
            "secretArn": self.secret_arn,
            "database": self.database,
            "sql": sql,
            "parameters": [_parameter(name, value) for name, value in (parameters or {}).items()],
            "includeResultMetadata": include_result_metadata,
        }
        return self.client.execute_statement(**request)

    def fetch_one(self, sql, parameters=None):
        rows = self.fetch_all(sql, parameters)
        return rows[0] if rows else None

    def fetch_all(self, sql, parameters=None):
        response = self.execute(sql, parameters, include_result_metadata=True)
        return records_to_dicts(response)

    @contextmanager
    def transaction(self):
        response = self.client.begin_transaction(
            resourceArn=self.cluster_arn,
            secretArn=self.secret_arn,
            database=self.database,
        )
        transaction_id = response["transactionId"]
        transaction = _RdsDataTransaction(self, transaction_id)
        try:
            yield transaction
            self.client.commit_transaction(
                resourceArn=self.cluster_arn,
                secretArn=self.secret_arn,
                transactionId=transaction_id,
            )
        except Exception:
            self.client.rollback_transaction(
                resourceArn=self.cluster_arn,
                secretArn=self.secret_arn,
                transactionId=transaction_id,
            )
            raise


class _RdsDataTransaction:
    def __init__(self, owner, transaction_id):
        self.owner = owner
        self.transaction_id = transaction_id

    def execute(self, sql, parameters=None, include_result_metadata=True):
        request = {
            "resourceArn": self.owner.cluster_arn,
            "secretArn": self.owner.secret_arn,
            "database": self.owner.database,
            "transactionId": self.transaction_id,
            "sql": sql,
            "parameters": [_parameter(name, value) for name, value in (parameters or {}).items()],
            "includeResultMetadata": include_result_metadata,
        }
        return self.owner.client.execute_statement(**request)

    def fetch_one(self, sql, parameters=None):
        rows = self.fetch_all(sql, parameters)
        return rows[0] if rows else None

    def fetch_all(self, sql, parameters=None):
        return records_to_dicts(self.execute(sql, parameters, include_result_metadata=True))


def records_to_dicts(response):
    metadata = response.get("columnMetadata") or []
    records = response.get("records") or []
    columns = [column.get("name") for column in metadata]
    return [
        {
            column: _field_value(field)
            for column, field in zip(columns, record)
        }
        for record in records
    ]


def json_dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def json_loads(value, default=None):
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _parameter(name, value):
    parameter = {"name": name, "value": _value(value)}
    return parameter


def _value(value):
    if value is None:
        return {"isNull": True}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"longValue": value}
    if isinstance(value, float):
        return {"doubleValue": value}
    return {"stringValue": str(value)}


def _field_value(field):
    if field.get("isNull"):
        return None
    for key in ("stringValue", "longValue", "doubleValue", "booleanValue"):
        if key in field:
            return field[key]
    return None


def _boto3_client():
    try:
        import boto3
    except ImportError as error:
        raise RdsDataConfigurationError("boto3 is required for Aurora Data API access") from error
    return boto3.client("rds-data")
