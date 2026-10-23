from __future__ import annotations

import os
from typing import Any

from mangum import Mangum
from starlette.applications import Starlette
from workflow_adapter.auth import AuthProfile, OAuth2TokenVerifier
from workflow_adapter.backends.local import LocalBackend
from workflow_adapter.mcp_server import MCPWorkflowServer
from workflow_adapter.ports import StorageBackendPort

from genomics_assistant.domain import GenomicsDomainPolicy


def create_genomics_backend(policy: GenomicsDomainPolicy | None = None) -> StorageBackendPort:
    pol = policy or GenomicsDomainPolicy()
    backend_mode = os.environ.get("WORKFLOW_BACKEND", "local").lower()

    if backend_mode == "aws":
        from workflow_adapter.backends.aws_step_functions import create_aws_backend

        table_name = os.environ.get("DYNAMODB_TABLE_NAME", "CheckpointGenomicsTable")
        sfn_arn = os.environ.get("SFN_STATE_MACHINE_ARN", "")
        sns_arn = os.environ.get("SNS_NOTIFICATION_TOPIC_ARN")

        return create_aws_backend(
            policy=pol,
            table_name=table_name,
            state_machine_arn=sfn_arn,
            sns_topic_arn=sns_arn,
        )

    sqlite_path = os.environ.get("SQLITE_DB_PATH", "genomics_workflow.db")
    return LocalBackend(sqlite_path, pol)


def create_genomics_asgi_app(
    backend: StorageBackendPort | None = None,
    verifier: OAuth2TokenVerifier | None = None,
) -> Starlette:
    policy = GenomicsDomainPolicy()
    storage_backend = backend or create_genomics_backend(policy)

    if verifier is None:
        issuer_url = os.environ.get("OAUTH_ISSUER_URL", "https://test-issuer.checkpoint.local")
        resource_uri = os.environ.get("MCP_RESOURCE_URI", "https://mcp.checkpoint.local/mcp")
        jwks_json = os.environ.get("OAUTH_JWKS_JSON", '{"keys": []}')
        profile_str = os.environ.get("ALEXA_AUTH_PROFILE", "ALEXA_CATEGORY_MCP")
        profile = getattr(AuthProfile, profile_str, AuthProfile.ALEXA_CATEGORY_MCP)

        verifier = OAuth2TokenVerifier(
            issuer_url=issuer_url,
            resource_uri=resource_uri,
            jwks_json=jwks_json,
            profile=profile,
        )

    server = MCPWorkflowServer(
        backend=storage_backend,
        token_verifier=verifier,
        server_name="checkpoint-genomics-wgs-qc",
        server_version="0.1.0",
    )
    return server.create_asgi_app()


app: Starlette = create_genomics_asgi_app()
lambda_handler: Any = Mangum(app, lifespan="off")
