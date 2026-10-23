from __future__ import annotations

import pytest

from genomics_assistant.domain import GenomicsDomainPolicy


@pytest.fixture(autouse=True)
def clean_aws_env_for_offline_tests(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    """Strips AWS credential environment variables for all non-aws tests (AC12 guardrail)."""
    if "aws" not in request.keywords:
        monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
        monkeypatch.delenv("AWS_SESSION_TOKEN", raising=False)
        monkeypatch.delenv("AWS_PROFILE", raising=False)
        monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)


@pytest.fixture
def policy() -> GenomicsDomainPolicy:
    return GenomicsDomainPolicy()
