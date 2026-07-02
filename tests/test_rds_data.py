import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shared.rds_data import RdsDataClient


class FakeRdsDataApi:
    def __init__(self):
        self.calls = []

    def begin_transaction(self, **request):
        self.calls.append(("begin", request))
        return {"transactionId": "tx-1"}

    def execute_statement(self, **request):
        self.calls.append(("execute", request))
        return {"numberOfRecordsUpdated": 1}

    def commit_transaction(self, **request):
        self.calls.append(("commit", request))

    def rollback_transaction(self, **request):
        self.calls.append(("rollback", request))


class RdsDataTransactionTests(unittest.TestCase):
    def client(self, api):
        return RdsDataClient("cluster", "secret", "lovv", boto3_client=api)

    def test_transaction_begins_executes_and_commits_with_same_id(self):
        api = FakeRdsDataApi()
        with self.client(api).transaction() as transaction:
            transaction.execute("UPDATE users SET status = :status", {"status": "active"}, False)

        self.assertEqual([call[0] for call in api.calls], ["begin", "execute", "commit"])
        self.assertEqual(api.calls[1][1]["transactionId"], "tx-1")
        self.assertEqual(api.calls[2][1]["transactionId"], "tx-1")

    def test_transaction_rolls_back_and_reraises(self):
        api = FakeRdsDataApi()
        with self.assertRaisesRegex(RuntimeError, "force rollback"):
            with self.client(api).transaction() as transaction:
                transaction.execute("UPDATE users SET status = 'active'", {}, False)
                raise RuntimeError("force rollback")

        self.assertEqual([call[0] for call in api.calls], ["begin", "execute", "rollback"])
        self.assertEqual(api.calls[-1][1]["transactionId"], "tx-1")


if __name__ == "__main__":
    unittest.main()
