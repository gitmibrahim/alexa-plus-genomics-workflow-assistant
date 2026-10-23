# AWS Deployment and Teardown Guide — Checkpoint

## 1. Overview
The Checkpoint reference architecture is deployed via AWS CDK (Python) in `alexa-plus-genomics-workflow-assistant/infra/cdk`.
It provisions:
* **Amazon DynamoDB Table:** `CheckpointWorkflowTable-{stage}` (Single-table transactional store, on-demand capacity, PITR enabled)
* **AWS Step Functions Standard State Machine:** `CheckpointInspectionStateMachine-{stage}` (Fenced outbox reconciler, task token wait state)
* **AWS Lambda Functions:**
  * `CheckpointAckAndRoute-{stage}`: Handles initialize/recover and callback ack transitions
  * `CheckpointRegisterWaitToken-{stage}`: Registers wait task token for pending mutations
  * `CheckpointMcpServer-{stage}`: Serves Streamable HTTP MCP endpoint and OAuth discovery
* **Amazon API Gateway HTTP API:** `CheckpointMcpHttpApi-{stage}` (Routes `POST /mcp`, `GET /health`, `GET /.well-known/oauth-protected-resource`)
* **Amazon SNS Topic:** `CheckpointGenomicsNotifications-{stage}` (Dispatches live workflow notifications)

---

## 2. Prerequisites
1. **AWS CLI / AWS Credentials:** Configured with administrator or power user deployment permissions.
2. **Node.js & AWS CDK CLI:** `cdk --version` (v2.1146+).
3. **Python Environment:** Python 3.11+ with `aws-cdk-lib` and project dependencies installed.

---

## 3. Deployment Steps

```bash
cd alexa-plus-genomics-workflow-assistant/infra/cdk

# 1. Bootstrap AWS Environment (first-time per account/region)
cdk bootstrap

# 2. Synthesize CloudFormation Template
cdk synth

# 3. Deploy Stack (default stage: dev)
cdk deploy --require-approval never
```

Upon successful deployment, CDK outputs the created resources:
* `DynamoDBTableName`: e.g. `CheckpointWorkflowTable-dev`
* `StateMachineArn`: e.g. `arn:aws:states:us-east-1:123456789012:stateMachine:CheckpointInspectionStateMachine-dev`
* `NotificationTopicArn`: e.g. `arn:aws:sns:us-east-1:123456789012:CheckpointGenomicsNotifications-dev`
* `McpApiEndpoint`: e.g. `https://xxxx.execute-api.us-east-1.amazonaws.com/mcp`

---

## 4. Verification After Deployment

Run live AWS integration tests:
```bash
export DYNAMODB_TABLE_NAME=$(aws cloudformation describe-stacks --stack-name CheckpointGenomicsStack-dev --query "Stacks[0].Outputs[?OutputKey=='DynamoDBTableName'].OutputValue" --output text)
export SFN_STATE_MACHINE_ARN=$(aws cloudformation describe-stacks --stack-name CheckpointGenomicsStack-dev --query "Stacks[0].Outputs[?OutputKey=='StateMachineArn'].OutputValue" --output text)
export SNS_NOTIFICATION_TOPIC_ARN=$(aws cloudformation describe-stacks --stack-name CheckpointGenomicsStack-dev --query "Stacks[0].Outputs[?OutputKey=='NotificationTopicArn'].OutputValue" --output text)

pytest -v -m aws alexa-plus-genomics-workflow-assistant/tests/integration/test_aws_live_stack.py
```

---

## 5. Teardown / Cleanup

To tear down all provisioned cloud resources and prevent ongoing charges:

```bash
cd alexa-plus-genomics-workflow-assistant/infra/cdk
cdk destroy --force
```
All resources have `RemovalPolicy.DESTROY` configured for clean demo teardown.
