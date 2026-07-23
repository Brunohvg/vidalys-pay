"""Deployment contract shared by both Coolify Compose files."""

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "filename",
    ["docker-compose.yml", "docker-compose.production.yml"],
)
def test_coolify_compose_files_keep_web_and_worker_on_external_network(filename):
    content = (PROJECT_ROOT / filename).read_text(encoding="utf-8")

    assert content.count("      - coolify") == 2
    assert "\nnetworks:\n  coolify:\n    external: true" in content
