from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_ac3_ac4_subprocess_crash_and_authoritative_resume(tmp_path: Path) -> None:
    """AC3, AC4: Verify genuine OS subprocess abrupt termination and authoritative SQLite WAL resume."""
    db_file = tmp_path / "genomics_wal.db"
    db_posix = db_file.as_posix()

    # 1. Subprocess 1: Starts inspection, records 2 steps, then abrupt crash (os._exit(0))
    subproc1_code = f"""
import os
from workflow_adapter.backends.local import LocalBackend
from genomics_assistant.domain import GenomicsDomainPolicy

policy = GenomicsDomainPolicy()
backend = LocalBackend("{db_posix}", policy)

start_resp = backend.start_inspection(
    principal_id="tech-1",
    inspection_type="wgs_clinical_qc",
    asset_id="FLOWCELL-WGS-07",
    idempotency_key="subproc-start-01",
)
exec_id = start_resp.execution_id

backend.record_inspection_result(
    principal_id="tech-1",
    execution_id=exec_id,
    step_id="dna_concentration_ng_ul",
    value=42.5,
    unit="ng/uL",
    idempotency_key="subproc-step1-01",
)

backend.record_inspection_result(
    principal_id="tech-1",
    execution_id=exec_id,
    step_id="fragment_size_bp",
    value=475.0,
    unit="bp",
    idempotency_key="subproc-step2-01",
)

# Print execution_id to stdout and terminate abruptly without closing connections
print(f"EXECUTION_ID:{{exec_id}}", flush=True)
os._exit(0)
"""

    res1 = subprocess.run(
        [sys.executable, "-c", subproc1_code],
        capture_output=True,
        text=True,
        check=True,
    )

    exec_id_line = next(
        line for line in res1.stdout.splitlines() if line.startswith("EXECUTION_ID:")
    )
    execution_id = exec_id_line.split(":", 1)[1].strip()
    assert execution_id.startswith("exec_")

    # 2. Subprocess 2: Spawn fresh process pointing to same database file and resume without execution_id
    subproc2_code = f"""
import sys
from workflow_adapter.backends.local import LocalBackend
from workflow_adapter.models import WorkflowStatus
from genomics_assistant.domain import GenomicsDomainPolicy

policy = GenomicsDomainPolicy()
backend = LocalBackend("{db_posix}", policy)

# Authoritative session resume with execution_id=None
status = backend.get_inspection_status(principal_id="tech-1")
assert status.execution_id == "{execution_id}", f"Expected {execution_id}, got {{status.execution_id}}"
assert status.status == WorkflowStatus.RUNNING
assert len(status.completed_steps) == 2
assert status.pending_step is not None
assert status.pending_step.step_id == "loading_molarity_pm"

# Complete Step 3
step3_resp = backend.record_inspection_result(
    principal_id="tech-1",
    execution_id="{execution_id}",
    step_id="loading_molarity_pm",
    value=210.0,
    unit="pM",
    idempotency_key="subproc-step3-01",
)
assert step3_resp.accepted is True
assert step3_resp.next_step is None

# Complete Inspection
comp_resp = backend.complete_inspection(
    principal_id="tech-1",
    execution_id="{execution_id}",
    idempotency_key="subproc-comp-01",
)
assert comp_resp.status == WorkflowStatus.COMPLETED
assert comp_resp.summary.total_steps == 3
print("RESUME_AND_COMPLETE_SUCCESS")
"""

    res2 = subprocess.run(
        [sys.executable, "-c", subproc2_code],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "RESUME_AND_COMPLETE_SUCCESS" in res2.stdout
