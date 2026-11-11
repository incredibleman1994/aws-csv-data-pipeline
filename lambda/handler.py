"""Triggered by S3 when a CSV lands in incoming/.

Validates each order row, saves valid rows to DynamoDB, moves the file to
processed/ (or failed/ if it can't be read), and emails a summary via SNS.
"""
import csv
import io
import os
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import unquote_plus

import boto3

REQUIRED_COLUMNS = {"order_id", "customer", "amount", "order_date"}
MAX_ISSUES_SHOWN = 5


def validate_row(row):
    """Return (item, None) for a valid row, or (None, reason) for an invalid one."""
    order_id = (row.get("order_id") or "").strip()
    customer = (row.get("customer") or "").strip()
    raw_amount = (row.get("amount") or "").strip()
    raw_date = (row.get("order_date") or "").strip()

    if not order_id:
        return None, "order_id is empty"
    if not customer:
        return None, "customer is empty"
    try:
        amount = Decimal(raw_amount)
    except InvalidOperation:
        return None, f"amount '{raw_amount}' is not a number"
    if not amount.is_finite() or amount <= 0:
        return None, "amount must be greater than zero"
    try:
        order_date = date.fromisoformat(raw_date)
    except ValueError:
        return None, "order_date must look like YYYY-MM-DD"

    item = {
        "order_id": order_id,
        "customer": customer,
        "amount": amount,
        "order_date": order_date.isoformat(),
    }
    return item, None


def parse_orders(text):
    """Return (valid_items, issues). Raises ValueError if columns are missing."""
    reader = csv.DictReader(io.StringIO(text))
    missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
    if missing:
        raise ValueError(f"missing columns: {', '.join(sorted(missing))}")

    items, issues = [], []
    for line_no, row in enumerate(reader, start=2):  # line 1 is the header
        item, reason = validate_row(row)
        if item:
            items.append(item)
        else:
            issues.append(f"line {line_no}: {reason}")
    return items, issues


def _move(s3, bucket, key, folder):
    new_key = f"{folder}/{os.path.basename(key)}"
    s3.copy_object(Bucket=bucket, Key=new_key, CopySource={"Bucket": bucket, "Key": key})
    s3.delete_object(Bucket=bucket, Key=key)
    return new_key


def lambda_handler(event, context):
    s3 = boto3.client("s3")
    sns = boto3.client("sns")
    table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
    topic_arn = os.environ["TOPIC_ARN"]
    summaries = []

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])
        name = os.path.basename(key)

        try:
            body = s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8-sig")
            items, issues = parse_orders(body)
        except (ValueError, UnicodeDecodeError) as err:
            _move(s3, bucket, key, "failed")
            subject = f"CSV rejected: {name}"
            message = f"File: {key}\nThe file was rejected: {err}\nIt was moved to failed/."
        else:
            with table.batch_writer(overwrite_by_pkeys=["order_id"]) as batch:
                for item in items:
                    batch.put_item(Item=item)
            _move(s3, bucket, key, "processed")
            subject = f"CSV processed: {name}"
            message = f"File: {key}\nRows saved: {len(items)}\nRows skipped: {len(issues)}"
            if issues:
                message += "\n\nFirst issues:\n" + "\n".join(issues[:MAX_ISSUES_SHOWN])

        sns.publish(TopicArn=topic_arn, Subject=subject[:100], Message=message)
        summaries.append(subject)

    return {"files": summaries}
