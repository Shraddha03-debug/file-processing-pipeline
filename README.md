# Serverless File Processing Pipeline

A small serverless pipeline I built to understand how event-driven architectures actually work on AWS — S3, SQS, Lambda and DynamoDB wired together so that uploading a file automatically triggers processing, with no server running in between.

Built and tested locally using a Docker-based AWS emulator (since I didn't want to rack up AWS bills while learning/debugging), with the plan to deploy it to real AWS next.

## What it does

You upload a file to an S3 bucket. That upload triggers an event to SQS, which wakes up a Lambda function, which reads the file's metadata and writes a record to DynamoDB. That's it — no polling, no server, everything reacts to the previous step.

```
File upload → S3 → SQS → Lambda → DynamoDB
                                      ↓
                              CloudWatch (logs)
```

## Why I built this

I wanted to actually understand serverless/event-driven design instead of just reading about it — how S3 event notifications work, how SQS decouples things, how Lambda's event source mapping polls a queue, and how IAM roles tie it all together with least-privilege permissions. Debugging it (see below) taught me more than the initial build did.

## Tech used

- AWS: S3, SQS, Lambda, DynamoDB, IAM, CloudWatch Logs
- Python 3.12 (Lambda handler)
- Docker + a local AWS emulator for testing everything without touching real AWS

## Repo structure

```
file-processing-pipeline/
├── config/
│   ├── trust-policy.json          → who's allowed to assume the Lambda role
│   ├── lambda-permissions.json    → what the Lambda role can actually do
│   ├── attributes.json            → lets S3 send messages into the SQS queue
│   ├── notification.json          → tells S3 to notify SQS on new uploads
│   └── queue-policy.json
├── lambda/
│   └── handler.py                 → the actual processing logic
└── .gitignore
```

## Running it locally

Everything below points at `localhost:4566`, where the local emulator serves S3/SQS/Lambda/DynamoDB.

```bash
# point the AWS CLI at the local emulator
set AWS_ENDPOINT_URL=http://localhost:4566
set AWS_ACCESS_KEY_ID=test
set AWS_SECRET_ACCESS_KEY=test
set AWS_DEFAULT_REGION=us-east-1

# create the bucket
aws s3 mb s3://file-processing-pipeline-incoming

# create the queue
aws sqs create-queue --queue-name file-processing-pipeline-queue

# let S3 send messages to that queue
aws sqs set-queue-attributes --queue-url http://localhost:4566/000000000000/file-processing-pipeline-queue --attributes file://config/attributes.json

# wire up the S3 → SQS event notification
aws s3api put-bucket-notification-configuration --bucket file-processing-pipeline-incoming --notification-configuration file://config/notification.json

# create the results table
aws dynamodb create-table --table-name file-processing-pipeline-results --attribute-definitions AttributeName=file_id,AttributeType=S --key-schema AttributeName=file_id,KeyType=HASH --billing-mode PAY_PER_REQUEST

# create the Lambda's execution role
aws iam create-role --role-name file-processing-pipeline-lambda-role --assume-role-policy-document file://config/trust-policy.json
aws iam put-role-policy --role-name file-processing-pipeline-lambda-role --policy-name file-processing-pipeline-lambda-policy --policy-document file://config/lambda-permissions.json

# package and deploy the function
cd lambda
tar -a -c -f function.zip handler.py
aws lambda create-function --function-name file-processing-pipeline-processor --runtime python3.12 --handler handler.lambda_handler --role arn:aws:iam::000000000000:role/file-processing-pipeline-lambda-role --zip-file fileb://function.zip --environment Variables={DYNAMODB_TABLE=file-processing-pipeline-results,AWS_ENDPOINT_URL=http://host.docker.internal:4566} --timeout 30

# hook the queue up to the Lambda
aws lambda create-event-source-mapping --function-name file-processing-pipeline-processor --event-source-arn arn:aws:sqs:us-east-1:000000000000:file-processing-pipeline-queue --batch-size 5
```

Then test it:

```bash
aws s3 cp test-file.txt s3://file-processing-pipeline-incoming/
aws dynamodb scan --table-name file-processing-pipeline-results
```

## What actually shows up in DynamoDB

```json
{
  "file_id": "c1169561-67e4-4e1e-848f-0bd40938d1ed",
  "bucket": "file-processing-pipeline-incoming",
  "key": "test-file.txt",
  "size": 13,
  "status": "PROCESSED",
  "processed_at": 1783669064
}
```

## The debugging part (the part I actually learned from)

At one point I uploaded a file and checked the SQS queue right after — it showed 0 messages, and my first instinct was that the S3 → SQS trigger was broken. Turned out it wasn't broken at all — Lambda had already picked up the message and deleted it from the queue before I ran my check. A `0` message count can mean "already succeeded," not "never arrived." Had to go check the emulator's container logs to actually see the full chain fire in order: S3 event → SQS receive → Lambda invoke → Lambda success → message deleted.

Also lost all my resources once because the container got removed (not just stopped) — good reminder that in-memory/local AWS setups don't persist unless you're careful about it, and that it's worth scripting the setup so you're not retyping ten commands from memory.

## If I keep working on this

- Add a dead-letter queue for messages that fail processing
- Write actual tests for the Lambda handler instead of just manually uploading files
- Deploy the real thing to AWS (Terraform, probably)
- Handle more file types instead of just generic metadata

---

Note: this was built and tested against a local AWS emulator, not real AWS — so any account ID you see in commands (`000000000000`) is just the emulator's default, not a real AWS account.
