from __future__ import annotations

from pathlib import Path

import pytest
from workflow_adapter.backends.local import InMemoryNotificationSink, LocalBackend
from workflow_adapter.errors import AdapterError, ErrorCode
from workflow_adapter.models import (
    NotificationEventType,
    NotificationPreferences,
    ResolutionBehavior,
    WorkflowStatus,
)

from genomics_assistant.domain import GenomicsDomainPolicy


@pytest.fixture
def policy() -> GenomicsDomainPolicy:
    return GenomicsDomainPolicy()


@pytest.fixture
def sink() -> InMemoryNotificationSink:
    return InMemoryNotificationSink()


@pytest.fixture
def backend(
    tmp_path: Path, policy: GenomicsDomainPolicy, sink: InMemoryNotificationSink
) -> LocalBackend:
    db_file = tmp_path / "full_journey.db"
    return LocalBackend(db_file, policy, notification_port=sink)


def test_full_11_step_wgs_inspection_journey(
    backend: LocalBackend, sink: InMemoryNotificationSink
) -> None:
    """Complete 11-step end-to-end WGS clinical QC journey."""
    tech_id = "technologist-lead-01"

    # Step 1: Start WGS clinical QC
    start_resp = backend.start_inspection(
        principal_id=tech_id,
        inspection_type="wgs_clinical_qc",
        asset_id="FLOWCELL-WGS-07",
        idempotency_key="journey-start-07",
        notification_prefs=NotificationPreferences(
            on_pause=True,
            on_revision=True,
            on_blocked=True,
            on_status=True,
            on_completion=True,
            channels=["lims_webhook", "voice_summary"],
        ),
    )
    exec_id = start_resp.execution_id
    assert start_resp.status == WorkflowStatus.RUNNING
    assert start_resp.next_step.step_id == "dna_concentration_ng_ul"

    # Step 2: Record Valid Step 1 & Step 2
    r_step1 = backend.record_inspection_result(
        principal_id=tech_id,
        execution_id=exec_id,
        step_id="dna_concentration_ng_ul",
        value=42.5,
        unit="ng/uL",
        idempotency_key="journey-step1-07",
    )
    assert r_step1.accepted is True
    assert r_step1.next_step is not None
    assert r_step1.next_step.step_id == "fragment_size_bp"

    r_step2 = backend.record_inspection_result(
        principal_id=tech_id,
        execution_id=exec_id,
        step_id="fragment_size_bp",
        value=475.0,
        unit="bp",
        idempotency_key="journey-step2-07",
    )
    assert r_step2.accepted is True
    assert r_step2.next_step is not None
    assert r_step2.next_step.step_id == "loading_molarity_pm"

    # Step 3: Pause Session for Wet-Lab Incubation
    pause_resp = backend.configure_notifications(
        principal_id=tech_id,
        execution_id=exec_id,
        pause_session=True,
        idempotency_key="journey-pause-07",
    )
    assert pause_resp.session_paused is True
    pause_notifs = [
        n
        for n in sink.delivered_records
        if n.event_type == NotificationEventType.ON_PAUSE_INTERRUPTION
    ]
    assert len(pause_notifs) >= 1

    # Step 4: Multi-Operator & Multi-Session Collision Check
    # 4a: Another technologist attempts to start on FLOWCELL-WGS-07 -> Rejected
    with pytest.raises(AdapterError) as exc_coll:
        backend.start_inspection(
            principal_id="tech-other-02",
            inspection_type="wgs_clinical_qc",
            asset_id="FLOWCELL-WGS-07",
            idempotency_key="collision-start",
        )
    assert exc_coll.value.error_code == ErrorCode.INVALID_STATE_TRANSITION
    assert exc_coll.value.details["reason"] == "ASSET_ALREADY_UNDER_INSPECTION"
    assert exc_coll.value.details["owned_by_caller"] is False

    # 4b: Same tech starts FLOWCELL-WGS-08 -> Ambiguous lookup
    backend.start_inspection(
        principal_id=tech_id,
        inspection_type="wgs_clinical_qc",
        asset_id="FLOWCELL-WGS-08",
        idempotency_key="journey-start-08",
    )
    with pytest.raises(AdapterError) as exc_ambig:
        backend.get_inspection_status(principal_id=tech_id, execution_id=None, asset_id=None)
    assert exc_ambig.value.error_code == ErrorCode.INVALID_INPUT
    assert exc_ambig.value.details["reason"] == "AMBIGUOUS_ACTIVE_SESSION"

    # Step 5: Resume by asset_id="FLOWCELL-WGS-07"
    status_07 = backend.get_inspection_status(
        principal_id=tech_id, asset_id="FLOWCELL-WGS-07", emit_notification=True
    )
    assert status_07.execution_id == exec_id
    assert len(status_07.completed_steps) == 2
    assert status_07.pending_step is not None
    assert status_07.pending_step.step_id == "loading_molarity_pm"

    # Step 6: Idempotent Duplicate Retry of Step 2
    r_step2_retry = backend.record_inspection_result(
        principal_id=tech_id,
        execution_id=exec_id,
        step_id="fragment_size_bp",
        value=475.0,
        unit="bp",
        idempotency_key="journey-step2-07",
    )
    assert r_step2_retry.duplicate is True

    # Step 7: Out-of-Range Molarity Triggers Block (310.0 pM > 250.0 max)
    r_step3_blocked = backend.record_inspection_result(
        principal_id=tech_id,
        execution_id=exec_id,
        step_id="loading_molarity_pm",
        value=310.0,
        unit="pM",
        idempotency_key="journey-step3-blocked",
    )
    assert r_step3_blocked.accepted is False
    assert r_step3_blocked.status == WorkflowStatus.BLOCKED
    assert r_step3_blocked.active_exception is not None
    exc_id = r_step3_blocked.active_exception.exception_id

    # Step 8: Rejected Completion While Blocked
    with pytest.raises(AdapterError) as exc_comp_blocked:
        backend.complete_inspection(
            principal_id=tech_id,
            execution_id=exec_id,
            idempotency_key="complete-blocked-attempt",
        )
    assert exc_comp_blocked.value.error_code == ErrorCode.WORKFLOW_BLOCKED

    # Step 9: Rejected Arbitrary Override (FORCE_RELEASE_TO_DRAGEN)
    with pytest.raises(AdapterError) as exc_bad_res:
        backend.resolve_inspection_exception(
            principal_id=tech_id,
            execution_id=exec_id,
            exception_id=exc_id,
            resolution="FORCE_RELEASE_TO_DRAGEN",
            idempotency_key="bad-res-attempt",
        )
    assert exc_bad_res.value.error_code == ErrorCode.INVALID_INPUT

    # Step 10: Approved Policy Resolution (RETEST) and Valid Re-reading (215.0 pM)
    res_resp = backend.resolve_inspection_exception(
        principal_id=tech_id,
        execution_id=exec_id,
        exception_id=exc_id,
        resolution="DILUTE_LIBRARY_TO_TARGET_MOLARITY_AND_RETEST",
        idempotency_key="resolve-dilute-07",
    )
    assert res_resp.status == WorkflowStatus.RUNNING
    assert res_resp.resolution_behavior == ResolutionBehavior.RETEST
    assert res_resp.pending_step is not None
    assert res_resp.pending_step.step_id == "loading_molarity_pm"

    # Record in-range molarity reading
    r_step3_valid = backend.record_inspection_result(
        principal_id=tech_id,
        execution_id=exec_id,
        step_id="loading_molarity_pm",
        value=215.0,
        unit="pM",
        idempotency_key="journey-step3-valid",
    )
    assert r_step3_valid.accepted is True
    assert r_step3_valid.next_step is None
    assert "complete_inspection" in r_step3_valid.next_allowed_actions

    # Step 11: Safe Completion & Downstream DRAGEN/Emedgene Pipeline Release
    comp_resp = backend.complete_inspection(
        principal_id=tech_id,
        execution_id=exec_id,
        idempotency_key="journey-complete-07",
    )
    assert comp_resp.status == WorkflowStatus.COMPLETED
    assert comp_resp.summary.total_steps == 3
    assert comp_resp.summary.normal_steps == 3
    assert comp_resp.summary.metadata["pipeline_release_target"] == "ICA_DRAGEN_EMEDGENE"
    assert (
        comp_resp.summary.metadata["release_decision"]
        == "APPROVED_FOR_SEQUENCING_AND_DRAGEN_INGEST"
    )
