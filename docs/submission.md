# Hackathon Submission Package — Checkpoint

## 1. Primary Track (Alexa+ & MCP Workflow Assistant)
* **Project Title:** Checkpoint — Hands-Free Clinical Genomics Wet-Lab QC & Workflow Assistant
* **Core Thesis:** Remembering a conversation is not the same as knowing the authoritative state of a business process.
* **What We Built:**
  1. **`alexa-plus-genomics-workflow-assistant`:** A voice-first Whole Genome Sequencing (WGS) wet-lab pre-sequencing quality control assistant (`wgs_clinical_qc` on synthetic flow cells `FLOWCELL-WGS-07` and `FLOWCELL-WGS-08`) gating downstream cloud bioinformatics release (ICA → DRAGEN → Emedgene).
  2. **`mcp-workflow-adapter`:** A standalone, Apache-2.0 licensed, domain-neutral Python MCP workflow durability library.
* **Explicit Candor & Safety Disclosures:**
  * All flow cells (`FLOWCELL-WGS-07`), pump assets (`PUMP-07`), and readings are synthetic software reliability fixtures. This project is not an FDA/CLIA/CAP certified medical device and does not actuate physical lab or industrial hardware.
  * When executed via `scripts/run_demo_walkthrough.py`, the walkthrough explicitly labels itself as `LOCAL_MCP_SIMULATION` or `REMOTE_AWS_MCP_SIMULATION` (`AC14`).

## 2. AWS Builder Mini-Challenge Description
* **AWS Services Used in Production Code (`infra/cdk/checkpoint_stack.py`):**
  1. **Amazon DynamoDB (`CheckpointWorkflowTable`):** Authoritative single-table transactional store using multi-item `TransactWriteItems` and deterministic `ClientRequestToken`s across `PRINCIPAL#`, `ASSET#`, and `EXEC#` partition keys.
  2. **AWS Step Functions Standard (`CheckpointInspectionStateMachine`):** Asynchronous lifecycle orchestrator synchronized via `.waitForTaskToken` callbacks, 5,000 ms fenced token leases (`sfn_lease_seq`), and single-active-execution recovery epochs (`R1`–`R8`).
  3. **AWS Lambda:** Runs the MCP Streamable HTTP server (`CheckpointMcpServerLambda`) and Step Functions state-machine task handlers (`AckAndRouteLambda`, `RegisterWaitTokenLambda`).
  4. **Amazon API Gateway HTTP API:** Exposes `POST /mcp` and `GET /.well-known/oauth-protected-resource` over HTTPS.
  5. **Amazon SNS (`CheckpointNotificationTopic`):** Publishes redacted live workflow notifications (`ON_PAUSE_INTERRUPTION`, `ON_STEP_REVISION`, `ON_EXCEPTION_BLOCKED`, `ON_STATUS_REQUESTED`, `ON_INSPECTION_COMPLETED`).
  6. **AWS CDK (Python):** Reproducible infrastructure-as-code (`cdk synth`, `cdk deploy`, `cdk destroy`).

## 3. Open Source Mini-Challenge Description
* **Repository:** `mcp-workflow-adapter`
* **License:** `Apache-2.0`
* **Why It Is Independently Useful:** Provides any Python MCP server developer with a drop-in hexagonal workflow engine (`CREATED`, `RUNNING`, `BLOCKED`, `COMPLETED`), canonical SHA-256 idempotency (`duplicate: true` replay envelopes), active asset exclusivity locking, multi-session disambiguation, live notification outbox, offline SQLite WAL persistence, and fenced AWS Step Functions reconciliation—proven across two distinct domains (Clinical Genomics WGS QC and Industrial Pump Inspection).
