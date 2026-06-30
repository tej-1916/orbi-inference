"""Static worker isolation and container security tests."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[4]


@pytest.mark.security
def test_docker_worker_runs_as_non_root() -> None:
    dockerfile = (ROOT / "apps/node/Dockerfile").read_text(encoding="utf-8")
    assert "USER orbi-node" in dockerfile
    assert "USER root" not in dockerfile


@pytest.mark.security
def test_node_compose_receives_no_control_plane_or_user_credentials() -> None:
    compose = yaml.safe_load(
        (ROOT / "deploy/docker-compose.yml").read_text(encoding="utf-8")
    )
    environment = compose["services"]["node"]["environment"]
    forbidden = {
        "ORBI_DATABASE_URL",
        "ORBI_REDIS_URL",
        "ORBI_API_KEY_PEPPER",
        "ORBI_ADMIN_TOKEN",
        "ORBI_JWT_PRIVATE_KEY_PATH",
        "ORBI_JWT_PUBLIC_KEY_PATH",
    }
    assert forbidden.isdisjoint(environment)
    assert all("API_KEY" not in key for key in environment)


@pytest.mark.security
def test_worker_routes_cannot_access_user_or_api_key_records() -> None:
    source = (
        ROOT / "apps/gateway/src/orbi_gateway/routes/internal/workers.py"
    ).read_text(encoding="utf-8")
    assert "APIKey" not in source
    assert "Project" not in source
    assert "require_api_key" not in source
