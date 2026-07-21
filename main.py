#!/usr/bin/env python
"""
Standalone entry point for Desktop Pet.
This file is used by PyInstaller to build the executable.

实际启动逻辑位于 ``desktop_pet.__main__``，本文件仅做转发，
确保 ``python main.py`` 与 ``uv run desktop-pet`` / ``python -m desktop_pet``
行为一致。
"""


def main():
    """Forward to desktop_pet.__main__.main()."""
    from desktop_pet.__main__ import main as _main

    _main()


if __name__ == "__main__":
    main()
