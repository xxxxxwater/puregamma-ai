"""Isolated Python research runner.

User research code is executed only inside an ephemeral, network-less Docker
container spawned by the worker. This package contains the static (AST) code
validator, the approved-dataset exporter, and the docker CLI runner. The API
and worker processes never execute user code inline.
"""

from packages.research_runner.validator import CodeValidationError, validate_research_code
from packages.research_runner.docker_runner import docker_available

__all__ = ["CodeValidationError", "validate_research_code", "docker_available"]
