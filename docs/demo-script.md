# 3-Minute Demo Script — Checkpoint: Clinical Genomics WGS Wet-Lab QC Assistant

* **Total Runtime:** 3:00
* **Core Thesis:** Remembering a conversation is not the same as knowing the authoritative state of a business process.

## 0:00 – 0:35 | The Clinical Genomics Wet-Lab Bottleneck
* **Visual:** Split-screen showing the terminal running the MCP Streamable HTTP server alongside the clinical genomics pre-sequencing checklist (`FLOWCELL-WGS-07`).
* **Narration:** "In a clinical genetics lab performing Whole Genome Sequencing for rare disease diagnosis, a wet-lab technologist works in double nitrile gloves at the bench. Before loading a $5,000 NovaSeq flow cell and releasing data to Illumina Connected Analytics, DRAGEN variant calling, and Emedgene AI interpretation, they must verify three strict QC gates: Qubit DNA concentration, TapeStation fragment length, and loading molarity. They cannot touch a keyboard without de-gloving—and conversational memory alone cannot safely gate a clinical sequencing run."

## 0:35 – 1:25 | Starting, Recording, Session Pause Notifications & Collision Protection
* **Visual:** Execute Steps 1–4 of `scripts/run_demo_walkthrough.py`.
* **Narration:** "Here, the technologist starts `wgs_clinical_qc` on `FLOWCELL-WGS-07` and records valid Qubit (`42.5 ng/uL`) and TapeStation (`475 bp`) readings. When they pause for a 15-minute incubation, `configure_notifications` marks the session paused and dispatches a live checkpoint notification. If another operator tries to start a duplicate run on `FLOWCELL-WGS-07`, our atomic asset exclusivity lock blocks it. And when the technologist has two flow cells active (`FLOWCELL-WGS-07` and `FLOWCELL-WGS-08`) and says 'Resume my inspection', Checkpoint refuses to guess—returning `AMBIGUOUS_ACTIVE_SESSION` so the technologist disambiguates."

## 1:25 – 2:15 | Process Restart Recovery, Idempotent Retry & Over-Clustering Block
* **Visual:** Execute Steps 5–8 of `scripts/run_demo_walkthrough.py`.
* **Narration:** "After a server restart, `get_inspection_status` recovers exact progress from SQLite WAL / DynamoDB (`steps 1 and 2 committed, loading_molarity_pm pending`). Replaying Step 2 with the same `idempotency_key` returns the original result with `duplicate: true` without advancing state twice. Next, the technologist submits an out-of-range loading molarity of `310.0 pM` (above the `250.0 pM` max). The engine immediately transitions to `BLOCKED`, emits an escalation alert, and rejects `complete_inspection` (`WORKFLOW_BLOCKED`)."

## 2:15 – 3:00 | Policy Resolution, DRAGEN Pipeline Release & Open-Source Reuse
* **Visual:** Execute Steps 9–11 of `scripts/run_demo_walkthrough.py` and run `python mcp-workflow-adapter/examples/industrial_pump_inspection.py`.
* **Narration:** "When an unapproved override (`FORCE_PASS`) is attempted, the server rejects it with `INVALID_INPUT`. Only after applying the whitelisted policy `DILUTE_LIBRARY_TO_TARGET_MOLARITY_AND_RETEST` and recording a valid `215.0 pM` reading does `complete_inspection` succeed—releasing the run to the ICA, DRAGEN, and Emedgene pipeline with an immutable audit reference. Finally, our standalone Apache-2.0 library `mcp-workflow-adapter` has zero genomics code inside its core and powers a completely different industrial pump inspection domain out of the box."
