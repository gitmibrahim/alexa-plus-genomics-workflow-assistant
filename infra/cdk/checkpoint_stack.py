from __future__ import annotations

import json
from typing import Any, cast

import aws_cdk as cdk
from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import (
    aws_apigatewayv2 as apigwv2,
)
from aws_cdk import (
    aws_apigatewayv2_integrations as apigw_integrations,
)
from aws_cdk import (
    aws_dynamodb as dynamodb,
)
from aws_cdk import (
    aws_iam as iam,
)
from aws_cdk import (
    aws_lambda as lambda_,
)
from aws_cdk import (
    aws_sns as sns,
)
from aws_cdk import (
    aws_stepfunctions as sfn,
)
from constructs import Construct


class CheckpointGenomicsStack(Stack):
    """Reproducible AWS CDK stack for Checkpoint (DynamoDB + Step Functions Standard + Lambda + SNS + HTTP API)."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        stage_name: str = "dev",
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 1. Single-Table Authoritative DynamoDB Store
        workflow_table = dynamodb.Table(
            self,
            "CheckpointWorkflowTable",
            table_name=f"CheckpointWorkflowTable-{stage_name}",
            partition_key=dynamodb.Attribute(name="PK", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="SK", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            ),
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # 2. Amazon SNS Topic for Live Wet-Lab Notifications
        notification_topic = sns.Topic(
            self,
            "CheckpointNotificationTopic",
            topic_name=f"CheckpointGenomicsNotifications-{stage_name}",
            display_name="Checkpoint Clinical Genomics Workflow Notifications",
        )

        # Resolve code asset path to repo src directory
        from pathlib import Path
        src_path = Path(__file__).resolve().parents[2] / "src"
        if not src_path.is_dir():
            src_path = Path("src").resolve()
        lambda_code = lambda_.Code.from_asset(str(src_path))

        sfn_name = f"CheckpointInspectionStateMachine-{stage_name}"
        sfn_arn = self.format_arn(
            service="states",
            resource="stateMachine",
            resource_name=sfn_name,
            arn_format=cdk.ArnFormat.COLON_RESOURCE_NAME,
        )
        sfn_exec_arn = self.format_arn(
            service="states",
            resource="execution",
            resource_name=f"{sfn_name}:*",
            arn_format=cdk.ArnFormat.COLON_RESOURCE_NAME,
        )

        # 3. Step Functions Task Lambda Handlers
        ack_and_route_fn = lambda_.Function(
            self,
            "AckAndRouteLambda",
            function_name=f"CheckpointAckAndRoute-{stage_name}",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="genomics_assistant.aws_handlers.ack_and_route_lambda_entrypoint",
            code=lambda_code,
            timeout=Duration.seconds(15),
            memory_size=256,
            environment={
                "WORKFLOW_BACKEND": "aws",
                "DYNAMODB_TABLE_NAME": workflow_table.table_name,
                "SFN_STATE_MACHINE_ARN": sfn_arn,
            },
        )

        register_wait_token_fn = lambda_.Function(
            self,
            "RegisterWaitTokenLambda",
            function_name=f"CheckpointRegisterWaitToken-{stage_name}",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="genomics_assistant.aws_handlers.register_wait_token_lambda_entrypoint",
            code=lambda_code,
            timeout=Duration.seconds(15),
            memory_size=256,
            environment={
                "WORKFLOW_BACKEND": "aws",
                "DYNAMODB_TABLE_NAME": workflow_table.table_name,
                "SFN_STATE_MACHINE_ARN": sfn_arn,
            },
        )

        workflow_table.grant_read_write_data(ack_and_route_fn)
        workflow_table.grant_read_write_data(register_wait_token_fn)

        # 4. Step Functions Standard State Machine (ASL Definition)
        sfn_role = iam.Role(
            self,
            "StateMachineExecutionRole",
            assumed_by=cast(iam.IPrincipal, iam.ServicePrincipal("states.amazonaws.com")),
        )
        ack_and_route_fn.grant_invoke(sfn_role)
        register_wait_token_fn.grant_invoke(sfn_role)

        asl_definition = {
            "Comment": "Checkpoint Fenced Asynchronous Orchestration State Machine",
            "StartAt": "InitializeOrRecoverState",
            "States": {
                "InitializeOrRecoverState": {
                    "Type": "Task",
                    "Resource": ack_and_route_fn.function_arn,
                    "Parameters": {
                        "action": "initialize_or_recover",
                        "execution_id.$": "$.execution_id",
                        "epoch.$": "$.epoch",
                        "entry_target_version.$": "$.entry_target_version",
                        "status.$": "$.status",
                        "sfn_execution_arn.$": "$$.Execution.Id",
                    },
                    "ResultPath": "$.orchestration_result",
                    "Next": "EvaluateWorkflowStatusChoice",
                },
                "EvaluateWorkflowStatusChoice": {
                    "Type": "Choice",
                    "Choices": [
                        {
                            "Variable": "$.orchestration_result.status",
                            "StringEquals": "COMPLETED",
                            "Next": "InspectionCompletedSucceed",
                        }
                    ],
                    "Default": "WaitForNextMutationCallback",
                },
                "WaitForNextMutationCallback": {
                    "Type": "Task",
                    "Resource": "arn:aws:states:::lambda:invoke.waitForTaskToken",
                    "Parameters": {
                        "FunctionName": register_wait_token_fn.function_arn,
                        "Payload": {
                            "action": "register_wait_token",
                            "execution_id.$": "$.execution_id",
                            "epoch.$": "$.epoch",
                            "processed_version.$": "$.orchestration_result.processed_version",
                            "task_token.$": "$$.Task.Token",
                            "sfn_execution_arn.$": "$$.Execution.Id",
                        },
                    },
                    "TimeoutSeconds": 3600,
                    "ResultPath": "$.callback_payload",
                    "Next": "AckCallbackTransitionState",
                },
                "AckCallbackTransitionState": {
                    "Type": "Task",
                    "Resource": ack_and_route_fn.function_arn,
                    "Parameters": {
                        "action": "ack_callback",
                        "execution_id.$": "$.execution_id",
                        "epoch.$": "$.epoch",
                        "from_version.$": "$.callback_payload.from_version",
                        "delivered_version.$": "$.callback_payload.delivered_version",
                        "status.$": "$.callback_payload.status",
                        "sfn_execution_arn.$": "$$.Execution.Id",
                    },
                    "ResultPath": "$.orchestration_result",
                    "Next": "EvaluateWorkflowStatusChoice",
                },
                "InspectionCompletedSucceed": {"Type": "Succeed"},
            },
        }

        state_machine = sfn.StateMachine(
            self,
            "CheckpointInspectionStateMachine",
            state_machine_name=sfn_name,
            definition_body=sfn.DefinitionBody.from_string(json.dumps(asl_definition)),
            state_machine_type=sfn.StateMachineType.STANDARD,
            role=cast(iam.IRole, sfn_role),
            timeout=Duration.hours(2),
        )

        register_wait_token_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "states:StartExecution",
                    "states:DescribeExecution",
                    "states:SendTaskSuccess",
                ],
                resources=[sfn_arn, sfn_exec_arn],
            )
        )
        ack_and_route_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "states:StartExecution",
                    "states:DescribeExecution",
                    "states:SendTaskSuccess",
                ],
                resources=[sfn_arn, sfn_exec_arn],
            )
        )

        # 5. MCP Streamable HTTP Server Lambda
        mcp_server_fn = lambda_.Function(
            self,
            "CheckpointMcpServerLambda",
            function_name=f"CheckpointMcpServer-{stage_name}",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="genomics_assistant.app.lambda_handler",
            code=lambda_code,
            timeout=Duration.seconds(29),
            memory_size=512,
            environment={
                "WORKFLOW_BACKEND": "aws",
                "DYNAMODB_TABLE_NAME": workflow_table.table_name,
                "SFN_STATE_MACHINE_ARN": sfn_arn,
                "SNS_NOTIFICATION_TOPIC_ARN": notification_topic.topic_arn,
            },
        )
        workflow_table.grant_read_write_data(mcp_server_fn)
        notification_topic.grant_publish(mcp_server_fn)
        mcp_server_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "states:StartExecution",
                    "states:DescribeExecution",
                    "states:SendTaskSuccess",
                ],
                resources=[sfn_arn, sfn_exec_arn],
            )
        )

        # 6. HTTPS API Gateway
        http_api = apigwv2.HttpApi(
            self,
            "CheckpointMcpHttpApi",
            api_name=f"CheckpointMcpHttpApi-{stage_name}",
        )
        mcp_integration = apigw_integrations.HttpLambdaIntegration(
            "McpLambdaIntegration", handler=cast(lambda_.IFunction, mcp_server_fn)
        )
        http_api.add_routes(
            path="/mcp",
            methods=[apigwv2.HttpMethod.POST, apigwv2.HttpMethod.GET],
            integration=mcp_integration,
        )
        http_api.add_routes(
            path="/health",
            methods=[apigwv2.HttpMethod.GET],
            integration=mcp_integration,
        )
        http_api.add_routes(
            path="/.well-known/oauth-protected-resource",
            methods=[apigwv2.HttpMethod.GET],
            integration=mcp_integration,
        )

        CfnOutput(self, "DynamoDBTableName", value=workflow_table.table_name)
        CfnOutput(self, "StateMachineArn", value=state_machine.state_machine_arn)
        CfnOutput(self, "NotificationTopicArn", value=notification_topic.topic_arn)
        CfnOutput(self, "McpApiEndpoint", value=f"{http_api.api_endpoint}/mcp")
