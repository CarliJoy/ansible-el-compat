from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface
from hatchling.builders.plugin.interface import BuilderInterface
from packaging.version import Version

_COLLECTION_DIR = Path("src/ansible_collections/carlijoy/compat")


def _read_galaxy_version(collection_dir: Path) -> str:
    for line in (collection_dir / "galaxy.yml").read_text().splitlines():
        if line.startswith("version:"):
            return line.split(":", 1)[1].strip()
    raise ValueError("version: key not found in galaxy.yml")


_DNF_BUNDLE_SCRIPT = Path("build-script") / "build_dnf_bundle.py"
_DNF_MODULE = _COLLECTION_DIR / "plugins" / "modules" / "dnf"


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        self._generate_galaxy_yml(build_data)
        self._build_dnf_bundle(build_data)

    def _generate_galaxy_yml(self, build_data: dict[str, Any]) -> None:
        v = Version(self.metadata.version)
        galaxy_version = f"{v.major}.{v.minor}.{v.micro}"
        template = Path(self.root) / _COLLECTION_DIR / "galaxy.template.yml"
        output = Path(self.root) / _COLLECTION_DIR / "galaxy.yml"
        output.write_text(template.read_text().format(version=galaxy_version))
        build_data["artifacts"].append(str(_COLLECTION_DIR / "galaxy.yml"))

    def _build_dnf_bundle(self, build_data: dict[str, Any]) -> None:
        script = Path(self.root) / _DNF_BUNDLE_SCRIPT
        subprocess.run(["uv", "run", str(script)], check=True, cwd=self.root)
        build_data["artifacts"].append(str(_DNF_MODULE))


class CustomBuilder(BuilderInterface):
    PLUGIN_NAME = "galaxy"

    def get_version_api(self) -> dict[str, Any]:
        return {"standard": self.build_standard}

    def get_default_versions(self) -> list[str]:
        return ["standard"]

    def build_standard(self, directory: str, **build_data: object) -> str:
        collection_dir = Path(self.root) / _COLLECTION_DIR

        ansible_galaxy = shutil.which("ansible-galaxy")
        if ansible_galaxy is None:
            raise RuntimeError("ansible-galaxy not found in PATH; install ansible-core")

        subprocess.run(
            [
                ansible_galaxy,
                "collection",
                "build",
                "--output-path",
                directory,
                "--force",
                str(collection_dir),
            ],
            check=True,
        )

        galaxy_version = _read_galaxy_version(collection_dir)
        return str(Path(directory) / f"carlijoy-compat-{galaxy_version}.tar.gz")
