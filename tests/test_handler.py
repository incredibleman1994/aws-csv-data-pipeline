import json
from decimal import Decimal

import pytest

from conftest import BUCKET

import handler

MIXED_CSV = """order_id,customer,amount,order_date
1001,Asha,250.50,2026-01-05
1002,Ravi,,2026-01-06
1003,Meera,99,2026-01-07
1004,Kabir,-5,2026-01-08
1005,Isha,40,06/01/2026
"""


def _event(key):
    return {"Records": [{"s3": {"bucket": {"name": BUCKET}, "object": {"key": key}}}]}


def _keys(aws, prefix):
    resp = aws.s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix)
    return [obj["Key"] for obj in resp.get("Contents", [])]


def _messages(aws):
    resp = aws.sqs.receive_message(QueueUrl=aws.queue_url, MaxNumberOfMessages=10)
    return [json.loads(m["Body"])["Message"] for m in resp.get("Messages", [])]


def test_valid_rows_saved_and_invalid_rows_reported(aws):
    aws.s3.put_object(Bucket=BUCKET, Key="incoming/orders.csv", Body=MIXED_CSV.encode())

    handler.lambda_handler(_event("incoming/orders.csv"), None)

    assert aws.table.scan()["Count"] == 2
    assert aws.table.get_item(Key={"order_id": "1001"})["Item"]["amount"] == Decimal("250.50")
    assert _keys(aws, "incoming/") == []
    assert _keys(aws, "processed/") == ["processed/orders.csv"]

    [message] = _messages(aws)
    assert "Rows saved: 2" in message
    assert "Rows skipped: 3" in message
    assert "line 3: amount '' is not a number" in message


def test_file_with_missing_columns_is_rejected(aws):
    aws.s3.put_object(Bucket=BUCKET, Key="incoming/bad.csv", Body=b"order_id,customer\n1,Asha\n")

    handler.lambda_handler(_event("incoming/bad.csv"), None)

    assert aws.table.scan()["Count"] == 0
    assert _keys(aws, "failed/") == ["failed/bad.csv"]
    [message] = _messages(aws)
    assert "missing columns: amount, order_date" in message


@pytest.mark.parametrize(
    "row, reason",
    [
        ({"order_id": "", "customer": "A", "amount": "1", "order_date": "2026-01-01"}, "order_id is empty"),
        ({"order_id": "1", "customer": "", "amount": "1", "order_date": "2026-01-01"}, "customer is empty"),
        ({"order_id": "1", "customer": "A", "amount": "abc", "order_date": "2026-01-01"}, "not a number"),
        ({"order_id": "1", "customer": "A", "amount": "NaN", "order_date": "2026-01-01"}, "greater than zero"),
        ({"order_id": "1", "customer": "A", "amount": "0", "order_date": "2026-01-01"}, "greater than zero"),
        ({"order_id": "1", "customer": "A", "amount": "5", "order_date": "01-01-2026"}, "YYYY-MM-DD"),
    ],
)
def test_validate_row_rejects_bad_input(row, reason):
    item, error = handler.validate_row(row)
    assert item is None
    assert reason in error


def test_validate_row_accepts_good_input():
    item, error = handler.validate_row({"order_id": " 7 ", "customer": "Asha", "amount": "12.5", "order_date": "2026-03-01"})
    assert error is None
    assert item == {"order_id": "7", "customer": "Asha", "amount": Decimal("12.5"), "order_date": "2026-03-01"}
