from __future__ import annotations

import logging
import os
from typing import Any

import boto3  # type: ignore[import-untyped]
from workflow_adapter.backends.aws_dynamodb import DynamoDBWorkflowStore
from workflow_adapter.backends.aws_sfn_reconciler import StepFunctionsReconciler, _now_ms
from workflow_adapter.models import TokenLifecycleStatus

logger = logging.getLogger(__name__)

WAIT_TOKEN_TTL_MS = 3_500_000


class StepFunctionsTaskHandlers:
    """Authoritative Step Functions Standard state-machine task handlers."""

    def __init__(
        self,
        *,
        ddb_client: Any,
        table_name: str,
        store: DynamoDBWorkflowStore,
        reconciler: StepFunctionsReconciler,
        clock_ms_fn: Any = _now_ms,
    ) -> None:
        self._ddb = ddb_client
        self._table = table_name
        self._store = store
        self._reconciler = reconciler
        self._clock_ms = clock_ms_fn

    def handle_ack_and_route(self, event: dict[str, Any]) -> dict[str, Any]:
        """Executes Transition 2 (initialize_or_recover) and Transition 5 (ack_callback)."""
        action = str(event["action"])
        execution_id = str(event["execution_id"])
        epoch = int(event["epoch"])
        exec_arn = str(event["sfn_execution_arn"])

        if action == "initialize_or_recover":
            entry_v = int(event["entry_target_version"])
            self._ddb.update_item(
                TableName=self._table,
                Key={"PK": {"S": f"EXEC#{execution_id}"}, "SK": {"S": "METADATA"}},
                UpdateExpression=(
                    "SET sfn_execution_arn = :arn, "
                    "acked_sfn_version = :entry_v, "
                    "sfn_token_status = :none_status, "
                    "sfn_recovery_lease_until_ms = :zero"
                ),
                ConditionExpression=(
                    "sfn_recovery_epoch = :epoch "
                    "AND acked_sfn_version < :entry_v "
                    "AND (attribute_not_exists(sfn_execution_arn) OR sfn_execution_arn = :empty OR sfn_execution_arn = :arn)"
                ),
                ExpressionAttributeValues={
                    ":arn": {"S": exec_arn},
                    ":entry_v": {"N": str(entry_v)},
                    ":epoch": {"N": str(epoch)},
                    ":none_status": {"S": TokenLifecycleStatus.NONE.value},
                    ":empty": {"S": ""},
                    ":zero": {"N": "0"},
                },
            )
            self._reconciler.acknowledge_outbox_up_to(
                execution_id=execution_id,
                up_to_version=entry_v,
                exec_arn=exec_arn,
            )
            latest = self._store.load_execution_metadata(execution_id)
            return {
                "processed_version": entry_v,
                "status": str(event.get("status") or latest.status.value),
            }

        if action == "ack_callback":
            from_v = int(event["from_version"])
            delivered_v = int(event["delivered_version"])
            delivered_status = str(event["status"])

            self._ddb.update_item(
                TableName=self._table,
                Key={"PK": {"S": f"EXEC#{execution_id}"}, "SK": {"S": "METADATA"}},
                UpdateExpression=(
                    "SET acked_sfn_version = :deliv_v, "
                    "sfn_token_status = :consumed, "
                    "sfn_task_token = :empty, "
                    "sfn_inflight_target_version = :zero, "
                    "sfn_token_lease_until_ms = :zero"
                ),
                ConditionExpression=(
                    "sfn_execution_arn = :arn "
                    "AND sfn_recovery_epoch = :epoch "
                    "AND acked_sfn_version = :from_v "
                    "AND acked_sfn_version < :deliv_v"
                ),
                ExpressionAttributeValues={
                    ":arn": {"S": exec_arn},
                    ":epoch": {"N": str(epoch)},
                    ":from_v": {"N": str(from_v)},
                    ":deliv_v": {"N": str(delivered_v)},
                    ":consumed": {"S": TokenLifecycleStatus.CONSUMED.value},
                    ":empty": {"S": ""},
                    ":zero": {"N": "0"},
                },
            )
            self._reconciler.acknowledge_outbox_up_to(
                execution_id=execution_id,
                up_to_version=delivered_v,
                exec_arn=exec_arn,
            )
            return {
                "processed_version": delivered_v,
                "status": delivered_status,
            }

        raise ValueError(f"Unsupported Step Functions task action '{action}'.")

    def handle_register_wait_token(self, event: dict[str, Any]) -> dict[str, Any]:
        """Executes Transition 3 (WaitForNextMutationCallback .waitForTaskToken)."""
        execution_id = str(event["execution_id"])
        epoch = int(event["epoch"])
        processed_v = int(event["processed_version"])
        task_token = str(event["task_token"])
        exec_arn = str(event["sfn_execution_arn"])
        now_ms = self._clock_ms()
        expires_at_ms = now_ms + WAIT_TOKEN_TTL_MS

        resp = self._ddb.update_item(
            TableName=self._table,
            Key={"PK": {"S": f"EXEC#{execution_id}"}, "SK": {"S": "METADATA"}},
            UpdateExpression=(
                "SET sfn_task_token = :token, "
                "sfn_token_version = :proc_v, "
                "sfn_token_status = :avail, "
                "sfn_lease_seq = sfn_lease_seq + :one, "
                "sfn_inflight_target_version = :zero, "
                "sfn_token_lease_until_ms = :zero, "
                "sfn_token_expires_at_ms = :expires_at"
            ),
            ConditionExpression=(
                "sfn_execution_arn = :arn "
                "AND sfn_recovery_epoch = :epoch "
                "AND acked_sfn_version = :proc_v "
                "AND (attribute_not_exists(sfn_token_version) OR sfn_token_version < :proc_v)"
            ),
            ExpressionAttributeValues={
                ":arn": {"S": exec_arn},
                ":epoch": {"N": str(epoch)},
                ":proc_v": {"N": str(processed_v)},
                ":token": {"S": task_token},
                ":avail": {"S": TokenLifecycleStatus.AVAILABLE.value},
                ":one": {"N": "1"},
                ":zero": {"N": "0"},
                ":expires_at": {"N": str(expires_at_ms)},
            },
            ReturnValues="ALL_NEW",
        )

        attrs = resp.get("Attributes", {})
        desired_v = int(attrs.get("desired_state_version", {}).get("N", str(processed_v)))
        acked_v = int(attrs.get("acked_sfn_version", {}).get("N", str(processed_v)))

        if desired_v > acked_v:
            self._reconciler.reconcile_execution(execution_id)

        return {"registered_token_version": processed_v, "fast_path_triggered": desired_v > acked_v}


def _build_handlers() -> StepFunctionsTaskHandlers:
    """Build handlers from environment variables for Lambda cold start."""
    from genomics_assistant.domain import GenomicsDomainPolicy

    table_name = os.environ.get("DYNAMODB_TABLE_NAME", "CheckpointWorkflowTable")
    sfn_arn = os.environ.get("SFN_STATE_MACHINE_ARN", "")
    ddb = boto3.client("dynamodb")
    sfn = boto3.client("stepfunctions")
    policy = GenomicsDomainPolicy()

    store = DynamoDBWorkflowStore(ddb_client=ddb, table_name=table_name, policy=policy)
    reconciler = StepFunctionsReconciler(
        ddb_client=ddb, sfn_client=sfn, table_name=table_name,
        state_machine_arn=sfn_arn, store=store,
    )
    store.set_orchestrator_port(reconciler)

    return StepFunctionsTaskHandlers(
        ddb_client=ddb, table_name=table_name, store=store, reconciler=reconciler,
    )


_handlers: StepFunctionsTaskHandlers | None = None


def _get_handlers() -> StepFunctionsTaskHandlers:
    global _handlers  # noqa: PLW0603
    if _handlers is None:
        _handlers = _build_handlers()
    return _handlers


def ack_and_route_lambda_entrypoint(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda entrypoint for AckAndRoute Step Functions task."""
    return _get_handlers().handle_ack_and_route(event)


def register_wait_token_lambda_entrypoint(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda entrypoint for RegisterWaitToken Step Functions task."""
    return _get_handlers().handle_register_wait_token(event)
