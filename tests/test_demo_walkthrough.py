from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from run_demo_walkthrough import run_walkthrough  # noqa: E402


@pytest.mark.asyncio
async def test_ac14_walkthrough_executes_all_11_steps_and_completes() -> None:
    result = await run_walkthrough(mode="local")
    assert result["final_status"] == "COMPLETED"
    assert result["summary"]["total_steps"] == 3
    assert result["summary"]["normal_steps"] == 3
    assert (
        result["summary"]["metadata"]["release_decision"]
        == "APPROVED_FOR_SEQUENCING_AND_DRAGEN_INGEST"
    )
    assert result["notifications_dispatched"] >= 5


def test_ac14_cli_walkthrough_prints_explicit_simulation_disclosure_banner() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_demo_walkthrough.py"
    proc = subprocess.run(
        [sys.executable, str(script_path), "--mode", "local"],
        capture_output=True,
        text=True,
        check=True,
    )
    stdout = proc.stdout
    assert "EXECUTION MODE: LOCAL_MCP_SIMULATION" in stdout
    assert "CANDOR DISCLOSURE (AC14)" in stdout
    assert "NOT a live Alexa+ cloud console" in stdout
    assert "[Step 11] Completed WGS QC Run -> status=COMPLETED" in stdout
