"""
Client Agent deployment orchestration package (DEPLOY-003).

Ties together deployment polling (FR-009, ``agent.communication.
deployment_client.poll_deployment``), installer download (FR-010,
``agent.communication.deployment_client.download_installer``), checksum
verification, and silent installation (FR-011,
``agent.installer.checksum`` / ``agent.installer.executor``) into a single
runnable cycle - see ``agent.deployment.manager``.

Deployment status *reporting* back to the server (FR-012) is out of scope
for this package until DEPLOY-004 is implemented; ``manager.
run_deployment_cycle`` returns a ``DeploymentExecutionResult`` describing
the outcome so a future DEPLOY-004 reporting client can consume it without
this package needing to change.
"""