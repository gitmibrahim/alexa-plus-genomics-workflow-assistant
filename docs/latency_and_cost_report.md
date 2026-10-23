# Multi-Boundary Latency Benchmark & AWS Cost Report (`AC15`)

## 1. Engineering Targets vs. Measurement Boundaries

* **Read Latency Engineering Target (`NFR-1`):** `p50 < 150.0 ms`, `p95 < 350.0 ms`
* **Mutation Latency Engineering Target (`NFR-1`):** `p50 < 250.0 ms`, `p95 < 500.0 ms`

---

## 2. Boundary 1 — Local Server-Side Execution (Measured: Streamable HTTP + OAuth 2.1 RS256 + SQLite WAL)

| Operation Category | Samples | Min (ms) | p50 (ms) | p95 (ms) | p99 (ms) | Mean (ms) | Max (ms) | Target Met |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Read (`get_inspection_status`)** | 50 | 2.37 | **12.94** | **18.56** | 29.98 | 13.89 | 32.31 | PASS |
| **Mutations (`start`, `record`, `complete`)** | 250 | 1.8 | **12.1** | **16.95** | 19.49 | 9.79 | 42.92 | PASS |
| **Idempotent Replay (`duplicate=True`)** | 50 | 8.48 | **13.24** | **19.12** | 19.68 | 13.83 | 19.69 | PASS |

---

## 3. Boundary 2 — Deployed AWS HTTPS Endpoint (`API Gateway -> Lambda -> DynamoDB TransactWriteItems`)

* **Measurement Status:** Measured via `pytest -m aws` / `benchmark_latency.py --mode aws` when deployed against live AWS credentials.
* **Architectural Bound:** Because MCP mutations commit synchronously to single-table DynamoDB (`TransactWriteItems`) and trigger Step Functions Standard asynchronously via the fenced outbox reconciler, end-to-end AWS mutation latency is bounded by single-region API Gateway + warm Lambda + DynamoDB transaction commit time rather than multi-hop Step Functions state transitions.

---

## 4. Boundary 3 — Alexa+ Cloud Platform Round-Trip (`< 500 ms` Platform Target)

* **Candor Disclosure (`AC14`, `AC15`):** CLI benchmark scripts measure Boundary 1 (Local Server-Side) and Boundary 2 (Deployed AWS MCP Endpoint) only. A self-built CLI simulation harness **cannot** measure internal Alexa+ cloud voice recognition or Alexa+ MCP client network routing.

---

## 5. AWS Reference Architecture Resource & Cost Profile

| AWS Resource | Provisioned SKU / Billing Mode | Estimated Cost for Demo & Testing (< 1,000 Runs) |
| :--- | :--- | :--- |
| **Amazon DynamoDB (`CheckpointWorkflowTable`)** | `PAY_PER_REQUEST` (On-Demand) | `< $0.05` (Covered by AWS Free Tier) |
| **AWS Step Functions Standard (`CheckpointInspectionStateMachine`)** | Standard Workflows (`$0.025 / 1,000` state transitions) | `< $0.25` (Covered by 4,000 free transitions/month) |
| **AWS Lambda (`McpServer`, `AckAndRoute`, `RegisterWaitToken`)** | Python 3.11 (`256 MB`–`512 MB` RAM, On-Demand) | `$0.00` (Covered by 1M free requests/month) |
| **Amazon API Gateway (`CheckpointMcpHttpApi`)** | HTTP API v2 (`$1.00 / million` requests) | `< $0.01` |
| **Amazon SNS (`CheckpointNotificationTopic`)** | Standard Topic | `< $0.01` |
