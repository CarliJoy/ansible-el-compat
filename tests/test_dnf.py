"""
Integration tests for carlijoy.compat.dnf.

Each test function receives its own fresh container (function-scoped fixture)
and tests a full scenario.  Related steps within a scenario (install →
idempotent → remove → idempotent) run as subtests so every step is reported
individually even when an earlier one fails.

Packages used:
  - tree  — available in BaseOS/AppStream, tiny, no side-effects
  - htop  — available in EPEL, equally harmless
  - jq    — EPEL only; exercises disablerepo/enablerepo wiring end-to-end
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest
import yaml

pytestmark = pytest.mark.integration

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _play(*tasks: dict) -> list[dict]:  # type: ignore[type-arg]
    """Wrap tasks in a single play targeting the alma8 inventory group."""
    return [{"hosts": "alma8", "become": True, "tasks": list(tasks)}]


def run_playbook(
    playbook: list[dict],  # type: ignore[type-arg]
    ansible_env: dict,  # type: ignore[type-arg]
    tmp_path: Path,
    *,
    suffix: str = "playbook",
) -> subprocess.CompletedProcess:  # type: ignore[type-arg]
    """Serialise playbook to YAML, write it to disk, and run ansible-playbook."""
    playbook_file = tmp_path / f"{suffix}.yml"
    playbook_file.write_text(yaml.dump(playbook, sort_keys=False))

    return subprocess.run(
        [
            "ansible-playbook",
            "-i",
            str(ansible_env["inventory"]),
            str(playbook_file),
            "-v",
        ],
        capture_output=True,
        text=True,
        env={**_inherit_env(), "ANSIBLE_CONFIG": str(ansible_env["cfg"])},
    )


def _inherit_env() -> dict[str, str]:
    import os

    return dict(os.environ)


def assert_ok(result: subprocess.CompletedProcess) -> None:  # type: ignore[type-arg]
    """Fail the test with useful output if the playbook failed."""
    if result.returncode != 0:
        pytest.fail(
            f"ansible-playbook failed (rc={result.returncode})\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestInstallAndRemove:
    """Basic install / remove lifecycle using 'tree' from BaseOS."""

    def test_tree_lifecycle(
        self,
        ansible_env: dict,  # type: ignore[type-arg]
        tmp_path: Path,
        subtests: pytest.Subtests,
    ) -> None:
        """Full install → idempotent → remove → idempotent cycle on one container."""
        with subtests.test("install reports changed"):
            assert_ok(
                run_playbook(
                    _play(
                        {
                            "name": "Install tree",
                            "carlijoy.compat.dnf": {"name": "tree", "state": "present"},
                            "register": "result",
                        },
                        {"assert": {"that": "result.changed"}},
                    ),
                    ansible_env,
                    tmp_path,
                    suffix="install",
                )
            )

        with subtests.test("install is idempotent"):
            assert_ok(
                run_playbook(
                    _play(
                        {
                            "name": "Install tree again",
                            "carlijoy.compat.dnf": {"name": "tree", "state": "present"},
                            "register": "result",
                        },
                        {"assert": {"that": "not result.changed"}},
                    ),
                    ansible_env,
                    tmp_path,
                    suffix="install_idem",
                )
            )

        with subtests.test("remove reports changed"):
            assert_ok(
                run_playbook(
                    _play(
                        {
                            "name": "Remove tree",
                            "carlijoy.compat.dnf": {"name": "tree", "state": "absent"},
                            "register": "result",
                        },
                        {"assert": {"that": "result.changed"}},
                    ),
                    ansible_env,
                    tmp_path,
                    suffix="remove",
                )
            )

        with subtests.test("remove is idempotent"):
            assert_ok(
                run_playbook(
                    _play(
                        {
                            "name": "Remove tree again",
                            "carlijoy.compat.dnf": {"name": "tree", "state": "absent"},
                            "register": "result",
                        },
                        {"assert": {"that": "not result.changed"}},
                    ),
                    ansible_env,
                    tmp_path,
                    suffix="remove_idem",
                )
            )


class TestMultiplePackages:
    """Install and remove a list of packages in a single task."""

    def test_multiple_packages_lifecycle(
        self,
        ansible_env: dict,  # type: ignore[type-arg]
        tmp_path: Path,
        subtests: pytest.Subtests,
    ) -> None:
        with subtests.test("install tree and htop"):
            assert_ok(
                run_playbook(
                    _play(
                        {
                            "name": "Install tree and htop",
                            "carlijoy.compat.dnf": {
                                "name": ["tree", "htop"],
                                "state": "present",
                            },
                            "register": "result",
                        },
                        {"assert": {"that": "result.changed"}},
                    ),
                    ansible_env,
                    tmp_path,
                    suffix="install",
                )
            )

        with subtests.test("remove tree and htop"):
            assert_ok(
                run_playbook(
                    _play(
                        {
                            "name": "Remove tree and htop",
                            "carlijoy.compat.dnf": {
                                "name": ["tree", "htop"],
                                "state": "absent",
                            },
                            "register": "result",
                        },
                        {"assert": {"that": "result.changed"}},
                    ),
                    ansible_env,
                    tmp_path,
                    suffix="remove",
                )
            )


class TestEpelRepo:
    """
    Install htop from EPEL to exercise the enablerepo parameter.

    htop is in EPEL but NOT in BaseOS/AppStream on EL8.  Passing
    enablerepo=epel confirms the repo-selection wiring reaches dnf.
    """

    def test_epel_lifecycle(
        self,
        ansible_env: dict,  # type: ignore[type-arg]
        tmp_path: Path,
        subtests: pytest.Subtests,
    ) -> None:
        with subtests.test("install htop from EPEL reports changed"):
            assert_ok(
                run_playbook(
                    _play(
                        {
                            "name": "Install htop from EPEL",
                            "carlijoy.compat.dnf": {
                                "name": "htop",
                                "state": "present",
                                "enablerepo": "epel",
                            },
                            "register": "result",
                        },
                        {"assert": {"that": "result.changed"}},
                    ),
                    ansible_env,
                    tmp_path,
                    suffix="install",
                )
            )

        with subtests.test("install htop is idempotent"):
            assert_ok(
                run_playbook(
                    _play(
                        {
                            "name": "Install htop from EPEL again",
                            "carlijoy.compat.dnf": {
                                "name": "htop",
                                "state": "present",
                                "enablerepo": "epel",
                            },
                            "register": "result",
                        },
                        {"assert": {"that": "not result.changed"}},
                    ),
                    ansible_env,
                    tmp_path,
                    suffix="install_idem",
                )
            )

        with subtests.test("remove htop reports changed"):
            assert_ok(
                run_playbook(
                    _play(
                        {
                            "name": "Remove htop",
                            "carlijoy.compat.dnf": {"name": "htop", "state": "absent"},
                            "register": "result",
                        },
                        {"assert": {"that": "result.changed"}},
                    ),
                    ansible_env,
                    tmp_path,
                    suffix="remove",
                )
            )


class TestUpdateCache:
    """update_cache=true should force a metadata refresh before install."""

    def test_install_with_cache_refresh(
        self,
        ansible_env: dict,  # type: ignore[type-arg]
        tmp_path: Path,
    ) -> None:
        assert_ok(
            run_playbook(
                _play(
                    {
                        "name": "Install tree with cache refresh",
                        "carlijoy.compat.dnf": {
                            "name": "tree",
                            "state": "present",
                            "update_cache": True,
                        },
                        "register": "result",
                    },
                    {"assert": {"that": "result.changed"}},
                ),
                ansible_env,
                tmp_path,
            )
        )


class TestStateLatest:
    """state=latest should install and report changed when package is absent."""

    def test_latest_installs_if_absent(
        self,
        ansible_env: dict,  # type: ignore[type-arg]
        tmp_path: Path,
    ) -> None:
        assert_ok(
            run_playbook(
                _play(
                    {
                        "name": "Ensure latest tree",
                        "carlijoy.compat.dnf": {"name": "tree", "state": "latest"},
                        "register": "result",
                    },
                    {"assert": {"that": "result.changed"}},
                ),
                ansible_env,
                tmp_path,
            )
        )
