from __future__ import annotations

from typing import Any, Final

from workflow_adapter.errors import AdapterError, ErrorCode
from workflow_adapter.models import (
    ResolutionBehavior,
    StepDefinition,
    WorkflowExecution,
)
from workflow_adapter.ports import DomainPolicyPort

GENOMICS_ASSET_CATALOG: Final[dict[str, dict[str, str]]] = {
    "FLOWCELL-WGS-07": {
        "description": "NovaSeq X Plus 25B Flow Cell - Bay A",
        "cohort_id": "COHORT-PED-RARE-07",
        "inspection_type": "wgs_clinical_qc",
    },
    "FLOWCELL-WGS-08": {
        "description": "NovaSeq X Plus 10B Flow Cell - Bay B",
        "cohort_id": "COHORT-CARDIO-HERED-08",
        "inspection_type": "wgs_clinical_qc",
    },
}

WGS_CLINICAL_QC_STEPS: Final[tuple[StepDefinition, ...]] = (
    StepDefinition(
        step_id="dna_concentration_ng_ul",
        title="Qubit dsDNA Yield Concentration",
        unit="ng/uL",
        accepted_units=("ng/ul", "ng/µl", "ng_ul"),
        min_value=15.0,
        max_value=60.0,
        resolution_policies={
            "DILUTE_OR_RECONCENTRATE_AND_REQUANTIFY": ResolutionBehavior.RETEST,
            "ANNOTATE_LOW_INPUT_AND_ESCALATE_TO_LAB_DIRECTOR": ResolutionBehavior.ANNOTATE_AND_ADVANCE,
        },
    ),
    StepDefinition(
        step_id="fragment_size_bp",
        title="TapeStation Mean Library Fragment Length",
        unit="bp",
        accepted_units=("bp", "base_pairs"),
        min_value=400.0,
        max_value=550.0,
        resolution_policies={
            "REPEAT_AMPURE_BEAD_CLEANUP_AND_RETEST": ResolutionBehavior.RETEST,
            "ANNOTATE_FRAGMENT_VARIANCE_AND_ESCALATE_TO_LAB_DIRECTOR": ResolutionBehavior.ANNOTATE_AND_ADVANCE,
        },
    ),
    StepDefinition(
        step_id="loading_molarity_pm",
        title="Normalized Flow-Cell Loading Molarity",
        unit="pM",
        accepted_units=("pm", "picomolar"),
        min_value=180.0,
        max_value=250.0,
        resolution_policies={
            "DILUTE_LIBRARY_TO_TARGET_MOLARITY_AND_RETEST": ResolutionBehavior.RETEST,
            "ANNOTATE_MOLARITY_EXCEPTION_AND_ESCALATE_TO_LAB_DIRECTOR": ResolutionBehavior.ANNOTATE_AND_ADVANCE,
        },
    ),
)


class GenomicsDomainPolicy(DomainPolicyPort):
    """Whole Genome Sequencing (WGS) Pre-Run QC & Pipeline Release Policy."""

    def __init__(self) -> None:
        self._steps = WGS_CLINICAL_QC_STEPS
        self._step_map: dict[str, StepDefinition] = {s.step_id: s for s in self._steps}

    def validate_asset_and_type(self, inspection_type: str, asset_id: str) -> dict[str, Any]:
        if inspection_type != "wgs_clinical_qc":
            raise AdapterError(
                ErrorCode.INVALID_INPUT,
                f"Unknown inspection type '{inspection_type}'. Allowed: 'wgs_clinical_qc'.",
            )
        if asset_id not in GENOMICS_ASSET_CATALOG:
            raise AdapterError(
                ErrorCode.INVALID_INPUT,
                f"Unknown flow cell '{asset_id}'. Allowed flow cells: {list(GENOMICS_ASSET_CATALOG.keys())}.",
            )
        return dict(GENOMICS_ASSET_CATALOG[asset_id])

    def get_steps(self, inspection_type: str) -> tuple[StepDefinition, ...]:
        if inspection_type != "wgs_clinical_qc":
            raise AdapterError(
                ErrorCode.INVALID_INPUT,
                f"Unknown inspection type '{inspection_type}'. Allowed: 'wgs_clinical_qc'.",
            )
        return self._steps

    def get_step(self, inspection_type: str, step_id: str) -> StepDefinition:
        if inspection_type != "wgs_clinical_qc":
            raise AdapterError(
                ErrorCode.INVALID_INPUT,
                f"Unknown inspection type '{inspection_type}'. Allowed: 'wgs_clinical_qc'.",
            )
        step = self._step_map.get(step_id)
        if step is None:
            raise AdapterError(
                ErrorCode.INVALID_INPUT,
                f"Step '{step_id}' not found in 'wgs_clinical_qc'.",
            )
        return step

    def validate_reading(
        self, inspection_type: str, step_id: str, value: float, unit: str | None = None
    ) -> tuple[bool, str | None]:
        step = self.get_step(inspection_type, step_id)
        if value < step.min_value:
            return False, "OUT_OF_RANGE_LOW"
        if value > step.max_value:
            return False, "OUT_OF_RANGE_HIGH"
        return True, None

    def resolve_exception_behavior(
        self, inspection_type: str, step_id: str, resolution: str
    ) -> ResolutionBehavior:
        step = self.get_step(inspection_type, step_id)
        if resolution not in step.resolution_policies:
            raise AdapterError(
                ErrorCode.INVALID_INPUT,
                f"Resolution '{resolution}' is not whitelisted for step '{step_id}'. "
                f"Allowed: {list(step.resolution_policies.keys())}.",
            )
        return step.resolution_policies[resolution]

    def build_completion_metadata(self, execution: WorkflowExecution) -> dict[str, Any]:
        asset_info = GENOMICS_ASSET_CATALOG.get(execution.asset_id, {})
        cohort_id = asset_info.get("cohort_id", "UNKNOWN_COHORT")
        return {
            "workflow_domain": "clinical_genomics_wgs_qc",
            "asset_id": execution.asset_id,
            "cohort_id": cohort_id,
            "ica_project_handoff": f"ICA-PROJ-{cohort_id}",
            "secondary_analysis_pipeline": "DRAGEN-Germline-WGS-v4.3-HW-Accel",
            "tertiary_interpretation_engine": "Emedgene-XAI-RareDisease-Shortlist",
            "pipeline_release_target": "ICA_DRAGEN_EMEDGENE",
            "release_decision": "APPROVED_FOR_SEQUENCING_AND_DRAGEN_INGEST",
        }
