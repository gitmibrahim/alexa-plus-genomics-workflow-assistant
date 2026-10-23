# Checkpoint: `alexa-plus-genomics-workflow-assistant`

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

Hands-free Whole Genome Sequencing (WGS) wet-lab quality-control (QC) and cloud bioinformatics pipeline release assistant for Alexa+, powered by `mcp-workflow-adapter`.

> **Core Systems Thesis:** Remembering a conversation is not the same as knowing the authoritative state of a business process.

In a BSL-2 clinical genomics laboratory performing Whole Genome Sequencing for rare and hereditary genetic disease testing, technologists wear double nitrile gloves, lab coats, and eye protection while handling DNA libraries, Qubit fluorometers, TapeStation bioanalyzers, and NovaSeq flow cells. Touching a keyboard or mouse contaminates the station or requires de-gloving.

Before a high-consequence flow cell (`FLOWCELL-WGS-07`) is loaded and released into cloud bioinformatics pipelines (Illumina Connected Analytics → DRAGEN secondary variant calling → Emedgene explainable AI tertiary interpretation), three strict pre-sequencing QC gates must be recorded and validated:

1. **`dna_concentration_ng_ul`:** Qubit dsDNA Yield Concentration (`15.0`–`60.0 ng/uL`)
2. **`fragment_size_bp`:** TapeStation Mean Library Fragment Length (`400.0`–`550.0 bp`)
3. **`loading_molarity_pm`:** Normalized Flow-Cell Loading Molarity (`180.0`–`250.0 pM`)

---

## Safety, Candor & Compliance Notice

* **Synthetic Data Only:** All flow-cell identifiers (`FLOWCELL-WGS-07`, `FLOWCELL-WGS-08`), cohort labels, readings, and pipeline release manifests are 100% synthetic software reliability fixtures. This project contains zero Protected Health Information (PHI) or real patient data.
* **No Medical or Hardware Actuation Claims:** This project is an engineering demonstration of deterministic MCP workflow state recovery. It is not an FDA, CLIA, CAP, or CE-IVD certified clinical diagnostic device and does not actuate physical sequencing or laboratory hardware.

---

## Quick Start (Offline Mode)

```bash
# 1. Install dependencies in editable mode
pip install -e "../mcp-workflow-adapter[dev]"
pip install -e ".[dev]"

# 2. Run the offline test suite (subprocess restart, concurrency, wgs journey)
pytest tests/

# 3. Execute the labeled simulation walkthrough
python scripts/run_demo_walkthrough.py --mode local
```

---

## License

This project is licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for details.
