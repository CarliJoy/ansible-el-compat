"""
Shared pytest fixtures for carlijoy.compat.dnf integration tests.

A base Docker image is built once per session (openssh-server + python3.12 +
EPEL pre-installed, SSH host keys baked in).  Each test then gets its own
fresh container started from that image, named by a hash of the test node ID
so containers are identifiable in Docker ps output.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import yaml
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import PortWaitStrategy

if TYPE_CHECKING:
    from collections.abc import Generator

_BASE_IMAGE_TAG = "ansible-el-compat-alma8-base:latest"
_DOCKER_DIR = Path(__file__).parent / "docker"
SSH_PORT = 22


@dataclass
class ContainerInfo:
    host: str
    port: int
    user: str
    private_key: Path


# ---------------------------------------------------------------------------
# SSH keypair — generated once per session
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def ssh_keypair(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Generate a temporary SSH keypair for the test session."""
    key_dir = tmp_path_factory.mktemp("ssh")
    private_key = key_dir / "id_ed25519"
    public_key = key_dir / "id_ed25519.pub"
    subprocess.run(
        [
            "ssh-keygen",
            "-t",
            "ed25519",
            "-N",
            "",
            "-C",
            "ansible-test",
            "-f",
            str(private_key),
        ],
        check=True,
        capture_output=True,
    )
    private_key.chmod(0o600)
    return {"private": private_key, "public": public_key}


# ---------------------------------------------------------------------------
# Base Docker image — built once per session, reused for every test container
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def alma8_base_image() -> str:
    """
    Build (or rebuild via Docker layer cache) the image from tests/docker/.
    Uses buildx so the BuildKit heredoc syntax in the Dockerfile is available.
    --load makes the resulting image available to the local Docker daemon.
    Returns the image tag.
    """
    subprocess.run(
        [
            "docker",
            "buildx",
            "build",
            "--load",
            "-t",
            _BASE_IMAGE_TAG,
            str(_DOCKER_DIR),
        ],
        check=True,
    )
    return _BASE_IMAGE_TAG


# ---------------------------------------------------------------------------
# Per-test container — fresh instance from the base image for each test
# ---------------------------------------------------------------------------


@pytest.fixture
def alma8_container(
    ssh_keypair: dict[str, Path],
    alma8_base_image: str,
    request: pytest.FixtureRequest,
) -> Generator[ContainerInfo, None, None]:
    """
    Start a fresh almalinux:8 container for this test from the pre-built image.
    The container name encodes a hash of the test node ID for easy identification.
    Any stale container with the same name is removed before starting.
    """
    pubkey = ssh_keypair["public"].read_text().strip()
    node_hash = hashlib.sha256(request.node.nodeid.encode()).hexdigest()[:12]
    container_name = f"ael-test-{node_hash}"

    # Remove a stale container with this name (e.g. from a crashed previous run).
    subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)

    container = (
        DockerContainer(alma8_base_image)
        .with_exposed_ports(SSH_PORT)
        .with_env("SSH_PUBKEY", pubkey)
        .with_name(container_name)
        .waiting_for(PortWaitStrategy(SSH_PORT))
    )

    with container:
        yield ContainerInfo(
            host=container.get_container_host_ip(),
            port=int(container.get_exposed_port(SSH_PORT)),
            user="ansible",
            private_key=ssh_keypair["private"],
        )


# ---------------------------------------------------------------------------
# Per-test Ansible inventory + config
# ---------------------------------------------------------------------------


@pytest.fixture
def ansible_env(
    alma8_container: ContainerInfo,
    tmp_path: Path,
) -> dict[str, Path]:
    """Write inventory.yml and ansible.cfg pointing at the per-test container."""
    inventory = tmp_path / "inventory.yml"
    inventory.write_text(
        yaml.dump(
            {
                "alma8": {
                    "hosts": {
                        "testhost": {
                            "ansible_host": alma8_container.host,
                            "ansible_port": alma8_container.port,
                            "ansible_user": alma8_container.user,
                            "ansible_ssh_private_key_file": str(alma8_container.private_key),
                            "ansible_python_interpreter": "/usr/bin/python3.12",
                            "ansible_ssh_common_args": (
                                "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
                            ),
                        }
                    }
                }
            },
            sort_keys=False,
        )
    )

    cfg = tmp_path / "ansible.cfg"
    cfg.write_text("[defaults]\nhost_key_checking = False\n")

    return {"inventory": inventory, "cfg": cfg, "dir": tmp_path}
