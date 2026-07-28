"""Launch and wake the single Electron control-center window."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from pathlib import Path


class ElectronControlLaunchError(RuntimeError):
    """Raised when the Electron control center cannot be launched."""


class ElectronControlLauncher:
    """Start Electron once and use its single-instance lock to focus it later."""

    def __init__(
        self,
        project_root: Path | None = None,
        popen: Callable[..., subprocess.Popen] | None = None,
    ) -> None:
        self.project_root = project_root or Path(__file__).resolve().parents[2]
        self._popen = popen or subprocess.Popen

    @property
    def command(self) -> list[str]:
        """Build the npm command without exposing any renderer IPC capability."""
        npm_command = "npm.cmd" if os.name == "nt" else "npm"
        return [
            npm_command,
            "--prefix",
            str(self.project_root / "electron-control-center"),
            "run",
            "electron",
        ]

    def open(self, api_url: str | None = None) -> bool:
        """Launch Electron or send its existing single instance a focus request."""
        control_center = self.project_root / "electron-control-center"
        if not control_center.is_dir():
            raise ElectronControlLaunchError(
                f"Electron control center is missing: {control_center}"
            )

        environment = os.environ.copy()
        if api_url:
            environment["DESKTOP_PET_API_URL"] = api_url
        kwargs: dict[str, object] = {
            "cwd": str(self.project_root),
            "env": environment,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self._popen(self.command, **kwargs)
        except OSError as error:
            raise ElectronControlLaunchError(str(error)) from error
        return True
