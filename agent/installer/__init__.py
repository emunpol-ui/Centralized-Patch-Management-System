"""
Client Agent installer package (DEPLOY-003; FR-011 Silent Software
Installation).

Responsible for verifying a downloaded installer's integrity
(``checksum``) and executing it silently as a direct process
(``executor``). Does not perform any network I/O itself - downloading is
``agent.communication.deployment_client``'s responsibility - and does not
report results back to the server, which is DEPLOY-004 scope
(``agent.deployment.manager`` orchestrates all of the above).
"""