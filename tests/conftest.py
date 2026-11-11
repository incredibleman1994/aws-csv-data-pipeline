import os
import sys
from types import SimpleNamespace

import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lambda"))

REGION = "ap-south-1"
BUCKET = "test-uploads"
TABLE = "test-orders"


@pytest.fixture
def aws(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)

    with mock_aws():
        s3 = boto3.client("s3")
        s3.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION})

        table = boto3.resource("dynamodb").create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "order_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "order_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        # Subscribe an SQS queue to the topic so tests can read what was published.
        sns = boto3.client("sns")
        sqs = boto3.client("sqs")
        topic_arn = sns.create_topic(Name="notifications")["TopicArn"]
        queue_url = sqs.create_queue(QueueName="inbox")["QueueUrl"]
        queue_arn = sqs.get_queue_attributes(QueueUrl=queue_url, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
        sns.subscribe(TopicArn=topic_arn, Protocol="sqs", Endpoint=queue_arn)

        monkeypatch.setenv("TABLE_NAME", TABLE)
        monkeypatch.setenv("TOPIC_ARN", topic_arn)
        yield SimpleNamespace(s3=s3, table=table, sqs=sqs, queue_url=queue_url)
