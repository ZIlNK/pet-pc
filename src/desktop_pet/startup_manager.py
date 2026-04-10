"""Windows startup management for Desktop Pet.

Handles enabling/disabling auto-start on Windows boot via registry.
"""
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Registry key for Windows startup programs
STARTUP_REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "DesktopPet"


def get_app_path() -> str:
    """Get the application executable path.

    Returns the EXE path when running as compiled executable,
    or the Python script path when running in development.
    """
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        return str(Path(sys.executable).resolve())
    else:
        # Running in development - use uv run command
        # For development, we return a batch script path or the python command
        return str(Path(sys.executable).resolve())


def is_startup_enabled() -> bool:
    """Check if the application is configured to start on boot.

    Returns:
        True if startup is enabled in registry, False otherwise.
    """
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REGISTRY_KEY) as key:
            try:
                winreg.QueryValueEx(key, APP_NAME)
                return True
            except FileNotFoundError:
                return False
    except Exception as e:
        logger.error(f"Failed to check startup status: {e}")
        return False


def enable_startup() -> bool:
    """Enable auto-start on Windows boot.

    Adds the application to the Windows startup registry.

    Returns:
        True if successful, False otherwise.
    """
    try:
        import winreg
        app_path = get_app_path()

        # If running in development, create a batch file to run the app
        if not getattr(sys, 'frozen', False):
            # Create a VBS script for silent execution (no console window)
            vbs_path = Path.home() / "AppData" / "Roaming" / "DesktopPet" / "startup.vbs"
            vbs_path.parent.mkdir(parents=True, exist_ok=True)

            # Get the project directory
            project_dir = str(Path(__file__).parent.parent.parent)

            vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "{project_dir}"
WshShell.Run "cmd /c uv run desktop-pet", 0, False
'''
            vbs_path.write_text(vbs_content, encoding='utf-8')
            app_path = str(vbs_path)

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            STARTUP_REGISTRY_KEY,
            0,
            winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, app_path)

        logger.info(f"Startup enabled: {app_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to enable startup: {e}")
        return False


def disable_startup() -> bool:
    """Disable auto-start on Windows boot.

    Removes the application from the Windows startup registry.

    Returns:
        True if successful, False otherwise.
    """
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            STARTUP_REGISTRY_KEY,
            0,
            winreg.KEY_SET_VALUE
        ) as key:
            try:
                winreg.DeleteValue(key, APP_NAME)
                logger.info("Startup disabled")
                return True
            except FileNotFoundError:
                # Already not in startup
                return True
    except Exception as e:
        logger.error(f"Failed to disable startup: {e}")
        return False


def set_startup_enabled(enabled: bool) -> bool:
    """Set whether the application should start on boot.

    Args:
        enabled: True to enable startup, False to disable.

    Returns:
        True if successful, False otherwise.
    """
    if enabled:
        return enable_startup()
    else:
        return disable_startup()