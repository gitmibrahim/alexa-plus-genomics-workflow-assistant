#!/usr/bin/env python3
from __future__ import annotations

import aws_cdk as cdk
from checkpoint_stack import CheckpointGenomicsStack

app = cdk.App()
stage = app.node.try_get_context("stage") or "dev"

CheckpointGenomicsStack(
    app,
    f"CheckpointGenomics-{stage}",
    stage_name=stage,
    env=cdk.Environment(
        account=app.node.try_get_context("account") or None,
        region=app.node.try_get_context("region") or "us-east-1",
    ),
)

app.synth()
