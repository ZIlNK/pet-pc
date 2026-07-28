"""Tests for the Python launcher that wakes the Electron control center."""

import os
from pathlib import Path

PROJECT_ROOT = Path.cwd()

from desktop_pet.electron_control import ElectronControlLauncher


class _Process:
    def poll(self):
        return None


def test_open_starts_electron_with_control_center_prefix():
    calls = []

    def popen(command, **kwargs):
        calls.append((command, kwargs))
        return _Process()

    launcher = ElectronControlLauncher(project_root=PROJECT_ROOT, popen=popen)
    assert launcher.open() is True
    command, kwargs = calls[0]
    npm_command = "npm.cmd" if os.name == "nt" else "npm"
    assert command[:4] == [npm_command, "--prefix", str(PROJECT_ROOT / "electron-control-center"), "run"]
    assert command[4] == "electron"
    assert kwargs["cwd"] == str(PROJECT_ROOT)
    assert "env" in kwargs


def test_open_reissues_electron_command_to_focus_single_instance():
    calls = []

    launcher = ElectronControlLauncher(
        project_root=PROJECT_ROOT,
        popen=lambda command, **kwargs: calls.append((command, kwargs)) or _Process(),
    )
    launcher.open()
    launcher.open()

    # Electron's single-instance lock turns the second command into a focus request,
    # so Python never creates a second control-center window.
    assert len(calls) == 2

def test_open_passes_loopback_api_url_to_electron():
    calls = []
    launcher = ElectronControlLauncher(
        project_root=PROJECT_ROOT,
        popen=lambda command, **kwargs: calls.append((command, kwargs)) or _Process(),
    )

    launcher.open("http://127.0.0.1:8090/api")

    assert calls[0][1]["env"]["DESKTOP_PET_API_URL"] == "http://127.0.0.1:8090/api"


def test_settings_launches_electron_with_configured_loopback_url(monkeypatch):
    from types import SimpleNamespace

    import desktop_pet.__main__ as main
    import desktop_pet.electron_control as electron_control

    calls = []

    class _Launcher:
        def open(self, api_url):
            calls.append(api_url)

    monkeypatch.setattr(electron_control, "ElectronControlLauncher", _Launcher)
    monkeypatch.setattr(main, "_electron_control_launcher", None)

    main._open_settings(SimpleNamespace(global_config=SimpleNamespace(api={"port": 8090})))

    assert calls == ["http://127.0.0.1:8090/api"]
