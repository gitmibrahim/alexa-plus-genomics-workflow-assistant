from __future__ import annotations

import os
import time
import uuid

import boto3
import pytest
from workflow_adapter.backends.aws_dynamodb import DynamoDBWorkflowStore
from workflow_adapter.backends.aws_sfn_reconciler import StepFunctionsReconciler
from workflow_adapter.backends.aws_step_functions import AWSBackend, SNSNotificationSink
from workflow_adapter.models import NotificationPreferences, OutboxStatus, WorkflowStatus

from genomics_assistant.domain import GenomicsDomainPolicy


@pytest.mark.aws
def test_ac13_live_aws_dynamodb_and_step_functions_reconciliation() -> None:
    """
    Live AWS integration test (AC13).
    Requires deployed CDK stack environment variables:
      DYNAMODB_TABLE_NAME and SFN_STATE_MACHINE_ARN
    """
    table_name = os.environ.get("DYNAMODB_TABLE_NAME", "")
    sfn_arn = os.environ.get("SFN_STATE_MACHINE_ARN", "")
    topic_arn = os.environ.get("SNS_NOTIFICATION_TOPIC_ARN", "")
    if not table_name or not sfn_arn:
        pytest.skip("Set DYNAMODB_TABLE_NAME and SFN_STATE_MACHINE_ARN to run live AWS stack tests.")

    region = os.environ.get("AWS_REGION", "us-east-1")
    ddb_client = boto3.client("dynamodb", region_name=region)
    sfn_client = boto3.client("stepfunctions", region_name=region)
    sns_client = boto3.client("sns", region_name=region)

    policy = GenomicsDomainPolicy()
    sns_sink = SNSNotificationSink(sns_client, topic_arn)
    store = DynamoDBWorkflowStore(
        ddb_client=ddb_client,
        table_name=table_name,
        policy=policy,
        notification_port=sns_sink,
    )
    reconciler = StepFunctionsReconciler(
        ddb_client=ddb_client,
        sfn_client=sfn_client,
        table_name=table_name,
        state_machine_arn=sfn_arn,
        store=store,
    )
    backend = AWSBackend(store=store, reconciler=reconciler)

    principal_id = f"live-aws-tech-{uuid.uuid4().hex[:8]}"
    run_tag = uuid.uuid4().hex[:8]

    # 1. Start Inspection on FLOWCELL-WGS-07
    start_res = backend.start_inspection(
        principal_id=principal_id,
        inspection_type="wgs_clinical_qc",
        asset_id="FLOWCELL-WGS-07",
        idempotency_key=f"aws-start-{run_tag}",
        notification_prefs=NotificationPreferences(on_completion=True),
    )
    exec_id = start_res.execution_id
    assert start_res.status == WorkflowStatus.RUNNING

    # 2. Record Steps 1, 2, 3 and Complete
    backend.record_inspection_result(
        principal_id=principal_id,
        execution_id=exec_id,
        step_id="dna_concentration_ng_ul",
        value=42.5,
        unit="ng/uL",
        idempotency_key=f"aws-s1-{run_tag}",
    )
    backend.record_inspection_result(
        principal_id=principal_id,
        execution_id=exec_id,
        step_id="fragment_size_bp",
        value=475.0,
        unit="bp",
        idempotency_key=f"aws-s2-{run_tag}",
    )
    backend.record_inspection_result(
        principal_id=principal_id,
        execution_id=exec_id,
        step_id="loading_molarity_pm",
        value=215.0,
        unit="pM",
        idempotency_key=f"aws-s3-{run_tag}",
    )
    comp_res = backend.complete_inspection(
        principal_id=principal_id,
        execution_id=exec_id,
        idempotency_key=f"aws-comp-{run_tag}",
    )
    assert comp_res.status == WorkflowStatus.COMPLETED

    # 3. Poll reconciliation briefly for Step Functions Standard completion acknowledgement
    deadline = time.time() + 25.0
    while time.time() < deadline:
        reconciler.reconcile_execution(exec_id)
        meta = store.load_execution_metadata(exec_id)
        if meta.acked_sfn_version == meta.desired_state_version:
            break
        time.sleep(1.0)

    final_meta = store.load_execution_metadata(exec_id)
    assert final_meta.acked_sfn_version == final_meta.desired_state_version
    outbox = store.get_outbox_records(principal_id=principal_id, execution_id=exec_id)
    assert all(rec.outbox_status == OutboxStatus.ACKNOWLEDGED for rec in outbox)
