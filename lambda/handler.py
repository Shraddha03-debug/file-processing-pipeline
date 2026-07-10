import json
import os
import time
import uuid
import urllib.parse
import boto3

DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE")
ENDPOINT_URL = os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566")

dynamodb = boto3.resource("dynamodb", endpoint_url=ENDPOINT_URL)
table = dynamodb.Table(DYNAMODB_TABLE)


def lambda_handler(event, context):
    processed = 0

    for record in event.get("Records", []):
        body = json.loads(record["body"])

        for s3_record in body.get("Records", []):
            bucket = s3_record["s3"]["bucket"]["name"]
            key = urllib.parse.unquote_plus(s3_record["s3"]["object"]["key"])
            size = s3_record["s3"]["object"].get("size", 0)

            file_id = str(uuid.uuid4())
            table.put_item(
                Item={
                    "file_id": file_id,
                    "bucket": bucket,
                    "key": key,
                    "size": size,
                    "status": "PROCESSED",
                    "processed_at": int(time.time()),
                }
            )
            processed += 1
            print(f"Processed {key} from {bucket} -> file_id={file_id}")

    return {
        "statusCode": 200,
        "body": json.dumps({"processed": processed}),
    }