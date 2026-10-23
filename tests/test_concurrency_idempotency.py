from __future__ import annotations

import concurrent.futures
import threading
from pathlib import Path

import pytest
from workflow_adapter.backends.local import LocalBackend
from workflow_adapter.models import RecordResultResponse, StartInspectionResponse

from genomics_assistant.domain import GenomicsDomainPolicy


@pytest.fixture
def policy() -> GenomicsDomainPolicy:
    return GenomicsDomainPolicy()


@pytest.fixture
def backend(tmp_path: Path, policy: GenomicsDomainPolicy) -> LocalBackend:
    db_file = tmp_path / "concurrency_test.db"
    return LocalBackend(db_file, policy)


def test_ac7_16_concurrent_duplicate_starts_commit_once(backend: LocalBackend) -> None:
    """AC7: 16 threads racing start_inspection with identical idempotency_key."""
    num_threads = 16
    barrier = threading.Barrier(num_threads)

    def worker() -> StartInspectionResponse:
        barrier.wait()
        return backend.start_inspection(
            principal_id="tech-pool-1",
            inspection_type="wgs_clinical_qc",
            asset_id="FLOWCELL-WGS-07",
            idempotency_key="concurrent-start-07",
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker) for _ in range(num_threads)]
        results = [f.result() for f in futures]

    assert len(results) == num_threads
    first_exec_id = results[0].execution_id
    assert all(r.execution_id == first_exec_id for r in results)

    new_commits = [r for r in results if not r.duplicate]
    replays = [r for r in results if r.duplicate]

    assert len(new_commits) == 1
    assert len(replays) == 15


def test_ac7_16_concurrent_duplicate_step_mutations_commit_once(backend: LocalBackend) -> None:
    """AC7: 16 threads racing record_inspection_result with identical idempotency_key."""
    start_resp = backend.start_inspection(
        principal_id="tech-pool-1",
        inspection_type="wgs_clinical_qc",
        asset_id="FLOWCELL-WGS-07",
        idempotency_key="setup-start-07",
    )
    exec_id = start_resp.execution_id

    num_threads = 16
    barrier = threading.Barrier(num_threads)

    def worker() -> RecordResultResponse:
        barrier.wait()
        return backend.record_inspection_result(
            principal_id="tech-pool-1",
            execution_id=exec_id,
            step_id="dna_concentration_ng_ul",
            value=44.0,
            unit="ng/uL",
            idempotency_key="concurrent-step-1-key",
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker) for _ in range(num_threads)]
        results = [f.result() for f in futures]

    assert len(results) == num_threads
    assert all(r.accepted is True for r in results)

    new_commits = [r for r in results if not r.duplicate]
    replays = [r for r in results if r.duplicate]

    assert len(new_commits) == 1
    assert len(replays) == 15

    status = backend.get_inspection_status(principal_id="tech-pool-1", execution_id=exec_id)
    assert status.desired_state_version == 2
    assert len(status.completed_steps) == 1
    assert status.pending_step is not None
    assert status.pending_step.step_id == "fragment_size_bp"
